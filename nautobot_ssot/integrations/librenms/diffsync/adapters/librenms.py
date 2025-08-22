"""Nautobot Ssot Librenms Adapter for LibreNMS SSoT app."""

import json
import os

from diffsync import Adapter
from diffsync.exceptions import ObjectAlreadyExists, ObjectNotFound
from django.core.exceptions import ValidationError

from nautobot_ssot.integrations.librenms.constants import (
    librenms_status_map,
    os_manufacturer_map,
    PLUGIN_CFG,
)
from nautobot_ssot.integrations.librenms.diffsync.models.librenms import (
    LibrenmsDevice,
    LibrenmsLocation,
)
from nautobot_ssot.integrations.librenms.utils import (
    normalize_device_hostname,
    normalize_gps_coordinates,
    validate_device_data,
)
from nautobot_ssot.integrations.librenms.utils.librenms import LibreNMSApi


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
        if self.job.debug:
            self.job.logger.debug(f'Loading LibreNMS Device {device[self.job.hostname_field]}')

        if device["os"] != "ping":
            if device["type"] in PLUGIN_CFG.get("librenms_permitted_values").get("role"):
                validated_device = validate_device_data(device, self.job)
                if validated_device["load_errors"]:
                    self.job.logger.error(f"Unable to load device {device[self.job.hostname_field]}: {validated_device['load_errors']}.")
                    self.failed_import_devices.append(device)
                    return
                try:
                    self.get(self.device, device[self.job.hostname_field])
                except ObjectNotFound:
                    if device["disabled"] == 1:
                        _status = "Offline"
                    else:
                        _status = librenms_status_map[device["status"]]
                    try:
                        new_device = self.device(
                            name=normalize_device_hostname(device, self.job),
                            device_id=device["device_id"],
                            location=device["location"],
                            role=device["type"],
                            serial_no=device["serial"] if device["serial"] is not None else "",
                            status=_status,
                            manufacturer=os_manufacturer_map.get(device["os"]),
                            device_type=device["hardware"],
                            platform=device["os"],
                            os_version=device["version"] if device["version"] is not None else "Unknown",
                            ip_address=device["ip"],
                            system_of_record=os.getenv("NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD", "LibreNMS"),
                        )
                    except ValidationError as err:
                        self.job.logger.error(f"Unable to load device {device[self.hostname_field]}: {err}.  Skipping.")
                        device["load_error"] = err
                        self.failed_import_devices.append(device)
                        return
                    try:
                        self.add(new_device)
                    except ObjectAlreadyExists:
                        self.job.logger.warning(f"Device {device[self.hostname_field]} already exists. Skipping.")
            else:
                self.job.logger.warning(f'Device {device[self.hostname_field]} does not have a permitted role ({device["type"]}). Skipping.')
        else:
            self.job.logger.info(f'Device {device[self.hostname_field]} is "ping-only". Skipping.')

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
