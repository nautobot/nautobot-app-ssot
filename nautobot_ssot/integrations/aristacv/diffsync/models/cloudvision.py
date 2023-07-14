"""Cloudvision DiffSync models for AristaCV SSoT."""
from nautobot_ssot.integrations.aristacv.constant import APP_SETTINGS
from nautobot_ssot.integrations.aristacv.diffsync.models.base import Device, CustomField, IPAddress, Port
from nautobot_ssot.integrations.aristacv.utils.cloudvision import CloudvisionApi


class CloudvisionDevice(Device):
    """Cloudvision Device model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Device in AristaCV from Device object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Device in AristaCV from Device object."""
        return super().update(attrs)

    def delete(self):
        """Delete Device in AristaCV from Device object."""
        return self


class CloudvisionPort(Port):
    """Cloudvision Port model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Interface in AristaCV from Port object."""
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Interface in AristaCV from Port object."""
        return super().update(attrs)

    def delete(self):
        """Delete Interface in AristaCV from Port object."""
        return self


class CloudvisionIPAddress(IPAddress):
    """Cloudvision IPAdress model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create IPAddress in AristaCV from IPAddress object."""
        ...
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update IPAddress in AristaCV from IPAddress object."""
        ...
        return super().update(attrs)

    def delete(self):
        """Delete IPAddress in AristaCV from IPAddress object."""
        ...
        return self


class CloudvisionCustomField(CustomField):
    """Cloudvision CustomField model."""

    @staticmethod
    def connect_cvp():
        """Connect to Cloudvision gRPC endpoint."""
        return CloudvisionApi(
            cvp_host=APP_SETTINGS["cvp_host"],
            cvp_port=APP_SETTINGS.get("cvp_port", "8443"),
            verify=APP_SETTINGS["verify"],
            username=APP_SETTINGS["cvp_user"],
            password=APP_SETTINGS["cvp_password"],
            cvp_token=APP_SETTINGS["cvp_token"],
        )

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create a user tag in cvp."""
        cvp = cls.connect_cvp()
        cvp.create_tag(ids["name"], attrs["value"])
        # Create mapping from device_name to CloudVision device_id
        device_ids = {dev["hostname"]: dev["device_id"] for dev in cvp.get_devices()}
        for device in attrs["devices"]:
            # Exclude devices that are inactive in CloudVision
            if device in device_ids:
                cvp.assign_tag_to_device(device_ids[device], ids["name"], attrs["value"])
            else:
                tag = f"{ids['name']}:{attrs['value']}" if attrs["value"] else ids["name"]
                diffsync.job.log_warning(
                    message=f"{device} is inactive or missing in CloudVision - skipping for tag: {tag}"
                )
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update user tag in cvp."""
        cvp = self.connect_cvp()
        remove = set(self.device_name) - set(attrs["devices"])
        add = set(attrs["devices"]) - set(self.device_name)
        # Create mapping from device_name to CloudVision device_id
        device_ids = {dev["hostname"]: dev["device_id"] for dev in cvp.get_devices()}
        for device in remove:
            cvp.remove_tag_from_device(device_ids[device], self.name, self.value)
        for device in add:
            # Exclude devices that are inactive in CloudVision
            if device in device_ids:
                cvp.assign_tag_to_device(device_ids[device], self.name, self.value)
            else:
                tag = f"{self.name}:{self.value}" if self.value else self.name
                self.diffsync.job.log_warning(
                    message=f"{device} is inactive or missing in CloudVision - skipping for tag: {tag}"
                )
        # Call the super().update() method to update the in-memory DiffSyncModel instance
        return super().update(attrs)

    def delete(self):
        """Delete user tag applied to devices in cvp."""
        cvp = self.connect_cvp()
        device_ids = {dev["hostname"]: dev["device_id"] for dev in cvp.get_devices()}
        for device in self.device_name:
            cvp.remove_tag_from_device(device_ids[device], self.name, self.value)
        cvp.delete_tag(self.name, self.value)
        # Call the super().delete() method to remove the DiffSyncModel instance from its parent DiffSync adapter
        super().delete()
        return self
