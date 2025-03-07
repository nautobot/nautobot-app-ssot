"""Nautobot Adapter for Cradlepoint Integration."""
from nautobot_ssot.contrib import NautobotAdapter
from nautobot_ssot.integrations.cradlepoint.diffsync.models.cradlepoint import (
    CradlepointDevice,
    CradlepointDeviceType,
    CradlepointRole,
    CradlepointStatus,
)


class Adapter(NautobotAdapter):
    """Nautobot Adapter for vSphere SSoT."""

    status = CradlepointStatus
    role = CradlepointRole
    device_type = CradlepointDeviceType
    device = CradlepointDevice

    top_level = ("status", "role", "device_type", "device")

    def __init__(self, *args, job=None, sync=None, config, **kwargs):
        """Initialize the adapter."""
        super().__init__(*args, job=job, sync=sync, **kwargs)
        self.config = config

    def load_param_mac_address(self, parameter_name, database_object):
        """Force mac address to string when loading it into the diffsync store."""
        return str(getattr(database_object, parameter_name))

    # def sync_complete(self, source, diff, flags: DiffSyncFlags = DiffSyncFlags.NONE, logger=None):
    #     """Update devices with their primary IPs once the sync is complete."""
    #     for info in self._primary_ips:
    #         vm = VirtualMachine.objects.get(**info["device"])
    #         for ip in ["primary_ip4", "primary_ip6"]:
    #             if info[ip]:
    #                 setattr(vm, ip, IPAddress.objects.get(host=info[ip]))
    #         vm.validated_save()

    # def _load_objects(self, diffsync_model):
    #     """Overriding _load_objects so we can pass in the config object to the models."""
    #     parameter_names = self._get_parameter_names(diffsync_model)
    #     for database_object in diffsync_model._get_queryset(self.config, self.cluster_filters):
    #         self._load_single_object(database_object, diffsync_model, parameter_names)
