"""Itential SSoT models."""

from nautobot_ssot.integrations.itential.diffsync.models import base


class ItentialAnsibleDeviceModel(base.BaseAnsibleDeviceDiffsyncModel):
    """Itential Ansible Device DiffSyncModel."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create device in Automation Gateway."""
        adapter.api_client.create_device(device_name=ids.get("name"), variables=attrs.get("variables"))
        adapter.api_client.add_device_to_group(group_name="all", device_name=ids.get("name"))
        return super().create(ids=ids, adapter=adapter, attrs=attrs)

    def delete(self):
        """Delete device in Automation Gateway."""
        self.adapter.api_client.delete_device_from_group(group_name="all", device_name=self.name)
        self.adapter.api_client.delete_device(device_name=self.name)
        return super().delete()

    def update(self, attrs):
        """Update device in Automation Gateway."""
        self.adapter.api_client.update_device(device_name=self.name, variables=attrs.get("variables"))
        return super().update(attrs)


class ItentialDefaultAnsibleGroupModel(base.BaseAnsibleDefaultGroupDiffsyncModel):
    """Itential Default Ansible Group DiffsyncModel."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create default group in Automation Gateway."""
        adapter.api_client.create_group(group_name=ids.get("name"), variables=attrs.get("variables"))
        return super().create(ids=ids, adapter=adapter, attrs=attrs)

    def update(self, attrs):
        """Update default group in Automation Gateway."""
        self.adapter.api_client.update_device(device_name=self.name, variables=attrs.get("variables"))
        return super().update(attrs)

    def delete(self):
        """Delete default group in Automation Gateway."""
        raise NotImplementedError
