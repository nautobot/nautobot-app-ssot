"""Utility functions for working with Nautobot."""

import re
from ipaddress import ip_network

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from nautobot.apps.choices import IPAddressTypeChoices, PrefixTypeChoices
from nautobot.dcim.models import (
    ControllerManagedDeviceGroup,
    Device,
    DeviceType,
    Interface,
    Manufacturer,
    Platform,
    SoftwareVersion,
    VirtualDeviceContext,
)
from nautobot.extras.models import Role, Status
from nautobot.ipam.models import IPAddress, IPAddressToInterface, Namespace, Prefix

app_settings = settings.PLUGINS_CONFIG.get("nautobot_ssot")


class Nautobot:  # pylint: disable=too-many-public-methods
    """Helper methods for interacting with Django ORM."""

    def create_vdc(self, adapter, ids, attrs):
        """Creates Vdc."""
        if adapter.job.debug:
            adapter.job.logger.debug(f"Creating VirtualDeviceContext (vsys) with ids: {ids} with attrs: {attrs}")
        try:
            device = Device.objects.get(serial=ids["parent"])
            sysid = int(re.sub("[^0-9]", "", ids["name"]))
            vdc = VirtualDeviceContext(
                name=ids["name"], device=device, identifier=sysid, status=adapter.job.default_device_status
            )
            vdc.validated_save()
            return vdc
        except Exception as err:
            adapter.job.logger.error(f"Unable to create Vdc: {ids}, {err.args}")
            return None

    def update_vdc(self, adapter, ids, attrs):
        """Updates Vdc."""
        ...

    def create_firewall(self, adapter, ids, attrs):
        """Creates a Firewall."""
        if adapter.job.debug:
            adapter.job.logger.debug(f"Creating Firewall device with ids: {ids} and attrs: {attrs}")
        try:
            device = Device.objects.get(name=attrs["name"], location=adapter.job.panorama_controller.location)
            if device.serial != ids["serial"]:
                # If the device already exists but the serial number differs, log a warning
                adapter.job.logger.warning(
                    f"Firewall named {attrs['name']} already exists, but the serial number differs. "
                    f"Existing device serial: {device.serial}, Incoming serial from Panorama: {ids['serial']}",
                    extra={"object": device},
                )
                return device
        except ObjectDoesNotExist:
            pass
        except Exception as err:
            adapter.job.logger.error(f"Error checking for existing Nautobot Firewall {ids} {attrs}, {err}")
            return None

        # TODO: Disable the warning above and re-enable this update option.
        # Considerations: what should happen if there are many devices in Panorama with the same name?!
        # try:
        #     device = Device.objects.get(name=attrs["name"], location=adapter.job.panorama_controller.location)
        #     adapter.job.logger.warning(f"Firewall named {attrs['name']} already exists. This device will be updated.")
        #     device.serial = ids["serial"]
        #     device.role = Role.objects.get(name="Panorama")
        #     device.device_type = DeviceType.objects.get(model=attrs["model"])
        #     device.platform = Platform.objects.get(name="paloalto_panos")
        #     device.validated_save()
        #     return device
        # except ObjectDoesNotExist:
        #     pass
        # except Exception as err:
        #     adapter.job.logger.error(f"Unable to update Firewall {ids} {attrs}, {err}")
        #     return None
        try:
            manufacturer_name = app_settings.get("panorama_firewall_manufacturer_name", "Palo Alto")
            manufacturer, _ = Manufacturer.objects.get_or_create(name=manufacturer_name)
            platform_name = app_settings.get("panorama_firewall_platform_name", "paloalto_panos")
            platform, _ = Platform.objects.get_or_create(name=platform_name, manufacturer=manufacturer)
            device = Device(
                status=adapter.job.default_device_status,
                serial=ids["serial"],
                name=attrs["name"],
                role=Role.objects.get(name="FW-Other"),
                device_type=DeviceType.objects.get(model=attrs["model"]),
                platform=platform,
                location=adapter.job.panorama_controller.location,
            )
            device.validated_save()
            if adapter.job.debug:
                adapter.job.logger.debug(f"Created Firewall {ids}")
            # add the IP address to a map that will be used in sync_complete()
            adapter.firewall_primary_ip_map[ids["serial"]] = attrs.get("management_ip").split("/")[0]
        except Exception as err:
            adapter.job.logger.error(f"Unable to create Firewall {ids} {attrs}, {err}")
            return None
        return device

    def update_firewall(self, adapter, serial, attrs):
        """Updates a Firewall."""
        if adapter.job.debug:
            adapter.job.logger.debug(f"Updating Firewall: {serial} with attrs: {attrs}")
        try:
            device = Device.objects.get(serial=serial)
            if "name" in attrs:
                device.name = attrs["name"]
                device.validated_save()
            if "model" in attrs:
                if attrs["model"]:
                    device.device_type = DeviceType.objects.get(model=attrs["model"])
                    device.validated_save()
            if attrs.get("management_ip"):  # add the IP address to a map that will be used in sync_complete()
                adapter.firewall_primary_ip_map[serial] = attrs.get("management_ip").split("/")[0]
            return device
        except Exception as err:
            adapter.job.logger.error(f"Unable to update Firewall {serial}, {err}")
            return None

    def create_device_type(self, adapter, ids, attrs):
        """Creates a DeviceType."""
        if adapter.job.debug:
            adapter.job.logger.debug(f"Creating DeviceType with ids: {ids} with attrs: {attrs}")
        try:
            manufacturer_name = app_settings.get("panorama_firewall_manufacturer_name", "Palo Alto")
            manufacturer, _ = Manufacturer.objects.get_or_create(name=manufacturer_name)
            device_type = DeviceType(
                model=ids["model"],
                part_number=attrs["part_number"],
                manufacturer=manufacturer,
            )
            device_type.validated_save()
            return device_type
        except Exception as err:
            adapter.job.logger.error(f"Unable to create DeviceType: {ids}, {err}")
            return None

    def update_device_type(self, adapter, identifiers, attrs):  # pylint: disable=inconsistent-return-statements
        """Updates a DeviceType."""
        if adapter.job.debug:
            adapter.job.logger.debug(f"Updating DeviceType with attrs: {attrs}")
        if "part_number" in attrs.keys():
            try:
                device_type = DeviceType.objects.get(**identifiers)
                device_type.part_number = attrs["part_number"]
                device_type.validated_save()
                return device_type
            except Exception as err:
                adapter.job.logger.error(f"Unable to update DeviceType: {identifiers}, {attrs}, {err}")
                return None

    def _get_or_create_prefix(self, adapter, address):
        try:
            try:
                network_with_prefixlen = str(ip_network(address, strict=False))
                prefix = Prefix.objects.get(
                    network=network_with_prefixlen.split("/", maxsplit=1)[0],
                    prefix_length=network_with_prefixlen.split("/")[1],
                    namespace=Namespace.objects.get(name="Global"),
                )
                return prefix
            except ObjectDoesNotExist:
                # Create the Prefix if it does not exist
                adapter.job.logger.info(f"Creating Prefix {network_with_prefixlen}")
                prefix = Prefix(
                    network=network_with_prefixlen.split("/")[0],
                    prefix_length=network_with_prefixlen.split("/")[1],
                    namespace=Namespace.objects.get(name="Global"),
                    status=Status.objects.get(name="Active"),
                    type=PrefixTypeChoices.TYPE_NETWORK,
                )
                prefix.validated_save()
                return prefix
        except Exception as err:
            adapter.job.logger.error(f"Error getting or creating Prefix for address {address}, {err}")
            return None

    def _get_or_create_ip_address(self, adapter, address, status):
        """
        Given an address, attempt to get or create a Nautobot IPAddress object.

        If the IPAddress must be created, also create a valid parent Prefix if required.
        """
        try:
            # Attempt to get an existing IP Address, update the mask length if necessary
            addr = IPAddress.objects.get(
                host=str(address).split("/", maxsplit=1)[0], parent__namespace=Namespace.objects.get(name="Global")
            )
            # If the existing IP Address has a different mask length, update it
            if str(addr.mask_length) != str(address).split("/")[1]:
                # Verify the necessary Prefix exists, create if necessary
                prefix = self._get_or_create_prefix(adapter, address)
                if not prefix:  # A valid prefix must exist to continue
                    return (None, None)
                adapter.job.logger.info(
                    f"Updating IP Address {addr} mask length from {addr.mask_length} to {str(address).split('/')[1]}"
                )
                addr.mask_length = str(address).split("/")[1]
                addr.validated_save()
            return (addr, "ip_address")
        # Create an IP Address if one does not exist
        except ObjectDoesNotExist:
            prefix = self._get_or_create_prefix(adapter, address)
            if not prefix:  # A valid prefix must exist to continue
                return (None, None)
            try:
                adapter.job.logger.info(f"Creating IPAddress {address}")
                addr = IPAddress(address=address, status=status, type=IPAddressTypeChoices.TYPE_HOST)
                addr.validated_save()
                return (addr, "ip_address")
            except Exception as err:
                adapter.job.logger.error(f"Unable to create IPAddress: {address}, {err}")
                return (None, None)
        except Exception as err:
            adapter.job.logger.error(f"Error getting or creating IPAddress for address {address}, {err}")

        return (None, None)

    def create_ip_address_to_interface(self, adapter, ids):  # pylint: disable=inconsistent-return-statements
        """Creates an IPAddressToInterface."""
        ip_address_assignment = None
        try:
            # Get or create the IP Address
            address = f"{ids['ip_address__host']}/{ids['ip_address__mask_length']}"
            ip_address_obj, _ = self._get_or_create_ip_address(
                adapter=adapter, address=address, status=Status.objects.get(name="Active")
            )
            if not ip_address_obj:
                return None

            # Assign the IP Address to the Interface
            interface = Interface.objects.get(
                name=ids["interface__name"], device__serial=ids["interface__device__serial"]
            )
            try:
                ip_address_assignment = IPAddressToInterface.objects.get(interface=interface, ip_address=ip_address_obj)
                adapter.job.logger.info(
                    f"IPAddress {ip_address_obj} already assigned to {interface} on {interface.device}"
                )
            except ObjectDoesNotExist:
                ip_address_assignment = IPAddressToInterface(interface=interface, ip_address=ip_address_obj)
                if adapter.job.debug:
                    adapter.job.logger.debug(f"Assigning {ip_address_obj} to {interface} on {interface.device}")
                ip_address_assignment.validated_save()

            # add the IP address to a map that will be used in sync_complete()
            # the management interface is always named "mgmt" in Palo Alto devices
            # it is assumed that the management IP will always be assigned to this interface
            if ids.get("interface__name") == "mgmt":
                try:
                    if adapter.job.debug:
                        adapter.job.logger.debug(
                            f"Adding management IP {ids['ip_address__host']} to firewall_primary_ip_map for device "
                            f"{interface.device.name}"
                        )
                    adapter.firewall_primary_ip_map[interface.device.serial] = ids["ip_address__host"]
                except Exception as err:
                    adapter.job.logger.error(
                        f"Unable to add management IP {ids['ip_address__host']} to firewall_primary_ip_map for device "
                        f"{interface.device.name}. This may result in the synced device not being assigned a Primary IP. {err}"
                    )
            return ip_address_assignment
        except Exception as err:
            adapter.job.logger.error(f"Unable to assign IPAddress: {ids}, {err}, {err.args}")
            return None

    def delete_ip_address_to_interface(self, adapter, ip_address_to_interface):
        """Deletes an IPAddressToInterface."""
        if adapter.job.debug:
            adapter.job.logger.debug(f"Deleting IPAddressToInterface {ip_address_to_interface.get_identifiers()}")
        try:
            ip_address_assignment = IPAddressToInterface.objects.get(**ip_address_to_interface.get_identifiers())
            ip_address_assignment.delete()
        # If the IPAddressToInterface does not exist, the interface was probably deleted during the sync. Okay to pass.
        except ObjectDoesNotExist:
            pass
        except Exception as err:
            adapter.job.logger.error(
                f"Unable to delete IPAddressToInterface {ip_address_to_interface.get_identifiers()}, {err}"
            )

    def create_software_version_to_device(self, adapter, ids, attrs):
        """Assigns a software version to a device."""
        if adapter.job.debug:
            adapter.job.logger.debug(f"Assigning software version to device: {ids} and attrs: {attrs}")
        try:
            software_version = SoftwareVersion.objects.get(version=ids["version"], platform__name=ids["platform__name"])
            device = Device.objects.get(serial=ids["device__serial"])
            device.software_version = software_version
            device.validated_save()
            return device
        except Exception as err:
            adapter.job.logger.error(f"Unable to assign software version to device: {ids}, {err}")
            return None

    def delete_software_version_to_device(self, adapter, software_version_to_device):
        """Deletes a SoftwareVersionToDevice."""
        # An empty value here means the device did not have software assigned when the data was cached, so a delete is not required.
        if not software_version_to_device.version:
            return
        if adapter.job.debug:
            adapter.job.logger.debug(f"Removing software from device {software_version_to_device.get_identifiers()}")
        try:
            device = Device.objects.get(serial=software_version_to_device.device__serial)
            software_version = SoftwareVersion.objects.get(
                version=software_version_to_device.version, platform__name=software_version_to_device.platform__name
            )
            if device.software_version == software_version:
                device.software_version = None
                device.validated_save()
        except Exception as err:
            adapter.job.logger.error(
                f"Unable to remove software from device {software_version_to_device.get_identifiers()}, {err}"
            )

    def create_device_to_controller_managed_device_group(self, adapter, ids, attrs):
        """Assigns a device to a controller managed device group."""
        if adapter.job.debug:
            adapter.job.logger.debug(f"Assigning device to controller managed device group: {ids} and attrs: {attrs}")
        try:
            device_group = ControllerManagedDeviceGroup.objects.get(name=ids["controllermanageddevicegroup__name"])
            device = Device.objects.get(serial=ids["device__serial"])
            device_group.devices.add(device)
            return device
        except Exception as err:
            adapter.job.logger.error(f"Unable to assign device to controller managed device group: {ids}, {err}")
            return None

    def delete_device_to_controller_managed_device_group(self, adapter, device_to_controller_managed_device_group):
        """Removes a device from a controller managed device group."""
        if adapter.job.debug:
            adapter.job.logger.debug(
                f"Removing device from controller managed device group "
                f"{device_to_controller_managed_device_group.get_identifiers()}"
            )
        try:
            device_group = ControllerManagedDeviceGroup.objects.get(
                name=device_to_controller_managed_device_group.controllermanageddevicegroup__name
            )
            device = Device.objects.get(serial=device_to_controller_managed_device_group.device__serial)
            device_group.devices.remove(device)
        except Exception as err:
            adapter.job.logger.error(
                "Unable to remove device from controller managed device group "
                f"{device_to_controller_managed_device_group.get_identifiers()}, {err}"
            )
