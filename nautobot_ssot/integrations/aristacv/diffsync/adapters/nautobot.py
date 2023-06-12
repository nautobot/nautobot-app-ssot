"""DiffSync adapter for Nautobot."""
from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import Device as OrmDevice
from nautobot.dcim.models import Interface as OrmInterface
from nautobot.extras.models import Relationship as OrmRelationship
from nautobot.extras.models import RelationshipAssociation as OrmRelationshipAssociation
from nautobot.ipam.models import IPAddress as OrmIPAddress
from diffsync import DiffSync
from diffsync.exceptions import ObjectNotFound, ObjectAlreadyExists

from nautobot_ssot.integrations.aristacv.constant import APP_SETTINGS
from nautobot_ssot.integrations.aristacv.diffsync.models.nautobot import (
    NautobotDevice,
    NautobotCustomField,
    NautobotIPAddress,
    NautobotPort,
)
from nautobot_ssot.integrations.aristacv.utils import nautobot


class NautobotAdapter(DiffSync):
    """DiffSync adapter implementation for Nautobot custom fields."""

    device = NautobotDevice
    port = NautobotPort
    ipaddr = NautobotIPAddress
    cf = NautobotCustomField

    top_level = ["device", "ipaddr", "cf"]

    def __init__(self, *args, job=None, **kwargs):
        """Initialize the Nautobot DiffSync adapter."""
        super().__init__(*args, **kwargs)
        self.job = job

    def load_devices(self):
        """Add Nautobot Device objects as DiffSync Device models."""
        for dev in OrmDevice.objects.filter(device_type__manufacturer__slug="arista"):
            try:
                new_device = self.device(
                    name=dev.name,
                    device_model=dev.device_type.model,
                    serial=dev.serial,
                    status=dev.status.slug,
                    version=nautobot.get_device_version(dev),
                    uuid=dev.id,
                )
                self.add(new_device)
            except ObjectAlreadyExists as err:
                self.job.log_warning(message=f"Unable to load {dev.name} as it appears to be a duplicate. {err}")
                continue

            self.load_custom_fields(dev=dev)

    def load_custom_fields(self, dev: OrmDevice):
        """Load device custom field data from Nautobot and populate DiffSync models."""
        for cf_name, cf_value in dev.custom_field_data.items():
            if cf_name.startswith("arista_"):
                try:
                    new_cf = self.cf(name=cf_name, value=cf_value if cf_value is not None else "", device_name=dev.name)
                    self.add(new_cf)
                except AttributeError as err:
                    self.job.log_warning(message=f"Unable to load {cf_name}. {err}")
                    continue

    def load_interfaces(self):
        """Add Nautobot Interface objects as DiffSync Port models."""
        for intf in OrmInterface.objects.filter(device__device_type__manufacturer__slug="arista"):
            new_port = self.port(
                name=intf.name,
                device=intf.device.name,
                description=intf.description,
                mac_addr=str(intf.mac_address).lower() if intf.mac_address else "",
                enabled=intf.enabled,
                mode=intf.mode,
                mtu=intf.mtu,
                port_type=intf.type,
                status=intf.status.slug,
                uuid=intf.id,
            )
            self.add(new_port)
            try:
                dev = self.get(self.device, intf.device.name)
                dev.add_child(new_port)
            except ObjectNotFound as err:
                self.job.log_warning(
                    message=f"Unable to find Device {intf.device.name} in diff to assign to port {intf.name}. {err}"
                )

    def load_ip_addresses(self):
        """Add Nautobot IPAddress objects as DiffSync IPAddress models."""
        for ipaddr in OrmIPAddress.objects.filter(interface__device__device_type__manufacturer__slug="arista"):
            new_ip = self.ipaddr(
                address=str(ipaddr.address),
                interface=ipaddr.assigned_object.name,
                device=ipaddr.assigned_object.device.name,
                uuid=ipaddr.id,
            )
            try:
                self.add(new_ip)
            except ObjectAlreadyExists as err:
                self.job.log_warning(message=f"Unable to load {ipaddr.address} as appears to be a duplicate. {err}")

    def sync_complete(self, source: DiffSync, *args, **kwargs):
        """Perform actions after sync is completed.

        Args:
            source (DiffSync): Source DiffSync DataSource adapter.
        """
        # if Controller is created we need to ensure all imported Devices have RelationshipAssociation to it.
        if APP_SETTINGS.get("create_controller"):
            self.job.log_info(message="Creating Relationships between CloudVision and connected Devices.")
            controller_relation = OrmRelationship.objects.get(name="Controller -> Device")
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
                        self.job.log_info(
                            message=f"Unable to find Device {dev['name']} to create Relationship to Controller."
                        )

    def load(self):
        """Load Nautobot models into DiffSync models."""
        self.load_devices()
        self.load_interfaces()
        self.load_ip_addresses()
