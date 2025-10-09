"""Utility functions for working with LibreNMS."""

# pylint: disable=duplicate-code

import ipaddress
import json
import logging
import os

import requests
import urllib3

from nautobot_ssot.exceptions import RequestConnectError, RequestHTTPError

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
            RequestConnectError: Error thrown if request errors.
            RequestHTTPError: Error thrown if HTTP errors.

        Returns:
            dict: JSON payload of API response.
        """
        url = self.validate_url(path)

        if not params:
            params = self.params
        else:
            params = {**self.params, **params}

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
            LOGGER.debug("LibreNMS Response: %s", resp)
            resp.raise_for_status()

            return resp.json()
        except requests.exceptions.HTTPError as err:
            LOGGER.error("Error in communicating to LibreNMS API: %s", err)
            raise RequestConnectError(f"Error communicating to the LibreNMS API: {err}") from err


class LibreNMSApi(ApiEndpoint):  # pylint: disable=too-few-public-methods
    """Representation of interactions with LibreNMS API."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        url: str,
        token: str,
        port: int = 443,
        verify: bool = True,
        devices_load_file=None,
        locations_load_file=None,
    ):
        """Create LibreNMS API connection."""
        super().__init__(url=url)
        self.url = url
        self.token = token
        self.verify = verify
        self.headers = {"Accept": "*/*", "X-Auth-Token": f"{self.token}"}
        self.devices_load_file = devices_load_file
        self.locations_load_file = locations_load_file

        LOGGER.info("Headers %s", self.headers)

    def get_librenms_devices_from_file(self):
        """Get Devices from LibreNMS example file."""
        if self.devices_load_file:
            try:
                # Reset file pointer to beginning
                self.devices_load_file.seek(0)
                # Read and decode the uploaded file
                content = self.devices_load_file.read().decode("utf-8")
                devices = json.loads(content)
                LOGGER.info("Loaded devices from uploaded JSON file")
                LOGGER.debug("File returned devices type: %s", type(devices))
                if devices and "devices" in devices:
                    LOGGER.debug("Devices array type: %s", type(devices["devices"]))
                    if devices["devices"]:
                        LOGGER.debug("First device type: %s", type(devices["devices"][0]))
                return devices
            except (json.JSONDecodeError, UnicodeDecodeError) as err:
                LOGGER.error("Error parsing uploaded devices file: %s", err)
                raise RequestHTTPError(f"Invalid JSON in uploaded devices file: {err}") from err
        else:
            with open(
                file=f"{os.getcwd()}/nautobot_ssot/tests/librenms/fixtures/get_librenms_devices.json",
                encoding="utf-8",
            ) as API_CALL_FIXTURE:  # pylint: disable=invalid-name
                devices = json.load(API_CALL_FIXTURE)
            return devices

    def get_librenms_locations_from_file(self):
        """Get Locations from LibreNMS example file."""
        if self.locations_load_file:
            try:
                # Reset file pointer to beginning
                self.locations_load_file.seek(0)
                # Read and decode the uploaded file
                content = self.locations_load_file.read().decode("utf-8")
                locations = json.loads(content)
                LOGGER.info("Loaded locations from uploaded JSON file")
                return locations
            except (json.JSONDecodeError, UnicodeDecodeError) as err:
                LOGGER.error("Error parsing uploaded locations file: %s", err)
                raise (f"Invalid JSON in uploaded locations file: {err}") from err
        else:
            with open(
                file=f"{os.getcwd()}/nautobot_ssot/tests/librenms/fixtures/get_librenms_locations.json",
                encoding="utf-8",
            ) as API_CALL_FIXTURE:  # pylint: disable=invalid-name
                locations = json.load(API_CALL_FIXTURE)
            return locations

    def get_librenms_devices(self):
        """Get Devices from LibreNMS API endpoint."""
        url = "/api/v0/devices"
        devices = self.api_call(path=url)
        LOGGER.debug("API returned devices type: %s", type(devices))
        if devices and "devices" in devices:
            LOGGER.debug("Devices array type: %s", type(devices["devices"]))
            if devices["devices"]:
                LOGGER.debug("First device type: %s", type(devices["devices"][0]))
        return devices

    def get_librenms_ports(self):
        """Get Ports from LibreNMS API endpoint."""
        url = "/api/v0/ports"
        ports = self.api_call(path=url)
        return ports

    def get_librenms_port_detail(self, port_id: int):
        """Get Port details from LibreNMS API endpoint."""
        url = f"/api/v0/port/{port_id}"
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
        url = f"/api/v0/devicegroups/{group}"
        devices = self.api_call(path=url)
        return devices

    def get_librenms_device_groups_by_device(self, hostname: str):
        """Get DeviceGroup by Device details from LibreNMS API endpoint."""
        url = f"/api/v0/devices/{hostname}/groups"
        device_groups = self.api_call(path=url)
        return device_groups

    def get_librenms_ips_for_device(self, librenms_device_id: int):
        """Get IP by Device details from LibreNMS API endpoint."""
        url = f"/api/v0/devices/{librenms_device_id}/ip"
        ips = self.api_call(path=url)
        return ips

    def get_librenms_ipinfo_for_device_ip(self, librenms_device_id: int, ip_address: str):
        """Get IP info for a device IP address from LibreNMS API endpoint."""
        device_ips = self.get_librenms_ips_for_device(librenms_device_id)
        if device_ips["status"] == "ok" and device_ips["count"] > 0:
            ipaddress_ip_interface = ipaddress.ip_address(ip_address)
            if isinstance(ipaddress_ip_interface, ipaddress.IPv4Address):
                for ipv4_address in device_ips["addresses"]:
                    if ipv4_address["ipv4_address"] == ip_address:
                        ip_network_info = ipaddress.ip_interface(f"{ip_address}/24")
                        ip_address_info = ipaddress.ip_interface(f"{ip_address}/{ipv4_address['ipv4_prefixlen']}")
                        return {
                            "network": f"{ip_network_info.network.with_prefixlen}",
                            "address": f"{ip_address_info.with_prefixlen}",
                        }
            elif isinstance(ipaddress_ip_interface, ipaddress.IPv6Address):
                for ipv6_address in device_ips["addresses"]:
                    if ipv6_address["ipv6_address"] == ip_address:
                        ip_network_info = ipaddress.ip_interface(f"{ip_address}/64")
                        ip_address_info = ipaddress.ip_interface(f"{ip_address}/{ipv6_address['ipv6_prefixlen']}")
                        return {
                            "network": f"{ip_network_info.network.with_prefixlen}",
                            "address": f"{ip_address_info.with_prefixlen}",
                        }
        return None

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
        url = f"/api/v0/locations/{location}"
        method = "PATCH"
        data = location
        response = self.api_call(path=url, method=method, payload=data)
        return response

    def delete_librenms_location(self, location: str):
        """Delete Location details from LibreNMS API endpoint."""
        url = f"/api/v0/locations/{location}"
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
        url = f"/api/v0/devices/{device}"
        method = "PATCH"
        data = device
        response = self.api_call(path=url, method=method, payload=data)
        return response

    def delete_librenms_device(self, device: str):
        """Delete Device details from LibreNMS API endpoint. Either hostname or device_id is required."""
        url = f"/api/v0/devices/{device}"
        method = "DELETE"
        response = self.api_call(path=url, method=method)
        return response
