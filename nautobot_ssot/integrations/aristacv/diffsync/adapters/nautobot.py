"""DiffSync adapter for Nautobot."""

from collections import defaultdict
from django.contrib.contenttypes.models import ContentType
from django.db.models import ProtectedError
from nautobot.dcim.models import Device as OrmDevice
from nautobot.dcim.models import Interface as OrmInterface
from nautobot.extras.models import Relationship as OrmRelationship
from nautobot.extras.models import RelationshipAssociation as OrmRelationshipAssociation
from nautobot.ipam.models import IPAddress as OrmIPAddress
from nautobot.ipam.models import IPAddressToInterface
from diffsync import DiffSync
from diffsync.exceptions import ObjectNotFound, ObjectAlreadyExists

from nautobot_ssot.integrations.aristacv.diffsync.models.nautobot import (
    NautobotDevice,
    NautobotCustomField,
    NautobotNamespace,
    NautobotPrefix,
    NautobotIPAddress,
    NautobotIPAssignment,
    NautobotPort,
)
from nautobot_ssot.integrations.aristacv.types import CloudVisionAppConfig
from nautobot_ssot.integrations.aristacv.utils import nautobot


class NautobotAdapter(DiffSync):
    """DiffSync adapter implementation for Nautobot custom fields."""

    device = NautobotDevice
    port = NautobotPort
    namespace = NautobotNamespace
    prefix = NautobotPrefix
    ipaddr = NautobotIPAddress
    ipassignment = NautobotIPAssignment
    cf = NautobotCustomField

    top_level = ["device", "namespace", "prefix", "ipaddr", "ipassignment", "cf"]

    def __init__(self, *args, job=None, **kwargs):
        """Initialize the Nautobot DiffSync adapter."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.objects_to_delete = defaultdict(list)

    def load_devices(self):
        """Add Nautobot Device objects as DiffSync Device models."""
        for dev in OrmDevice.objects.filter(device_type__manufacturer__name="Arista"):
            try:
                new_device = self.device(
                    name=dev.name,
                    device_model=dev.device_type.model,
                    serial=dev.serial,
                    status=dev.status.name,
                    version=nautobot.get_device_version(dev),
                    uuid=dev.id,
                )
                self.add(new_device)
            except ObjectAlreadyExists as err:
                self.job.logger.warning(f"Unable to load {dev.name} as it appears to be a duplicate. {err}")
                continue

            self.load_custom_fields(dev=dev)

    def load_custom_fields(self, dev: OrmDevice):
        """Load device custom field data from Nautobot and populate DiffSync models."""
        for cf_name, cf_value in dev.custom_field_data.items():
            if cf_name.startswith("arista_"):
                try:
                    new_cf = self.cf(
                        name=cf_name,
                        value=cf_value if cf_value is not None else "",
                        device_name=dev.name,
                    )
                    self.add(new_cf)
                except AttributeError as err:
                    self.job.logger.warning(f"Unable to load {cf_name}. {err}")
                    continue

    def load_interfaces(self):
        """Add Nautobot Interface objects as DiffSync Port models."""
        for intf in OrmInterface.objects.filter(device__device_type__manufacturer__name="Arista"):
            new_port = self.port(
                name=intf.name,
                device=intf.device.name,
                description=intf.description,
                mac_addr=str(intf.mac_address).lower() if intf.mac_address else "",
                enabled=intf.enabled,
                mode=intf.mode,
                mtu=intf.mtu,
                port_type=intf.type,
                status=intf.status.name,
                uuid=intf.id,
            )
            self.add(new_port)
            try:
                dev = self.get(self.device, intf.device.name)
                dev.add_child(new_port)
            except ObjectNotFound as err:
                self.job.logger.warning(
                    f"Unable to find Device {intf.device.name} in diff to assign to port {intf.name}. {err}"
                )

    def load_ip_addresses(self):
        """Add Nautobot IPAddress objects as DiffSync IPAddress models."""
        for ipaddr in OrmIPAddress.objects.filter(interfaces__device__device_type__manufacturer__name__in=["Arista"]):
            try:
                self.get(self.namespace, ipaddr.parent.namespace.name)
            except ObjectNotFound:
                new_ns = self.namespace(
                    name=ipaddr.parent.namespace.name,
                    uuid=ipaddr.parent.namespace.id,
                )
                self.add(new_ns)
            try:
                self.get(self.prefix, {"prefix": str(ipaddr.parent.prefix), "namespace": ipaddr.parent.namespace.name})
            except ObjectNotFound:
                new_pf = self.prefix(
                    prefix=str(ipaddr.parent.prefix),
                    namespace=ipaddr.parent.namespace.name,
                    uuid=ipaddr.parent.id,
                )
                self.add(new_pf)
            new_ip = self.ipaddr(
                address=str(ipaddr.address),
                prefix=str(ipaddr.parent.prefix),
                namespace=ipaddr.parent.namespace.name,
                uuid=ipaddr.id,
            )
            try:
                self.add(new_ip)
            except ObjectAlreadyExists as err:
                self.job.logger.warning(f"Unable to load {ipaddr.address} as appears to be a duplicate. {err}")
            ip_to_intfs = IPAddressToInterface.objects.filter(ip_address=ipaddr)
            for mapping in ip_to_intfs:
                new_map = self.ipassignment(
                    address=str(ipaddr.address),
                    namespace=mapping.ip_address.parent.namespace.name,
                    device=mapping.interface.device.name,
                    interface=mapping.interface.name,
                    primary=len(mapping.ip_address.primary_ip4_for.all()) > 0
                    or len(mapping.ip_address.primary_ip6_for.all()) > 0,
                    uuid=mapping.id,
                )
                self.add(new_map)

    def sync_complete(self, source: DiffSync, *args, **kwargs):
        """Perform actions after sync is completed.

        Args:
            source (DiffSync): Source DiffSync DataSource adapter.
        """
        for grouping in (
            "ipaddresses",
            "prefixes",
            "namespaces",
            "interfaces",
            "devices",
        ):
            for nautobot_object in self.objects_to_delete[grouping]:
                try:
                    if self.job.debug:
                        self.job.logger.info(f"Deleting {nautobot_object}.")
                    nautobot_object.delete()
                except ProtectedError as err:
                    self.job.logger.warning(f"Deletion failed for protected object: {nautobot_object}. {err}")
            self.objects_to_delete[grouping] = []

        config: CloudVisionAppConfig = self.job.app_config  # type: ignore
        # if Controller is created we need to ensure all imported Devices have RelationshipAssociation to it.
        if config.create_controller:
            self.job.logger.info("Creating Relationships between CloudVision and connected Devices.")
            controller_relation = OrmRelationship.objects.get(label="Controller -> Device")
            device_ct = ContentType.objects.get_for_model(OrmDevice)
            cvp = OrmDevice.objects.get(name="CloudVision")
            loaded_devices = source.dict()["device"]
            for dev in loaded_devices:
                if dev != "CloudVision":
                    try:
                        device = OrmDevice.objects.get(name=dev)
                        relations = device.get_relationships()
                        if len(relations["destination"][controller_relation]) == 0:
                            new_assoc = OrmRelationshipAssociation(
                                relationship=controller_relation,
                                source_type=device_ct,
                                source=cvp,
                                destination_type=device_ct,
                                destination=device,
                            )
                            new_assoc.validated_save()
                    except OrmDevice.DoesNotExist:
                        self.job.logger.info(
                            f"Unable to find Device {dev['name']} to create Relationship to Controller."
                        )

    def load(self):
        """Load Nautobot models into DiffSync models."""
        self.load_devices()
        self.load_interfaces()
        self.load_ip_addresses()
