"""Base API SDK Class."""

from time import sleep

from panos.device import SystemSettings, Vsys
from panos.errors import PanDeviceXapiError
from panos.panorama import DeviceGroup


class BaseAPI:  # pylint: disable=too-few-public-methods
    """Create a base API for reuse."""

    def __init__(self, panorama, device_groups, job=None):
        """Init object with panorama instnace, job, & device group."""
        self.pano = panorama
        self.device_groups = device_groups
        self.job = job

    def _get_all_via_device_groups(self, obj_class, obj_type):
        exceptions = 0
        while exceptions < 3:
            if exceptions > 0:
                self.job.logger.warning(f"Retrying to cache {obj_class.__name__}...")
            try:
                output = {}
                for obj in obj_class.refreshall(self.pano):
                    output[obj.name] = {"value": obj, "type": obj_type, "location": "shared"}
                for group in self.device_groups.values():
                    for obj in obj_class.refreshall(group):
                        output[obj.name] = {"value": obj, "type": obj_type, "location": group.name}
                return output
            except Exception as err:
                self.job.logger.warning(f"Error while caching {obj_class.__name__}, {err}")
                exceptions += 1
                sleep(exceptions * 1.5)
        raise PanDeviceXapiError(f"Failed to cache {obj_class.__name__}")

    def _get_vsys_object(self, firewall_obj):  # pylint: disable=R1710
        """Refresh all the Vsys on a Firewall and get the Vsys object matching the assigned Vsys name."""
        vsys_name = firewall_obj.vsys if firewall_obj.vsys else "vsys1"
        try:
            vsys_objects = Vsys.refreshall(firewall_obj)
            for vsys in vsys_objects:
                if vsys.name == vsys_name:
                    return vsys
        except Exception as err:
            self.job.logger.warning(f"Error refreshing Vsys, {err}")
            return None

    def _get_firewalls_via_device_groups(self, obj_class, obj_type):
        """
        Retrieve firewall objects from device groups and return them as structured dictionaries.

        This method attempts to collect firewall objects by refreshing the provided object class
        across all device groups. It will retry up to 3 times if exceptions occur, with a backoff
        delay between attempts.

        Args:
            obj_class: The class of objects to retrieve (e.g., Firewall)
            obj_type: The type identifier string for the retrieved objects
        Returns:
            list: A list of dictionaries, each containing:
                - name (str): The hostname of the firewall or its serial if hostname is unavailable
                - value (obj): The actual firewall object
                - type (str): The object type as passed in obj_type
                - vsys_name (str): The vsys name of the firewall
                - vsys_obj: The vsys object associated with the firewall
                - location (str): Device group name where the firewall is located
        Raises:
            PanDeviceXapiError: If unable to retrieve objects after 3 attempts
        """
        exceptions = 0
        while exceptions < 3:  # pylint: disable=too-many-nested-blocks
            if exceptions > 0:
                self.job.logger.warning(f"Retrying to cache {obj_class.__name__}...")
            try:
                output = []
                seen_serials = set()
                for group in self.device_groups.values():
                    for obj in obj_class.refreshall(group):
                        try:
                            # If the user specified specific devices to sync, skip any devices that do not match
                            if self.job.filtered_device_serials and obj.serial not in self.job.filtered_device_serials:
                                continue
                            # Deduplicate, otherwise dup firewalls might arise with this data structure.
                            if obj.serial in seen_serials:
                                continue
                            seen_serials.add(obj.serial)
                            # Get the firewall hostname
                            obj_name = SystemSettings.refreshall(obj)[0].hostname
                        except PanDeviceXapiError:
                            obj_name = obj.serial
                        output.append(
                            {
                                "name": obj_name,
                                "value": obj,
                                "type": obj_type,
                                "vsys_name": obj.vsys if obj.vsys else "vsys1",
                                "vsys_obj": self._get_vsys_object(firewall_obj=obj),
                                "location": group.name,
                            }
                        )
                return output
            except Exception as err:
                self.job.logger.warning(f"Error while caching {obj_class.__name__}, {err}")
                exceptions += 1
                sleep(exceptions * 1.5)
        raise PanDeviceXapiError(f"Failed to cache {obj_class.__name__}")

    def _get_location(self, location):
        if not location:
            return self.pano
        if isinstance(location, str):
            return self.device_groups[location]
        if isinstance(location, DeviceGroup):
            return location
        raise ValueError("Invalid location.")
