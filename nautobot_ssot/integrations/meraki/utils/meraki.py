"""Utility functions for working with Meraki."""

from typing import List

import meraki


class DashboardClient:
    """Client for interacting with Meraki dashboard."""

    def __init__(self, logger, org_id: str, token: str, *args, **kwargs):
        """Initialize Meraki dashboard client."""
        self.logger = logger
        self.org_id = org_id
        self.token = token
        self.conn = self.connect_dashboard()
        self.network_map = {}

    def connect_dashboard(self) -> meraki.DashboardAPI:  # pylint: disable=inconsistent-return-statements
        """Connect to Meraki dashboard and return connection object.

        Raises:
            err: APIError if issue with connecting to Meraki dashboard.

        Returns:
            meraki.DashboardAPI: Connection to Meraki dashboard.
        """
        try:
            dashboard = meraki.DashboardAPI(
                api_key=self.token,
                base_url="https://api.meraki.com/api/v1/",
                output_log=False,
                print_console=False,
                wait_on_rate_limit=True,
                maximum_retries=100,
            )
            return dashboard
        except meraki.APIError as err:
            self.logger.log.error(f"Unable to connect to Meraki dashboard: {err.message}")
            raise err

    def validate_organization_exists(self) -> bool:
        """Confirm defined organization ID is seen in Dashboard to confirm we have access.

        Returns:
            bool: Whether Organiztion ID was found in Dashboard.
        """
        orgs = self.conn.organizations.getOrganizations()
        ids = [org["id"] for org in orgs]
        if self.org_id in ids:
            return True
        return False

    def get_org_networks(self) -> list:
        """Retrieve all networks for specified Organization ID.

        Returns:
            list: List of found networks. Empty list if error retrieving networks.
        """
        networks = []
        try:
            networks = self.conn.organizations.getOrganizationNetworks(organizationId=self.org_id)
            self.network_map = {net["id"]: net for net in networks}
        except meraki.APIError as err:
            self.logger.logger.warning(
                f"Meraki API error: {err}\nstatus code = {err.status}\nreason = {err.reason}\nerror = {err.message}"
            )
        return networks

    def get_org_devices(self) -> list:
        """Retrieve all devices for specified Organization ID.

        Returns:
            list: List of found devices. Empty list if error retrieving devices.
        """
        devices = []
        try:
            devices = self.conn.organizations.getOrganizationDevices(organizationId=self.org_id)
        except meraki.APIError as err:
            self.logger.logger.warning(
                f"Meraki API error: {err}\nstatus code = {err.status}\nreason = {err.reason}\nerror = {err.message}"
            )
        return devices

    def get_org_uplink_statuses(self) -> dict:
        """Retrieve appliance uplink statuses for MX, MG, and Z devices for specified Organization ID.

        Returns:
            dict: Map of Device serial to uplink settings for those MX, MG, and Z devices in specified organization ID.
        """
        settings_map = {}
        try:
            result = self.conn.organizations.getOrganizationUplinksStatuses(organizationId=self.org_id)
            settings_map = {net["serial"]: net for net in result}
        except meraki.APIError as err:
            self.logger.logger.warning(
                f"Meraki API error: {err}\nstatus code = {err.status}\nreason = {err.reason}\nerror = {err.message}"
            )
        return settings_map

    def get_org_uplink_addresses_by_device(self, serial: str) -> List[dict]:
        """Retrieve uplink addresses for specified device serial.

        Args:
            serial (str): Serial of device to retrieve uplink addresses for.

        Returns:
            List[dict]: List of dictionaries of uplink addresses for device with specified serial.
        """
        addresses = []
        try:
            addresses = self.conn.organizations.getOrganizationDevicesUplinksAddressesByDevice(
                organizationId=self.org_id, serials=[serial]
            )
        except meraki.APIError as err:
            self.logger.logger.warning(
                f"Meraki API error: {err}\nstatus code = {err.status}\nreason = {err.reason}\nerror = {err.message}"
            )
        return addresses

    def get_org_switchports(self) -> dict:
        """Retrieve all ports for switches in specified organization ID.

        Returns:
            dict: Map of Device serial to switchport information for specified organization ID.
        """
        port_map = {}
        try:
            result = self.conn.switch.getOrganizationSwitchPortsBySwitch(organizationId=self.org_id)
            port_map = {switch["serial"]: switch for switch in result}
        except meraki.APIError as err:
            self.logger.logger.warning(
                f"Meraki API error: {err}\nstatus code = {err.status}\nreason = {err.reason}\nerror = {err.message}"
            )
        return port_map

    def get_org_device_statuses(self) -> dict:
        """Retrieve device statuses from Meraki dashboard.

        Returns:
            dict: Dictionary of Device name with its status as value.
        """
        statuses = {}
        try:
            response = self.conn.organizations.getOrganizationDevicesStatuses(organizationId=self.org_id)
            statuses = {dev["name"]: dev["status"] for dev in response}
        except meraki.APIError as err:
            self.logger.logger.warning(
                f"Meraki API error: {err}\nstatus code = {err.status}\nreason = {err.reason}\nerror = {err.message}"
            )
        return statuses

    def get_management_ports(self, serial: str) -> dict:
        """Retrieve device management ports from Meraki dashboard.

        Args:
            serial (str): Serial of device to retrieve management ports for.

        Returns:
            list: List of management ports and associated information.
        """
        ports = {}
        try:
            ports = self.conn.devices.getDeviceManagementInterface(serial=serial)
            if ports.get("ddnsHostnames"):
                ports.pop("ddnsHostnames")
        except meraki.APIError as err:
            self.logger.logger.warning(
                f"Meraki API error: {err}\nstatus code = {err.status}\nreason = {err.reason}\nerror = {err.message}"
            )
        return ports

    def get_uplink_settings(self, serial: str) -> dict:
        """Retrieve settings for uplink ports from Meraki dashboard.

        Args:
            serial (str): Serial of device to retrieve uplink settings for.

        Returns:
            dict: Dictionary of uplink settings for device with specified serial.
        """
        ports = {}
        try:
            ports = self.conn.appliance.getDeviceApplianceUplinksSettings(serial=serial)
            ports = ports["interfaces"]
        except meraki.APIError as err:
            self.logger.logger.warning(
                f"Meraki API error: {err}\nstatus code = {err.status}\nreason = {err.reason}\nerror = {err.message}"
            )
        return ports

    def get_switchport_statuses(self, serial: str) -> dict:
        """Retrieve statuses for all switchports on specified MS Device.

        Args:
            serial (str): Serial of MS device in question.

        Returns:
            dict: Map of switch ports and associated information.
        """
        port_statuses = {}
        try:
            result = self.conn.switch.getDeviceSwitchPortsStatuses(serial=serial)
            port_statuses = {port["portId"]: port for port in result}
        except meraki.APIError as err:
            self.logger.logger.warning(
                f"Meraki API error: {err}\nstatus code = {err.status}\nreason = {err.reason}\nerror = {err.message}"
            )
        return port_statuses

    def get_appliance_switchports(self, network_id: str) -> list:
        """Retrieve switchports for MX devices in specified network ID.

        Args:
            network_id (str): Network ID that MX device belongs to.

        Returns:
            list: List of switchports for network that MX device belongs to.
        """
        ports = []
        try:
            ports = self.conn.appliance.getNetworkAppliancePorts(networkId=network_id)
        except meraki.APIError as err:
            self.logger.logger.warning(
                f"Meraki API error: {err}\nstatus code = {err.status}\nreason = {err.reason}\nerror = {err.message}"
            )
        return ports


def get_role_from_devicetype(dev_model: str, devicetype_map: dict) -> str:
    """Get Device Role using DeviceType from devicetype_mapping Setting.

    Args:
        dev_model (str): Hardware model of Device to determine role of.
        devicetype_map (dict): Dictionary of DeviceType's mapped to their Role.

    Returns:
        str: Name of DeviceRole. Defaults to Unknown.
    """
    dev_role = "Unknown"
    for entry in devicetype_map:
        if entry[0] in dev_model:
            dev_role = entry[1]
    return dev_role
