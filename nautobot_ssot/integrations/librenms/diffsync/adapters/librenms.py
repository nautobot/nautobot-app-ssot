"""Nautobot Ssot Librenms Adapter for LibreNMS SSoT app."""

import os

from diffsync import DiffSync
from diffsync.exceptions import ObjectNotFound
from django.core.exceptions import ValidationError

from nautobot_ssot.integrations.librenms.constants import librenms_status_map, os_manufacturer_map
from nautobot_ssot.integrations.librenms.diffsync.models.librenms import LibrenmsDevice, LibrenmsLocation
from nautobot_ssot.integrations.librenms.utils import get_city_state_geocode, normalize_gps_coordinates, is_running_tests
from nautobot_ssot.integrations.librenms.utils.librenms import LibreNMSApi


class LibrenmsAdapter(DiffSync):
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

    def load_location(self, location: dict):
        """Load Location objects from LibreNMS into DiffSync models."""
        self.job.logger.debug(f'Loading LibreNMS Location {location["location"]}')

        try:
            self.get(self.location, location["location"])
        except ObjectNotFound:
            # FIXME: Need to fix false errors when API errors occur with GeoCode API causing models to falsely need updates.
            _parent = "Unknown"
            if location["lat"] and location["lng"]:
                _location_info = get_city_state_geocode(latitude=location["lat"], longitude=location["lng"])
                _parent = ""
                if _location_info != "Unknown":
                    _parent = f'{_location_info["city"]}, {_location_info["state"]}'
            _latitude = None
            _longitude = None
            if location["lat"]:
                _latitude = normalize_gps_coordinates(location["lat"])
            if location["lng"]:
                _longitude = normalize_gps_coordinates(location["lng"])
            new_location = self.location(
                name=location["location"],
                status="Active",
                location_type="Site",
                parent=_parent,
                latitude=_latitude,
                longitude=_longitude,
                system_of_record=os.getenv("NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD", "LibreNMS"),
            )
            self.add(new_location)

    def load_device(self, device: dict):
        """Load Device objects from LibreNMS into DiffSync models."""
        self.job.logger.debug(f'Loading LibreNMS Device {device["sysName"]}')

        try:
            self.get(self.device, device["sysName"])
        except ObjectNotFound:
            if device["disabled"]:
                _status = "Disabled"
            else:
                _status = librenms_status_map[device["status"]]
            new_device = self.device(
                name=device[self.hostname_field],
                device_id=device["device_id"],
                location=device["location"] if device["location"] is not None else None,
                role=device["type"] if device["type"] is not None else None,
                serial_no=device["serial"] if device["serial"] is not None else "",
                status=_status,
                manufacturer=(
                    os_manufacturer_map.get(device["os"])
                    if os_manufacturer_map.get(device["os"]) is not None
                    else None
                ),
                device_type=device["hardware"] if device["hardware"] is not None else None,
                platform=device["os"] if device["os"] is not None else None,
                os_version=device["version"] if device["version"] is not None else None,
                system_of_record=os.getenv("NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD", "LibreNMS"),
            )
            self.add(new_device)

    def load(self):
        """Load data from LibreNMS into DiffSync models."""
        self.hostname_field = (
            os.getenv("NAUTOBOT_SSOT_LIBRENMS_HOSTNAME_FIELD", "sysName")
            if self.job.hostname_field == "env_var"
            else self.job.hostname_field or "sysName"
        )

        load_type = "file" # file or api
        if is_running_tests():
            load_type = "file"
        elif self.job.load_source == "env_var":
            load_type = os.getenv("NAUTOBOT_BOOTSTRAP_SSOT_LOAD_SOURCE", "file")
        else:
            load_type = self.job.load_source

        if load_type != "file":
            all_devices = self.lnms_api.get_librenms_devices()
        else:
            all_devices = self.lnms_api.get_librenms_devices_from_file()

        self.job.logger.info(f'Loading {all_devices["count"]} Devices from LibreNMS.')

        if load_type != "file":
            all_locations = self.lnms_api.get_librenms_locations()
        else:
            all_locations = self.lnms_api.get_librenms_locations_from_file()

        self.job.logger.info(f'Loading {all_locations["count"]} Locations from LibreNMS.')

        for _device in all_devices["devices"]:
            self.load_device(device=_device)
        for _location in all_locations["locations"]:
            self.load_location(location=_location)
