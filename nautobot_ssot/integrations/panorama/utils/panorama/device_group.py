"""DeviceGroup API."""

from panos.errors import PanDeviceXapiError
from panos.panorama import DeviceGroup, PanoramaDeviceGroupHierarchy

from .base import BaseAPI


class PanoramaDeviceGroupAPI(BaseAPI):
    """DeviceGroup Objects API SDK."""

    def get(self, name):
        """Returns a prefetched instance."""
        return self.device_groups[name]["value"]

    def get_parent(self, name):
        """Returns parent DeviceGroup name."""
        exceptions = 0
        while exceptions < 3:
            if exceptions > 0:
                self.job.logger.warning(f"Retrying to get parent for {name}...")
            try:
                parent = PanoramaDeviceGroupHierarchy(self.pano).fetch().get(name)
                return parent
            except Exception as err:
                exceptions += 1
                self.job.logger.warning(f"Error while getting parent for {name}, {err}")
        raise PanDeviceXapiError(f"Failed to retrieve parent for {name}, ")

    def retrieve_device_groups(self):
        """Returns all DeviceGroups."""
        self.device_groups = {}
        self.job.logger.info("Caching Device Groups from Panorama")
        self.device_groups = {i.name: i for i in self.pano.refresh_devices() if isinstance(i, DeviceGroup)}
        if self.job.debug:
            self.job.logger.debug(f"Cached Device Groups: {len(self.device_groups)}")
        return self.device_groups
