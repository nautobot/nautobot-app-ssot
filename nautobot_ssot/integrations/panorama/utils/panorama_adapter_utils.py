"""Utility functions for the Panorama adapter."""

from ipaddress import ip_interface

from diffsync.exceptions import ObjectAlreadyExists
from django.conf import settings
from nautobot.dcim.choices import InterfaceTypeChoices

app_settings = settings.PLUGINS_CONFIG.get("nautobot_ssot")


def load_firewall_to_diffsync(adapter, firewall, firewall_system_info):  # pylint: disable=too-many-branches, too-many-statements, too-many-locals
    """
    Load a PAN-OS firewall device and its related components into the DiffSync adapter.

    This function takes a firewall object and its system information, then creates and adds
    the following objects to the DiffSync adapter:
    - Device type based on the firewall model
    - Firewall device with management information
    - Management interface for the firewall
    - IP address assignment for the management interface
    - Software version information
    - Association between the software version and the device
    - Association between the device and its controller managed device group
    Args:
        adapter: The DiffSync adapter instance where objects will be stored
        firewall: The firewall object containing device information
        firewall_system_info: Dictionary containing system information for the firewall
    Raises:
        ObjectAlreadyExists: When an object being added already exists (typically caught and ignored)
        Exception: When any other error occurs during object creation or addition to DiffSync
    Notes:
        - The function handles ObjectAlreadyExists exceptions for certain objects
        - Debug logging is available when adapter.job.debug is True
        - All other exceptions are logged and re-raised
    """
    if adapter.job.debug:
        adapter.job.logger.debug(f"Loading {firewall} to Diffsync")
    # Add DeviceType to Diffsync store
    try:
        manufacturer_name = app_settings.get("panorama_firewall_manufacturer_name", "Palo Alto")
        model = firewall_system_info["system"]["model"]
        device_type = adapter.device_type(
            model=model,
            part_number=model,
            manufacturer__name=manufacturer_name,
        )
        adapter.add(device_type)
    except ObjectAlreadyExists:
        pass
    except Exception as err:
        adapter.job.logger.error(f"Failed to load device type for {firewall}, {err}")
        raise err

    # Add Firewall to Diffsync store
    management_interface_name, management_ip = adapter.pano.firewall.get_management_interface_name_and_ip(firewall)
    if adapter.job.debug:
        adapter.job.logger.debug(
            f"Management IP {management_ip} assgined to interface {management_interface_name} on {firewall}"
        )
    try:
        diffsync_firewall = adapter.firewall(
            name=adapter.pano.firewall.get_hostname(firewall),  # TODO: Can we just use system_info for this?
            serial=firewall.serial,
            model=model,
            management_ip=management_ip,
            management_interface_name=management_interface_name,
        )
        adapter.add(diffsync_firewall)
    # Multiple Vsys firewalls are all cached as individual firewalls. We only want to
    # load the first instance as the firewall vsys data is loaded separately.
    except ObjectAlreadyExists:
        pass
    except Exception as err:
        adapter.job.logger.error(f"Failed to load firewall to Diffsync {firewall}, {err}")
        raise err
    # Explicitly load the mgmt interface and IP for the firewall
    # These values do not come from a Vsys
    try:
        firewall_interface = adapter.firewall_interface(
            name=management_interface_name,
            device__serial=firewall.serial,
            status__name="Active",
            type=InterfaceTypeChoices.TYPE_OTHER,
            description="Management Interface",
        )
        adapter.add(firewall_interface)
    except ObjectAlreadyExists:
        # This is expected if the interface already exists
        pass
    except Exception as err:
        adapter.job.logger.error(f"Failed to load interface for {firewall}, {err}")
        raise err
    try:
        ip_address_to_interface = adapter.ip_address_to_interface(
            interface__device__serial=firewall.serial,
            interface__name=management_interface_name,
            ip_address__host=management_ip.split("/")[0],
            ip_address__mask_length=management_ip.split("/")[1],
        )
        adapter.add(ip_address_to_interface)
    except ObjectAlreadyExists:
        pass
    except Exception as err:
        adapter.job.logger.error(f"Failed to load ip address to interface {ip_address_to_interface}, {err}")
        raise err

    # Add the software version to the Diffsync store
    try:
        platform_name = app_settings.get("panorama_firewall_platform_name", "paloalto_panos")
        softwareversion = adapter.softwareversion(
            platform__name=platform_name,
            version=firewall_system_info["system"]["sw-version"],
            status__name="Active",
        )
        adapter.add(softwareversion)
    except ObjectAlreadyExists:
        # This is expected if the software version already exists
        pass
    except Exception as err:
        adapter.job.logger.error(f"Failed to load software version for {firewall}, {err}")
        raise err

    # Add the software version to device association to the Diffsync store
    try:
        platform_name = app_settings.get("panorama_firewall_platform_name", "paloalto_panos")
        softwareversiontodevice = adapter.softwareversiontodevice(
            device__serial=firewall.serial,
            platform__name=platform_name,
            version=firewall_system_info["system"]["sw-version"],
        )
        adapter.add(softwareversiontodevice)
    except ObjectAlreadyExists:
        # Each Vsys is loaded as its own separate firewall, so its possible this will already exist
        pass
    except Exception as err:
        adapter.job.logger.error(f"Failed to load software version to device for {firewall}, {err}")
        raise err

    # Add the device to controller managed device group association to the Diffsync store
    try:
        devicetocontrollermanageddevicegroup = adapter.devicetocontrollermanageddevicegroup(
            device__serial=firewall.serial,
            controllermanageddevicegroup__name=f"{adapter.job.panorama_controller.name} - Panorama Devices",
        )
        adapter.add(devicetocontrollermanageddevicegroup)
    except ObjectAlreadyExists:
        # Each Vsys is loaded as its own separate firewall, so its possible this will already exist
        pass
    except Exception as err:
        adapter.job.logger.error(f"Failed to load device to controller managed device group for {firewall}, {err}")
        raise err

    try:
        # Only devices that were successfully retrieved from Panorama should be synced to Nautobot
        adapter.job.loaded_panorama_devices.add(firewall.serial)
    except Exception as err:
        adapter.job.logger.error(f"Failed to add firewall to list of successfully cached firewalls {firewall}, {err}")
        raise err


def load_vsys_interface_to_diffsync(adapter, interface_obj, interface_data, vsys):
    """
    Load a virtual system interface into the DiffSync adapter.

    This function creates a firewall interface object from Panorama interface data
    and adds it to the DiffSync adapter. It handles duplicate objects gracefully
    and logs errors for debugging purposes.

    Args:
        adapter: The DiffSync adapter instance to add the interface to
        interface_obj: The original interface object from Panorama
        interface_data (dict): Dictionary containing interface configuration data
            with keys 'name' and 'comment'
        vsys (dict): Virtual system dictionary containing 'firewall_obj' with
            serial number and 'firewall_name' for error reporting
    Raises:
        Exception: Re-raises any exception that occurs during interface creation
            or addition to the adapter, after logging the error
    Note:
        ObjectAlreadyExists exceptions are silently ignored to handle duplicate
        interface entries gracefully.
    """
    try:
        firewall_interface = adapter.firewall_interface(
            name=interface_data["name"],
            device__serial=vsys["firewall_obj"].serial,
            status__name="Active",
            type=InterfaceTypeChoices.TYPE_OTHER,
            description=interface_data["comment"] if interface_data.get("comment") else "",  # TODO: refactor
        )
        adapter.add(firewall_interface)
    except ObjectAlreadyExists:
        if adapter.job.debug:
            adapter.job.logger.debug(
                f"Interface {interface_data['name']} for {vsys.get('firewall_name')} already loaded to diffsync, skipping."
            )
    except Exception as err:
        adapter.job.logger.error(f"Failed to load interface {interface_obj} for {vsys.get('firewall_name')}, {err}")


def load_ipaddress_to_interface_to_diffsync(adapter, interface_obj, interface_data, vsys):
    """
    Load IP addresses associated with an interface into the DiffSync adapter.

    Processes IP addresses from interface data and creates ip_address_to_interface
    objects in the DiffSync adapter. Handles both CIDR notation and host addresses
    without subnet masks (defaulting to /32).

    Args:
        adapter: The DiffSync adapter instance to add objects to
        interface_obj: The interface object being processed
        interface_data (dict): Dictionary containing interface information including 'ip' and 'name' keys
        vsys (dict): Virtual system dictionary containing 'firewall_obj' and 'firewall_name' keys
    Raises:
        Logs errors for failed interface loading operations while continuing processing
    Note:
        - Silently ignores ObjectAlreadyExists exceptions to handle duplicates
        - Defaults to /32 subnet mask for IP addresses without CIDR notation
        - Uses firewall serial number and interface name for object identification
    """
    for ip_addr in interface_data["ip"]:
        try:
            ip_addr_split = ip_addr.split("/")
            ip_interface(ip_addr_split[0])
            ip_address_to_interface = adapter.ip_address_to_interface(
                interface__device__serial=vsys["firewall_obj"].serial,
                interface__name=interface_data["name"],
                ip_address__host=ip_addr_split[0],
                ip_address__mask_length=(ip_addr_split[1] if len(ip_addr_split) == 2 else "32"),
            )
            adapter.add(ip_address_to_interface)
        except ValueError:
            if adapter.job.debug:
                adapter.job.logger.debug(
                    f"IP address {ip_addr} for interface {interface_data['name']} "
                    f"on {vsys.get('firewall_name')} is not a valid IPAddress, skipping."
                )
            continue
        except ObjectAlreadyExists:
            if adapter.job.debug:
                adapter.job.logger.debug(
                    f"IP address {ip_addr} for interface {interface_data['name']} "
                    f"on {vsys.get('firewall_name')} already loaded to diffsync, skipping."
                )
            continue
        except Exception as err:
            adapter.job.logger.error(f"Failed to load interface {interface_obj} for {vsys.get('firewall_name')}, {err}")
