"""Itential SSoT API Clients."""

from typing import List, Optional, Union

import requests

from retry import retry

from nautobot_ssot.integrations.itential.constants import BACKOFF, DELAY, RETRIES


class AutomationGatewayClient:  # pylint: disable=too-many-instance-attributes
    """Itential Automation Gateway API Client."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        job: object,
        verify_ssl: Optional[bool] = True,
        api_version: Optional[str] = "v2.0",
    ):  # pylint: disable=too-many-arguments
        """Initialize the API client.

        Args:
            host (str): Hostname or IP address of automation gateway.
            username (str): Username.
            password (str): Password.
            job (object): Job object.
            verify_ssl (Optional[bool], optional): Enable or disable verification of SSL. Defaults to True.
            api_version (Optional[str], optional): Automation Gateway API version.
        """
        self.host = host
        self.username = username
        self.password = password
        self.job = job
        self.verify_ssl = verify_ssl
        self.api_version = api_version
        self.session = requests.Session()
        self.cookie = {}

    def __enter__(self):
        """Context manager setup."""
        self.login()

    def __exit__(self, exc_type, exc_value, traceback):
        """Context manager teardown."""
        self.logout()

    @property
    def base_url(self):
        """Build base URL."""
        return f"{self.host}/api/{self.api_version}"

    @retry(requests.exceptions.HTTPError, delay=DELAY, tries=RETRIES, backoff=BACKOFF)
    def _get(self, uri: str) -> requests.Response:
        """Perform a GET request to the specified uri."""
        response = self.session.get(f"{self.base_url}/{uri}", verify=self.verify_ssl)
        return response

    @retry(requests.exceptions.HTTPError, delay=DELAY, tries=RETRIES, backoff=BACKOFF)
    def _post(self, uri: str, json_data: Optional[dict] = None) -> requests.Response:
        """Perform a POST request to the specified uri."""
        if json_data:
            response = self.session.post(f"{self.base_url}/{uri}", json=json_data, verify=self.verify_ssl)
        else:
            response = self.session.post(f"{self.base_url}/{uri}", verify=self.verify_ssl)
        return response

    @retry(requests.exceptions.HTTPError, delay=DELAY, tries=RETRIES, backoff=BACKOFF)
    def _put(self, uri: str, json_data: Optional[dict] = None) -> requests.Response:
        """Perform a PUT request to the specified uri."""
        if json_data:
            response = self.session.put(f"{self.base_url}/{uri}", json=json_data, verify=self.verify_ssl)
        else:
            response = self.session.put(f"{self.base_url}/{uri}", verify=self.verify_ssl)
        return response

    @retry(requests.exceptions.HTTPError, delay=DELAY, tries=RETRIES, backoff=BACKOFF)
    def _delete(self, uri: str) -> requests.Response:
        """Perform a GET request to the specified uri."""
        response = self.session.delete(f"{self.base_url}/{uri}", verify=self.verify_ssl)
        return response

    def login(self) -> Union[requests.Response, requests.HTTPError]:
        """Login to Automation Gateway."""
        response = self._post(uri="login", json_data={"username": self.username, "password": self.password})

        if response.ok:
            self.job.logger.info(f"Logging into {self.host}.")
            self.cookie = {"AutomationGatewayToken": response.json()["token"]}
            self.session.headers.update(self.cookie)
            return response.json()
        self.job.logger.warning(f"Failed to login to {self.host}.")
        return response.raise_for_status()

    def logout(self) -> Union[requests.Response, requests.HTTPError]:
        """Logout of Automation Gateway."""
        response = self._post(uri="logout")
        if response.ok:
            self.job.logger.info(f"Logging out of {self.host}.")
            return response.json()
        self.job.logger.warning(f"Failed logging out of {self.host}.")
        return response.raise_for_status()

    def status(self) -> Union[requests.Response, requests.HTTPError]:
        """Get Automation Gateway status."""
        response = self._get(uri="poll")
        if response.ok:
            self.job.logger.info(f"{self.host} polling is successful.")
            return response.json()
        self.job.logger.warning(f"Failed to poll {self.host}.")
        return response.raise_for_status()

    def get_devices(self) -> Union[requests.Response, requests.HTTPError]:
        """Get a devices."""
        response = self._get(uri="devices")
        if response.ok:
            self.job.logger.info(f"Pulling devices from {self.host}.")
            return response.json()
        self.job.logger.warning(f"Failed pulling devices from {self.host}.")
        return response.raise_for_status()

    def get_device(self, device_name: str) -> Union[requests.Response, requests.HTTPError]:
        """Get a device object.

        Args:
            device_name (str): Device name.

        Returns:
            dict: The device and its attributes.
        """
        response = self._get(uri=f"devices/{device_name}")
        if response.ok:
            self.job.logger.info(f"Pulling {device_name} from {self.host}.")
            return response.json()
        self.job.logger.warning(f"Failed pulling {device_name} from {self.host}.")
        return response.raise_for_status()

    def create_device(
        self, device_name: str, variables: Optional[dict]
    ) -> Union[requests.Response, requests.HTTPError]:
        """Create a device with attributes.

        Args:
            device_name (str): Device name.
            variables (dict, optional): Device attributes. Defaults to {}.

        Returns:
            dict: API client return message.
        """
        payload = {"name": device_name, "variables": variables}
        response = self._post(uri="devices", json_data=payload)
        if response.ok:
            self.job.logger.info(f"Creating {device_name} on {self.host}.")
            return response.json()
        self.job.logger.warning(f"Failed to create {device_name} on {self.host}.")
        return response.raise_for_status()

    def update_device(
        self, device_name: str, variables: Optional[dict]
    ) -> Union[requests.Response, requests.HTTPError]:
        """Update a device with attributes.

        Args:
            device_name (str): Device name.
            variables (dict, optional): Device attributes. Defaults to {}.

        Returns:
            dict: API client return message.
        """
        response = self._put(uri=f"devices/{device_name}", json_data=variables)
        if response.ok:
            self.job.logger.info(f"Updating {device_name} on {self.host}.")
            return response.json()
        self.job.logger.warning(f"Failed to update {device_name} on {self.host}.")
        return response.raise_for_status()

    def delete_device(self, device_name: str) -> Union[requests.Response, requests.HTTPError]:
        """Delete a device.

        Args:
            device_name (str): Device name.

        Returns:
            dict: API client return message.
        """
        response = self._delete(uri=f"devices/{device_name}")
        if response.ok:
            self.job.logger.info(f"Deleting {device_name} on {self.host}.")
            return response.json()
        self.job.logger.warning(f"Failed to delete {device_name} on {self.host}.")
        return response.raise_for_status()

    def get_groups(self) -> List[str]:
        """Get a groups."""
        response = self._get(uri="groups")
        if response.ok:
            self.job.logger.info(f"Pulling groups from {self.host}.")
            return response.json()
        self.job.logger.warning(f"Failed pulling groups from {self.host}.")
        return response.raise_for_status()

    def get_group(self, group_name: str) -> Union[requests.Response, requests.HTTPError]:
        """Get a group object.

        Args:
            group_name (str): group name.

        Returns:
            dict: The group and its attributes.
        """
        response = self._get(uri=f"groups/{group_name}")
        if response.ok:
            self.job.logger.info(f"Pulling {group_name} from {self.host}.")
            return response.json()
        self.job.logger.warning(f"Failed pulling {group_name} from {self.host}.")
        return response.raise_for_status()

    def create_group(self, group_name: str, variables: Optional[dict]) -> Union[requests.Response, requests.HTTPError]:
        """Create a group with attributes.

        Args:
            group_name (str): group name.
            variables (dict, optional): group attributes. Defaults to {}.

        Returns:
            dict: API client return message.
        """
        payload = {"name": group_name, "variables": variables}
        response = self._post(uri="groups", json_data=payload)
        if response.ok:
            self.job.logger.info(f"Creating {group_name} on {self.host}.")
            return response.json()
        self.job.logger.warning(f"Failed to create {group_name} on {self.host}.")
        return response.raise_for_status()

    def update_group(self, group_name: str, variables: Optional[dict]) -> Union[requests.Response, requests.HTTPError]:
        """Update a group with attributes.

        Args:
            group_name (str): group name.
            variables (dict, optional): group attributes. Defaults to {}.

        Returns:
            dict: API client return message.
        """
        response = self._put(uri=f"groups/{group_name}", json_data=variables)
        if response.ok:
            self.job.logger.info(f"Updating {group_name} on {self.host}.")
            return response.json()
        self.job.logger.warning(f"Failed to update {group_name} on {self.host}.")
        return response.raise_for_status()

    def delete_group(self, group_name: str) -> Union[requests.Response, requests.HTTPError]:
        """Delete a group.

        Args:
            group_name (str): group name.

        Returns:
            dict: API client return message.
        """
        response = self._delete(uri=f"groups/{group_name}")
        if response.ok:
            self.job.logger.info(f"Deleting {group_name} on {self.host}.")
            return response.json()
        self.job.logger.warning(f"Failed to delete {group_name} on {self.host}.")
        return response.raise_for_status()

    def add_device_to_group(self, group_name: str, device_name: str) -> Union[requests.Response, requests.HTTPError]:
        """Add a device to a group.

        Args:
            group_name (str): Group name.
            device_name (str): Device name.

        Returns:
            Union[requests.Response, requests.HTTPError]: API client return message.
        """
        device_name = [device_name]
        response = self._post(uri=f"groups/{group_name}/devices", json_data=device_name)
        if response.ok:
            self.job.logger.info(f"Adding {device_name} to {group_name} group on {self.host}.")
            return response.json()
        self.job.logger.warning(f"Failed to add {device_name} to {group_name} group on {self.host}.")
        return response.raise_for_status()

    def delete_device_from_group(
        self, group_name: str, device_name: str
    ) -> Union[requests.Response, requests.HTTPError]:
        """Delete a device from a group.

        Args:
            group_name (str): Group name.
            device_name (str): Device name.

        Returns:
            Union[requests.Response, requests.HTTPError]: API client return message.
        """
        response = self._delete(uri=f"groups/{group_name}/devices/{device_name}")
        if response.ok:
            self.job.logger.info(f"Deleting {device_name} from {group_name} group on {self.host}.")
            return response.json()
        self.job.logger.warning(f"Failed to delete {device_name} from {group_name} group on {self.host}.")  # nosec
        return response.raise_for_status()
