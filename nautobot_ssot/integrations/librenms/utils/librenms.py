"""Utility functions for working with LibreNMS."""

import json
import logging
import os

import requests
import urllib3

LOGGER = logging.getLogger(__name__)


class ApiEndpoint:  # pylint: disable=too-few-public-methods
    """Base class to represent interactions with an API endpoint."""

    class Meta:
        """Meta data for ApiEndpoint class."""

        abstract = True

    def __init__(self, url: str, port: int = 443, timeout: int = 30, verify: bool = True):
        """Create API connection."""
        self.url = url
        self.port = port
        self.timeout = timeout
        self.base_url = f"{self.url}:{self.port}"
        self.verify = verify
        self.headers = {"Accept": "*/*"}
        self.params = {}

        if verify is False:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def validate_url(self, path):
        """Validate URL formatting is correct.

        Args:
            path (str): URI path for API endpoint

        Returns:
            str: Formatted URL path for API endpoint
        """
        if not self.base_url.endswith("/") and not path.startswith("/"):
            full_path = f"{self.base_url}/{path}"
        else:
            full_path = f"{self.base_url}{path}"
        if not full_path.endswith("/"):
            return full_path
        return full_path

    def api_call(self, path: str, method: str = "GET", params: dict = {}, payload: dict = {}):  # pylint: disable=dangerous-default-value
        """Send Request to API endpoint of type `method`. Defaults to GET request.

        Args:
            path (str): API path to send request to.
            method (str, optional): API request method. Defaults to "GET".
            params (dict, optional): Additional parameters to send to API. Defaults to None.
            payload (dict, optional): Message payload to be sent as part of API call.

        Raises:
            Exception: Error thrown if request errors.

        Returns:
            dict: JSON payload of API response.
        """
        url = self.validate_url(path)

        if not params:
            params = self.params
        else:
            params = {**self.params, **params}

        LOGGER.debug(
            f"LibreNMS API Call: Headers: {self.headers} Method: {method} URL: {url} Params: {params} Payload: {payload}"
        )

        resp = requests.request(
            method=method,
            headers=self.headers,
            url=url,
            params=params,
            verify=self.verify,
            json=payload,
            timeout=self.timeout,
        )
        try:
            LOGGER.debug(f"LibreNMS Response: {resp}")
            resp.raise_for_status()

            return resp.json()
        except requests.exceptions.HTTPError as err:
            LOGGER.error(f"Error in communicating to LibreNMS API: {err}")
            raise Exception(f"Error communicating to the LibreNMS API: {err}")


class LibreNMSApi(ApiEndpoint):  # pylint: disable=too-few-public-methods
    """Representation of interactions with LibreNMS API."""

    def __init__(self, url: str, token: str, port: int = 443, verify: bool = True):
        """Create LibreNMS API connection."""
        super().__init__(url=url)
        self.url = url
        self.token = token
        self.verify = verify
        self.headers = {"Accept": "*/*", "X-Auth-Token": f"{self.token}"}

        LOGGER.info(f"Headers {self.headers}")

    def get_librenms_devices_from_file(self):  # pylint: disable=no-self-use
        """Get Devices from LibreNMS example file."""
        with open(
            file=f"{os.getcwd()}/nautobot_ssot/tests/librenms/fixtures/get_librenms_devices.json",
            encoding="utf-8",
        ) as API_CALL_FIXTURE:  # pylint: disable=invalid-name
            devices = json.load(API_CALL_FIXTURE)
        return devices

    def get_librenms_locations_from_file(self):  # pylint: disable=no-self-use
        """Get Locations from LibreNMS example file."""
        with open(
            file=f"{os.getcwd()}/nautobot_ssot/tests/librenms/fixtures/get_librenms_locations.json",
            encoding="utf-8",
        ) as API_CALL_FIXTURE:  # pylint: disable=invalid-name
            devices = json.load(API_CALL_FIXTURE)
        return devices

    def get_librenms_devices(self):
        """Get Devices from LibreNMS API endpoint."""
        url = "/api/v0/devices"
        devices = self.api_call(path=url)
        return devices

    def get_librenms_ports(self):
        """Get Ports from LibreNMS API endpoint."""
        url = "/api/v0/ports"
        ports = self.api_call(path=url)
        return ports

    def get_librenms_port_detail(self, port_id: int):
        """Get Port details from LibreNMS API endpoint."""
        url = "/api/v0/port/{port_id}"
        port_details = self.api_call(path=url)
        return port_details

    def get_librenms_locations(self):
        """Get Location details from LibreNMS API endpoint."""
        url = "/api/v0/resources/locations"
        locations = self.api_call(path=url)
        return locations

    def get_librenms_device_groups(self):
        """Get DeviceGroup details from LibreNMS API endpoint."""
        url = "/api/v0/devicegroups"
        device_groups = self.api_call(path=url)
        return device_groups

    def get_librenms_devices_by_device_group(self, group: str):
        """Get Devices by DeviceGroup details from LibreNMS API endpoint."""
        url = "/api/v0/devicegroups/{group}"
        devices = self.api_call(path=url)
        return devices

    def get_librenms_device_groups_by_device(self, hostname: str):
        """Get DeviceGroup by Device details from LibreNMS API endpoint."""
        url = "/api/v0/devices/{hostname}/groups"
        device_groups = self.api_call(path=url)
        return device_groups

    def get_librenms_ip_for_device(self, hostname: str):
        """Get IP by Device details from LibreNMS API endpoint."""
        url = "/api/v0/devices/{hostname}/ip"
        ips = self.api_call(path=url)
        return ips

    def get_librenms_vrf(self):
        """Get VRF details from LibreNMS API endpoint."""
        url = "/api/v0/routing/vrf"
        vrf = self.api_call(path=url)
        return vrf

    def get_librenms_vlans(self):
        """Get VRF details from LibreNMS API endpoint."""
        url = "/api/v0/resources/vlans"
        vlans = self.api_call(path=url)
        return vlans

    def create_librenms_location(self, location: dict):
        """Add Location details to LibreNMS API endpoint."""
        url = "/api/v0/locations"
        method = "POST"
        data = location
        response = self.api_call(path=url, method=method, payload=data)
        return response

    def update_librenms_location(self, location: dict):
        """Update Location details to LibreNMS API endpoint."""
        url = "/api/v0/locations{location}"
        method = "PATCH"
        data = location
        response = self.api_call(path=url, method=method, payload=data)
        return response

    def delete_librenms_location(self, location: str):
        """Delete Location details from LibreNMS API endpoint."""
        url = "/api/v0/locations/{location}"
        method = "DELETE"
        response = self.api_call(path=url, method=method)
        return response

    def create_librenms_device(self, device: dict):
        """Add Device details to LibreNMS API endpoint."""
        url = "/api/v0/devices"
        method = "POST"
        data = device
        response = self.api_call(path=url, method=method, payload=data)
        return response

    def update_librenms_device(self, device: dict):
        """Update Device details to LibreNMS API endpoint."""
        url = "/api/v0/devices{device}"
        method = "PATCH"
        data = device
        response = self.api_call(path=url, method=method, payload=data)
        return response

    def delete_librenms_device(self, device: str):
        """Delete Device details from LibreNMS API endpoint. Either hostname or device_id is required."""
        url = "/api/v0/devices/{device}"
        method = "DELETE"
        response = self.api_call(path=url, method=method)
        return response
