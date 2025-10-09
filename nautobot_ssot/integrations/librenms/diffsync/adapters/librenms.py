"""Nautobot Ssot Librenms Adapter for LibreNMS SSoT app."""

import json
import os

from diffsync import Adapter
from diffsync.exceptions import ObjectAlreadyExists, ObjectNotFound
from django.core.exceptions import ValidationError

from nautobot_ssot.integrations.librenms.constants import (
    LIBRENMS_LIB_MAPPER,
    PLUGIN_CFG,
    librenms_status_map,
    os_manufacturer_map,
)
from nautobot_ssot.integrations.librenms.diffsync.models.librenms import (
    LibrenmsDevice,
    LibrenmsLocation,
)
from nautobot_ssot.integrations.librenms.utils import (
    has_required_values,
    normalize_device_hostname,
    normalize_gps_coordinates,
)
from nautobot_ssot.integrations.librenms.utils.librenms import LibreNMSApi
from nautobot_ssot.utils import parse_hostname_for_location, parse_hostname_for_role


class LibrenmsAdapter(Adapter):
    """DiffSync adapter for LibreNMS."""

    location = LibrenmsLocation
    device = LibrenmsDevice

    top_level = ["location", "device"]

    def __init__(self, *args, job=None, sync=None, librenms_api: LibreNMSApi, **kwargs):
        """Initialize LibreNMS.

        Args:
            job (object, optional): LibreNMS job. Defaults to None.
            sync (object, optional): LibreNMS DiffSync. Defaults to None.
            client (object): LibreNMS API client connection object.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.lnms_api = librenms_api
        self.failed_import_devices = []

    def load_location(self, location: dict):
        """Load Location objects from LibreNMS into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f'Loading LibreNMS Location {location["location"]}')

        try:
            self.get(self.location, location["location"])
        except ObjectNotFound:
            _latitude = None
            _longitude = None
            if location["lat"]:
                _latitude = normalize_gps_coordinates(location["lat"])
            if location["lng"]:
                _longitude = normalize_gps_coordinates(location["lng"])
            new_location = self.location(
                name=location["location"],
                status="Active",
                location_type=self.job.location_type.name,
                latitude=_latitude,
                longitude=_longitude,
                system_of_record=os.getenv("NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD", "LibreNMS"),
            )
            self.add(new_location)

    def load_device(self, device: dict):
        """Load Device objects from LibreNMS into DiffSync models."""
        # Ensure device is a dictionary
        if not isinstance(device, dict):
            self.job.logger.warning(f"Device data is not a dictionary: {type(device)} - {device}")
            self.failed_import_devices.append(device)
            return

        # Get the hostname field to use
        hostname_field = (
            os.getenv("NAUTOBOT_SSOT_LIBRENMS_HOSTNAME_FIELD", "sysName")
            if self.job.hostname_field == "env_var"
            else self.job.hostname_field or "sysName"
        )

        if self.job.debug:
            self.job.logger.debug(f"Loading LibreNMS Device {device[hostname_field]}")

        if device["os"] != "ping":
            if device["type"] in PLUGIN_CFG.get("librenms_permitted_values", {}).get("role"):
                normalized_name = normalize_device_hostname(device[hostname_field], self.job)
                if isinstance(normalized_name, str):
                    location_data = parse_hostname_for_location(
                        str(self.job.location_map) if self.job.location_map else {"name": device["location"], "parent": device["location"]}, normalized_name, device["location"]
                    )
                    role = parse_hostname_for_role(
                        str(self.job.hostname_map) if self.job.hostname_map else None,
                        normalized_name,
                        self.job.default_role if self.job.default_role else "Unknown",
                    )
                    normalized_platform = LIBRENMS_LIB_MAPPER.get(device["os"], device["os"])
                    ip_address = device.get("ip", None)
                    ip_info = None  # Initialize ip_info to None
                    if ip_address:
                        try:
                            ip_info = self.lnms_api.get_librenms_ipinfo_for_device_ip(device["device_id"], ip_address)
                        except Exception as e:
                            self.job.logger.warning(f"Error getting IP info for {ip_address}: {e}")
                            ip_info = None
                    self.job.logger.debug(f"Platform for {normalized_name}: {normalized_platform}")
                    device_type = device["hardware"]
                    if self.job.debug:
                        self.job.logger.debug(f"Role for {normalized_name}: {role}")
                        self.job.logger.debug(f"Platform for {normalized_name}: {normalized_platform}")
                        self.job.logger.debug(f"Device type for {normalized_name}: {device_type}")

                    device_validation_dict = {
                        self.job.hostname_field: normalized_name,
                        "location": location_data["name"],
                        "role": role,
                        "platform": device["os"],
                        "device_type": device_type,
                    }
                    if self.job.debug:
                        self.job.logger.debug(
                            f"Device validation dictionary for {device[hostname_field]}: {device_validation_dict}"
                        )
                    validation_result = has_required_values(device_validation_dict, self.job)
                    device["field_validation"] = validation_result

                    if self.job.debug:
                        self.job.logger.debug(f"Validation result for {device[hostname_field]}: {validation_result}")

                    if any(value["valid"] is False for value in validation_result.values()):
                        failed_device = device.copy()
                        self.failed_import_devices.append(failed_device)
                        return

                else:
                    device_validation_dict = {
                        self.job.hostname_field: normalized_name,
                        "location": {"valid": False, "reason": "Hostname validation failed"},
                        "role": {"valid": False, "reason": "Hostname validation failed"},
                        "platform": {"valid": False, "reason": "Hostname validation failed"},
                        "device_type": {"valid": False, "reason": "Hostname validation failed"},
                    }
                    validation_result = has_required_values(device_validation_dict, self.job)
                    device["field_validation"] = validation_result

                    if self.job.debug:
                        self.job.logger.debug(f"Validation result for {device[hostname_field]}: {validation_result}")

                    # Hostname validation failed, so this device should always fail
                    failed_device = device.copy()
                    self.failed_import_devices.append(failed_device)
                    return

                try:
                    self.get(self.device, {"name": normalized_name})
                except ObjectNotFound:
                    if device["disabled"] == 1:
                        _status = "Offline"
                    else:
                        _status = librenms_status_map[device["status"]]
                        manufacturer = os_manufacturer_map.get(device["os"])

                        # Store the full location data in the device for the NautobotDevice to use
                        device["_location_data"] = location_data

                        try:
                            new_device = self.device(
                                name=normalized_name,
                                device_id=device["device_id"],
                                location=location_data["name"],
                                parent_location=location_data["parent"],
                                snmp_location=device["location"],
                                role=str(role) if role else None,
                                serial_no=device["serial"] if device["serial"] is not None else "",
                                status=_status,
                                manufacturer=manufacturer,
                                device_type=device["hardware"],
                                platform=normalized_platform,
                                os_version=device["version"] if device["version"] is not None else "Unknown",
                                tenant=str(self.job.tenant) if self.job.tenant else None,
                                ip_address=str(ip_info["address"]) if ip_info and ip_info.get("address") else None,
                                ip_prefix=str(ip_info["network"]) if ip_info and ip_info.get("network") else None,
                                system_of_record=os.getenv("NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD", "LibreNMS"),
                            )
                        except ValidationError as err:
                            self.failed_import_devices.append(device)
                            self.job.logger.warning(f"Device {device[hostname_field]} failed to load: {err}")
                            return
                    try:
                        self.add(new_device)
                    except ObjectAlreadyExists:
                        self.job.logger.warning(f"Device {device[hostname_field]} already exists. Skipping.")
            else:
                self.job.logger.warning(
                    f'Device {device[hostname_field]} role "{device["type"]}" is not permitted by the configuration. Skipping.'
                )
        else:
            self.job.logger.warning(f'Device {device[hostname_field]} is "ping-only". Skipping.')

    def load(self):
        """Load data from LibreNMS into DiffSync models."""
        self.hostname_field = (
            os.getenv("NAUTOBOT_SSOT_LIBRENMS_HOSTNAME_FIELD", "sysName")
            if self.job.hostname_field == "env_var"
            else self.job.hostname_field or "sysName"
        )

        load_source = self.job.load_type

        if load_source != "file":
            all_devices = self.lnms_api.get_librenms_devices()
        else:
            all_devices = self.lnms_api.get_librenms_devices_from_file()

        self.job.logger.info(f'Loading {all_devices["count"]} Devices from LibreNMS.')

        # Debug: Check the structure of the devices array
        if self.job.debug:
            self.job.logger.debug(f"Devices array type: {type(all_devices['devices'])}")
            if all_devices["devices"]:
                self.job.logger.debug(f"First device type: {type(all_devices['devices'][0])}")
                self.job.logger.debug(f"First device content: {all_devices['devices'][0]}")

        for _device in all_devices["devices"]:
            self.load_device(device=_device)

        if PLUGIN_CFG.get("librenms_show_failures"):
            if self.failed_import_devices:
                self.job.logger.warning(
                    f"List of {len(self.failed_import_devices)} devices that were unable to be loaded. {json.dumps(self.failed_import_devices, indent=2)}"
                )
            else:
                self.job.logger.info("There weren't any failed device loads. Congratulations!")

        if self.job.sync_locations:
            if load_source != "file":
                all_locations = self.lnms_api.get_librenms_locations()
            else:
                all_locations = self.lnms_api.get_librenms_locations_from_file()

            self.job.logger.info(f'Loading {all_locations["count"]} Locations from LibreNMS.')

            for _location in all_locations["locations"]:
                self.load_location(location=_location)
        else:
            self.job.logger.info("Location Sync Disabled. Skipping loading locations.")
