"""Diffsync adapters for nautobot_ssot_uisp."""

from diffsync import Adapter

from nautobot_ssot_uisp.diffsync.models import DeviceSSoTModel


class UispRemoteAdapter(Adapter):
    """DiffSync adapter for UISP."""

    device = DeviceSSoTModel

    top_level = ["device"]

    def __init__(self, *args, job=None, sync=None, client=None, **kwargs):
        """Initialize UISP.

        Args:
            job (object, optional): UISP job. Defaults to None.
            sync (object, optional): UISP SSoT. Defaults to None.
            client (object): UISP API client connection object.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.conn = client

    def load(self):
        """Load data from UISP into SSoT models."""
        raise NotImplementedError()


class UispNautobotAdapter(NautobotAdapter):
    """DiffSync adapter for Nautobot."""

    device = DeviceSSoTModel

    top_level = ["device"]

    
