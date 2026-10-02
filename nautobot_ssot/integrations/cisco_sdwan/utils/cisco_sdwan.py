"""Utility functions for working with Cisco SD-WAN (vManage / Catalyst SD-WAN Manager)."""

import re
from typing import Any, Dict, List, Optional

from cisco_sdwan.base.rest_api import Rest, RestAPIException


class CiscoSdwanManager:
    """Lightweight wrapper around the Cisco Catalyst SD-WAN Manager (vManage) REST API.

    A fresh REST session is created for each call using a context manager unless an
    existing client is passed in. This keeps the implementation simple and safe, at
    the cost of logging in once per request.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self, job, base_url: str, username: str, password: str, verify: bool = True
    ) -> None:
        """Initialize the CiscoSdwanManager.

        Args:
            job: The running Nautobot Job, used for logging.
            base_url (str): The SD-WAN Manager URL.
            username (str): The SD-WAN Manager username.
            password (str): The SD-WAN Manager password.
            verify (bool): Whether to verify TLS certificates (recommended True in production).
        """
        self.job = job
        self.base_url = base_url
        self.username = username
        self.password = password
        self.verify = verify

    def _new_api(self) -> Rest:
        """Create a new REST API client instance with no active network session yet."""
        return Rest(
            base_url=self.base_url,
            username=self.username,
            password=self.password,
            verify=self.verify,
        )

    def send_request(
        self,
        method: str,
        endpoint: str,
        api: Optional[Rest] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Send an HTTP request to an SD-WAN Manager REST API endpoint.

        Args:
            method (str): The HTTP method to use ('get', 'post', 'put', 'delete').
            endpoint (str): The REST endpoint path, e.g. 'device' or 'template/device'.
            api (Rest): An existing SD-WAN Rest client instance. If not provided, a new
                temporary client will be created and used via a context manager.
            payload (dict): Optional JSON payload for write operations.

        Returns:
            Any: The parsed JSON response from the SD-WAN Manager.

        Raises:
            ValueError: If the HTTP method is unsupported.
        """
        method = method.lower()
        allowed_methods = {"get", "post", "put", "delete"}

        if method not in allowed_methods:
            raise ValueError(f"Unsupported HTTP method: {method!r}")

        if self.job.debug:
            self.job.logger.debug(f"Sending {method} request to {endpoint}.")

        def _call(client: Rest) -> Any:  # pylint: disable=inconsistent-return-statements
            try:
                match method:
                    case "get":
                        return client.get(endpoint)
                    case "post":
                        return client.post(endpoint, payload or {})
                    case "put":
                        return client.put(endpoint, payload or {})
                    case "delete":
                        return client.delete(endpoint, payload or {})
            except RestAPIException as err:
                self.job.logger.error(f"API {method} request to {endpoint} failed with {err}")

        if api is not None:
            # Reuse existing client / session
            return _call(api)

        # Create a fresh client for this call
        with self._new_api() as client:
            return _call(client)

    def get_server_version(self) -> str:
        """Retrieve the SD-WAN Manager server version."""
        with self._new_api() as api:
            return api.server_version

    def get_devices(self, device_filter: Optional[List] = None) -> List[Dict]:
        """Retrieve all SD-WAN devices (WAN Edges and controllers) from the SD-WAN Manager.

        Args:
            device_filter (list): Optional list of Nautobot Device objects. When provided, only
                SD-WAN devices whose hostname matches one of the Device names are returned.

        Returns:
            list[dict]: The device inventory as returned by the SD-WAN Manager.
        """
        response = self.send_request(method="get", endpoint="/system/device/vedges")
        devices = response.get("data", []) if response else []
        response = self.send_request(method="get", endpoint="/system/device/controllers")
        if response:
            devices.extend(response.get("data", []))
        devices = [device for device in devices if device.get("host-name")]
        if device_filter:
            device_names_filter = {device.name for device in device_filter}
            devices = [device for device in devices if device["host-name"] in device_names_filter]
        return devices

    def get_device_interfaces(self, device_id: str, api: Optional[Rest] = None) -> Optional[List[Dict]]:
        """Retrieve interfaces for a specific device using NMS-synced data.

        Args:
            device_id (str): The system IP or device identifier of the SD-WAN device.
            api (Rest): Optional existing Rest client to reuse for the request.

        Returns:
            list[dict]: Interface information returned by the SD-WAN Manager, or None.
        """
        response = self.send_request(
            method="get",
            endpoint=f"/device/interface/synced?deviceId={device_id}",
            api=api,
        )
        if response:
            return response.get("data")
        return None

    def get_interfaces(self, devices: List[Dict]) -> List[Dict]:
        """Retrieve NMS-synced interface data for each device and attach it to the device record.

        Args:
            devices (list[dict]): Device dictionaries returned by the SD-WAN Manager.

        Returns:
            list[dict]: The same list of device dictionaries, each updated with an 'interfaces' key.
        """
        with self._new_api() as api:
            for device in devices:
                device_id = device.get("system-ip") or device.get("deviceId")
                if not device_id:
                    device["interfaces"] = []
                    continue

                device_interfaces = self.get_device_interfaces(device_id=device_id, api=api)
                device["interfaces"] = device_interfaces or []

        return devices


def normalize_device_model(device_model: str, pattern: Optional[str] = None) -> str:
    r"""Normalize a device model by removing all occurrences of a regex pattern anywhere in the string.

    Args:
        device_model (str): The original device model string.
        pattern (str): A regular expression pattern. All matches of this pattern will be removed.
            Examples: r"^vedge-" (remove a prefix), r"[-_]" (remove separators), r"\s+" (whitespace).

    Returns:
        str: The normalized device model.
    """
    if not pattern:
        return device_model

    # Remove all regex matches
    cleaned = re.sub(pattern, "", device_model)

    # Normalize whitespace and strip edges
    return cleaned.strip()


def normalize_software_version(version: Optional[str]) -> Optional[str]:
    """Normalize Cisco IOS XE / SD-WAN software versions for Nautobot.

    Rules:
    - Keep major.minor.patch with zero-padding (MM.mm.pp)
    - Keep optional patch letter (e.g. 'a')
    - Strip internal build numbers (e.g. '.0.6476')

    Args:
        version (str): The raw version string reported by the SD-WAN Manager.

    Returns:
        str: The normalized version string, or None if no version was provided.
    """
    if not version:
        return None

    # Match: major.minor.patch + optional letter
    match = re.match(r"^\s*(\d+)\.(\d+)\.(\d+)([a-zA-Z]?)", version)

    if not match:
        # Fallback: return cleaned original
        return version.strip()

    major, minor, patch, letter = match.groups()

    # Zero-pad minor and patch
    return f"{int(major)}.{int(minor):02d}.{int(patch):02d}{letter}"
