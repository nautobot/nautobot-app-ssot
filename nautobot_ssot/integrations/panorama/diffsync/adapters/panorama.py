"""Nautobot SSoT Panorama Adapter for Panorama SSoT plugin."""

from typing import Any

from diffsync import Adapter, DiffSyncModel
from diffsync.exceptions import ObjectAlreadyExists, ObjectNotFound
from nautobot.apps.jobs import Job
from nautobot.dcim.models import Controller
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from panos.network import (
    AggregateInterface,
    EthernetInterface,
    Layer2Subinterface,
    Layer3Subinterface,
    LoopbackInterface,
    TunnelInterface,
    VlanInterface,
)

from nautobot_ssot.integrations.panorama.diffsync.models.panorama import (
    PanoramaControllerManagedDeviceGroup,
    PanoramaDeviceToControllerManagedDeviceGroup,
    PanoramaDeviceType,
    PanoramaFirewall,
    PanoramaFirewallInterface,
    PanoramaIPAddressToInterface,
    PanoramaSoftwareVersion,
    PanoramaSoftwareVersionToDevice,
    PanoramaVdc,
    PanoramaVdcToControllerManagedDeviceGroup,
    PanoramaVirtualDeviceContextAssociation,
)
from nautobot_ssot.integrations.panorama.utils.panorama import Panorama
from nautobot_ssot.integrations.panorama.utils.panorama_adapter_utils import (
    load_firewall_to_diffsync,
    load_ipaddress_to_interface_to_diffsync,
    load_vdc_interface_to_diffsync,
)
from nautobot_ssot.models import Sync


class PanoSSoTPanoramaAdapter(Adapter):
    """DiffSync adapter for Panorama."""

    device_type = PanoramaDeviceType
    firewall = PanoramaFirewall
    firewall_interface = PanoramaFirewallInterface
    ip_address_to_interface = PanoramaIPAddressToInterface
    vdc = PanoramaVdc
    virtualdevicecontextassociation = PanoramaVirtualDeviceContextAssociation
    softwareversion = PanoramaSoftwareVersion
    softwareversiontodevice = PanoramaSoftwareVersionToDevice
    controllermanageddevicegroup = PanoramaControllerManagedDeviceGroup
    devicetocontrollermanageddevicegroup = PanoramaDeviceToControllerManagedDeviceGroup
    vdctocontrollermanageddevicegroup = PanoramaVdcToControllerManagedDeviceGroup

    top_level = [
        "device_type",
        "firewall",
        "firewall_interface",
        "vdc",
        "virtualdevicecontextassociation",
        "ip_address_to_interface",
        "softwareversion",
        "softwareversiontodevice",
        "controllermanageddevicegroup",
        "devicetocontrollermanageddevicegroup",
        "vdctocontrollermanageddevicegroup",
    ]

    def __init__(self, *args: Any, job: Job, sync: Sync, pan: Controller, **kwargs: Any) -> None:
        """Initialize the Panorama adapter.

        Args:
            *args: Variable length argument list to pass to parent class.
            job: Nautobot job instance for logging and tracking.
            sync: Sync instance that coordinates the synchronization.
            pan: Controller instance representing the Panorama device to connect to.
            **kwargs: Arbitrary keyword arguments to pass to parent class.

        Returns:
            None
        Note:
            This establishes a connection to the Panorama device using credentials
            from the associated external integration and secrets group.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.pan = pan
        self.job.logger.info("Using selected Panorama for connection.", extra={"object": pan})
        self.pano = Panorama(
            url=pan.external_integration.remote_url.split("https://")[-1],
            username=pan.external_integration.secrets_group.get_secret_value(
                access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
                secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
            ),
            password=pan.external_integration.secrets_group.get_secret_value(
                access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
                secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
            ),
            verify=pan.external_integration.verify_ssl,
            job=self.job,
        )
        self._backend = "Panorama"
        self._loaded_apps = []

    def get_or_add(self, obj: "DiffSyncModel") -> "DiffSyncModel":
        """Ensures a model is added.

        Args:
            obj (DiffSyncModel): Instance of model

        Returns:
            DiffSyncModel: Instance of model that has been added
        """
        model = obj.get_type()
        ids = obj.get_unique_id()
        try:
            return self.store.get(model=model, identifier=ids)
        except ObjectNotFound:
            self.add(obj=obj)
            return obj

    def load(self):
        """Load data from Panorama into DiffSync models."""
        self.job.logger.info(f"Caching Firewalls from {self._backend}", extra={"object": self.pan})
        self.pano.firewall.retrieve_firewalls()
        if self.job.debug:
            self.job.logger.debug(f"Cached Firewalls: {len(self.pano.firewall.firewalls)}")
        self.job.logger.info(f"Caching Vsys from {self._backend}", extra={"object": self.pan})
        self.pano.firewall.retrieve_vsys()
        self.job.logger.info(f"Loading objects from {self._backend} via cache", extra={"object": self.pan})
        self.load_controllermanageddevicegroup()
        self.load_cached_objects()

    def load_controllermanageddevicegroup(self):
        """Load ControllerManagedDeviceGroup hierarchy to the DiffSync store."""
        controller_name = self.job.panorama_controller.name

        # Root: "Panorama Devices" container
        try:
            self.add(
                self.controllermanageddevicegroup(
                    name=f"{controller_name} - Panorama Devices",
                    controller__name=controller_name,
                    parent__name=None,
                )
            )
        except Exception as err:
            self.job.logger.error(f"Failed to load root CMDG, {err}")

        # "shared" default device group (child of root)
        try:
            self.add(
                self.controllermanageddevicegroup(
                    name=f"{controller_name} - shared",
                    controller__name=controller_name,
                    parent__name=f"{controller_name} - Panorama Devices",
                )
            )
        except Exception as err:
            self.job.logger.error(f"Failed to load 'shared' CMDG, {err}")

        # All Panorama device groups
        for group_name in self.pano.device_group.device_groups.keys():
            parent_group_name = self.pano.device_group.get_parent(group_name)
            if not parent_group_name:
                parent_cmdg_name = f"{controller_name} - shared"
            else:
                parent_cmdg_name = f"{controller_name} - {parent_group_name}"
            try:
                self.add(
                    self.controllermanageddevicegroup(
                        name=f"{controller_name} - {group_name}",
                        controller__name=controller_name,
                        parent__name=parent_cmdg_name,
                    )
                )
            except Exception as err:
                self.job.logger.error(f"Failed to load CMDG for {group_name}, {err}")

    def load_cached_objects(self):
        """Load objects from cache."""
        self.job.loaded_panorama_devices = set()

        # Add Firewalls to the Diffsync store
        for firewall in self.pano.firewall.firewalls:
            try:
                firewall_name = firewall["name"]
                firewall_obj = firewall["value"]
            except Exception as err:
                self.job.logger.error(f"Failed to load cached firewall data for {firewall}, {err}")
                continue
            try:
                firewall_system_info = firewall_obj.show_system_info()
            except Exception as err:
                self.job.logger.error(
                    f"Failed to load system info for {firewall_name}, This device will not be synced. {err}"
                )
                continue
            try:
                load_firewall_to_diffsync(
                    adapter=self, firewall=firewall_obj, firewall_system_info=firewall_system_info
                )
            except Exception as err:
                self.job.logger.error(
                    f"Failed to load data for Device {firewall_name} to the diffsync store, "
                    f"this device will not be synced. {err}"
                )
                continue
            try:
                # Add a firewall directly to a device group only if its not a multi-vsys device
                multi_vsys = firewall_system_info["system"]["multi-vsys"]
                if multi_vsys == "off":
                    devicetocontrollermanageddevicegroup = self.devicetocontrollermanageddevicegroup(
                        device__serial=firewall_obj.serial,
                        controllermanageddevicegroup__name=f"{self.job.panorama_controller.name} - {firewall.get('location')}",
                    )
                    self.add(devicetocontrollermanageddevicegroup)
            except Exception as err:
                self.job.logger.error(
                    f"Failed to load device to controller managed device group for {firewall_name}, {err}"
                )
                pass

        # Add Vsys to the Diffsync store
        for serial in self.job.loaded_panorama_devices:
            try:
                vsys_data = self.pano.firewall.vsys[serial]
            except KeyError:
                self.job.logger.error(f"Failed to load cached vsys data for {serial}, this device will not be synced.")
                continue
            if not vsys_data:  # Do not continue if no vsys data was actually cached
                continue
            for vsys in vsys_data.values():
                if vsys["cached_successfully"]:
                    if self.job.debug:
                        self.job.logger.debug(
                            f"Loading cached data for Vsys: {vsys.get('name')} for firewall: {vsys.get('firewall_name')}"
                        )
                    try:
                        vdctocontrollermanageddevicegroup = self.vdctocontrollermanageddevicegroup(
                            controller_managed_device_group__name=f"{self.job.panorama_controller.name} - {vsys['devicegroup']}",
                            virtual_device_context__device__serial=vsys["firewall_obj"].serial,
                            virtual_device_context__name=vsys["vsys_obj"].name,
                        )
                        self.add(vdctocontrollermanageddevicegroup)
                    except Exception as err:
                        self.job.logger.error(
                            f"Failed to load VDC to CMDG for {vsys.get('firewall_name')} - {vsys.get('name')}, {err}"
                        )
                        continue
                    self.get_or_add(
                        self.vdc(
                            name=vsys["vsys_obj"].name,
                            parent=vsys["firewall_obj"].serial,
                        )
                    )
                    # Load interface data
                    interfaces = vsys["interfaces"]
                    interface_classes = (
                        AggregateInterface,
                        EthernetInterface,
                        Layer3Subinterface,
                        Layer2Subinterface,
                        LoopbackInterface,
                        TunnelInterface,
                        VlanInterface,
                    )
                    for interface in interfaces:
                        # Only load valid interface classes
                        if not isinstance(interface, interface_classes):
                            if self.job.debug:
                                self.job.logger.debug(
                                    f"Skipping interface {interface} for {vsys.get('firewall_name')}, "
                                    "it is not a valid interface class."
                                )
                            continue
                        interface_data = interface.about()
                        load_vdc_interface_to_diffsync(
                            adapter=self,
                            interface_obj=interface,
                            interface_data=interface_data,
                            vsys=vsys,
                        )
                        if interface_data.get("ip"):
                            load_ipaddress_to_interface_to_diffsync(
                                adapter=self,
                                interface_obj=interface,
                                interface_data=interface_data,
                                vsys=vsys,
                            )
                        try:
                            virtualdevicecontextassociation = self.virtualdevicecontextassociation(
                                virtual_device_context__device__serial=vsys["firewall_obj"].serial,
                                virtual_device_context__name=vsys["name"],
                                interface__device__serial=vsys["firewall_obj"].serial,
                                interface__name=interface.name,
                            )
                            self.add(virtualdevicecontextassociation)
                        except ObjectAlreadyExists:
                            pass
                        except Exception as err:
                            self.job.logger.error(
                                f"Failed to load interface to Vsys for {vsys.get('firewall_name')}, {err}"
                            )
                            continue
                        # Load child interface data, if any.
                        if interface.children:
                            for child in interface.children:
                                # Only load valid interface classes
                                if not isinstance(child, interface_classes):
                                    if self.job.debug:
                                        self.job.logger.debug(
                                            f"Skipping interface child {child} for {vsys.get('firewall_name')}, "
                                            "it is not a valid interface class."
                                        )
                                    continue
                                interface_data = child.about()
                                load_vdc_interface_to_diffsync(
                                    adapter=self,
                                    interface_obj=child,
                                    interface_data=interface_data,
                                    vsys=vsys,
                                )
                                if interface_data.get("ip"):
                                    load_ipaddress_to_interface_to_diffsync(
                                        adapter=self,
                                        interface_obj=child,
                                        interface_data=interface_data,
                                        vsys=vsys,
                                    )
                                try:
                                    virtualdevicecontextassociation = self.virtualdevicecontextassociation(
                                        virtual_device_context__device__serial=vsys["firewall_obj"].serial,
                                        virtual_device_context__name=vsys["name"],
                                        interface__device__serial=vsys["firewall_obj"].serial,
                                        interface__name=child.name,
                                    )
                                    self.add(virtualdevicecontextassociation)
                                except ObjectAlreadyExists:
                                    pass
                                except Exception as err:
                                    self.job.logger.error(
                                        f"Failed to load interface to Vsys for {vsys.get('firewall_name')}, {err}"
                                    )
                                    continue
