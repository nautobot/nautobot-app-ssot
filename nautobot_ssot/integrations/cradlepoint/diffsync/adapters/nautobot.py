"""Nautobot Adapter for Cradlepoint Integration."""

from nautobot_ssot.contrib import NautobotAdapter
from nautobot_ssot.integrations.cradlepoint.diffsync.models.nautobot import BaseAdapter


class NautobotTargetAdapter(BaseAdapter, NautobotAdapter):
    """Nautobot Adapter for vSphere SSoT."""

    def __init__(self, *args, job=None, sync=None, config, **kwargs):
        """Initialize the adapter."""
        super().__init__(*args, job=job, sync=sync, **kwargs)
        # TODO: Is this config attr really needed on the Nautobot adapter? If not, can get rid of this overload
        self.config = config

    def load_param_mac_address(self, parameter_name, database_object):
        """Force mac address to string when loading it into the diffsync store."""
        return str(getattr(database_object, parameter_name))
