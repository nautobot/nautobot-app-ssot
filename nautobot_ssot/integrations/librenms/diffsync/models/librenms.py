"""Nautobot Ssot Librenms DiffSync models for Nautobot Ssot Librenms SSoT."""

from nautobot.dcim.models import Device as NautobotDevice

from nautobot_ssot.integrations.librenms.diffsync.models.base import Device, Location


class LibrenmsLocation(Location):
    """LibreNMS implementation of Location DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Location in LibreNMS from LibrenmsLocation object."""
        if attrs["status"] == "Active" or attrs["status"] == "Staged":
            if attrs["latitude"] and attrs["longitude"]:
                location = {
                    "location": ids["name"],
                    "lat": attrs["latitude"],
                    "lng": attrs["longitude"],
                }
                adapter.job.logger.info(f"Creating location in LibreNMS: {location['location']}")
                adapter.lnms_api.create_librenms_location(location)
            else:
                adapter.job.logger.warning(
                    f"Skipping location in LibreNMS: {ids['name']}. Latitude or Longitude is not set, which LibreNMS requires."
                )
        else:
            if adapter.job.debug:
                adapter.job.logger.debug(
                    f"Skipping location in LibreNMS: {ids['name']}. Status is not Active or Staged."
                )
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Location in LibreNMS from LibrenmsLocation object."""
        if "latitude" in attrs or "longitude" in attrs:
            location = {
                "lat": attrs["latitude"],
                "lng": attrs["longitude"],
            }
            self.adapter.job.logger.info(f"Updating location in LibreNMS: {location}")
            self.adapter.lnms_api.update_librenms_location(location)
        return super().update(attrs)

    def delete(self):
        """Delete Location in LibreNMS from LibrenmsLocation object."""
        return self


class LibrenmsDevice(Device):
    """LibreNMS implementation of Device adapter model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Device in LibreNMS from LibrenmsDevice object."""
        if attrs["status"] == "Active" or attrs["status"] == "Staged":
            device_data = adapter.job.source_adapter.dict()["device"][ids["name"]]
            if device_data.get("ip_address"):
                device = {
                    "hostname": device_data["ip_address"],
                    "display": ids["name"],
                    "location": attrs["location"],
                }
                if adapter.job.force_add:
                    device["force_add"] = True
                if adapter.job.ping_fallback:
                    device["ping_fallback"] = True
                adapter.job.logger.info(f"Creating device in LibreNMS: {device['hostname']}")
                response = adapter.lnms_api.create_librenms_device(device)
                if response.get("status") == "error":
                    adapter.job.logger.error(f"Error creating device in LibreNMS: {response['message']}")
                elif response.get("status") == "ok" and response.get("devices"):
                    # Get the device ID from the first device in the devices array
                    librenms_device_id = response["devices"][0]["device_id"]
                    nautobot_device = NautobotDevice.objects.get(name=ids["name"])
                    nautobot_device.custom_field_data["librenms_device_id"] = librenms_device_id
                    nautobot_device.save()
            else:
                if adapter.job.debug:
                    adapter.job.logger.debug(
                        f"Skipping device in LibreNMS: {ids['name']}. No Primary IP address found."
                    )
        else:
            adapter.job.logger.info(f"Skipping device in LibreNMS: {ids['name']}. Status is not Active or Staged.")
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Device in LibreNMS from LibrenmsDevice object."""
        return super().update(attrs)

    def delete(self):
        """Delete Device in LibreNMS from LibrenmsDevice object."""
        return self
