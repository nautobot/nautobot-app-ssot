"""Panorama SDK."""

from panos.panorama import Panorama as PanOsPanorama

from .device_group import PanoramaDeviceGroupAPI
from .firewall import PanoramaFirewallAPI


class Panorama:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
    """Wrapper on Panorama python SDK."""

    def __init__(self, url=None, username=None, password=None, verify=True, port=443, job=None):  # pylint: disable=too-many-arguments
        """Create base connectivity to Panorama."""
        self.pano = PanOsPanorama(url, api_username=username, api_password=password, port=port, verify=verify)
        self.device_group = PanoramaDeviceGroupAPI(self.pano, {}, job=job)
        self.device_groups = self.device_group.retrieve_device_groups()  # Cache device groups
        self.firewall = PanoramaFirewallAPI(self.pano, self.device_groups, job=job)
