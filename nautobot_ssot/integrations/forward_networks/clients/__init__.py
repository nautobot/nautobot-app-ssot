"""Forward Networks API client package."""

from nautobot_ssot.integrations.forward_networks.clients.client import ForwardNetworksClient
from nautobot_ssot.integrations.forward_networks.clients.collection import CollectionAPI
from nautobot_ssot.integrations.forward_networks.clients.device_tags import DeviceTagsAPI
from nautobot_ssot.integrations.forward_networks.clients.devices import DevicesAPI
from nautobot_ssot.integrations.forward_networks.clients.locations import LocationsAPI
from nautobot_ssot.integrations.forward_networks.clients.networks import NetworkAPI
from nautobot_ssot.integrations.forward_networks.clients.nqe import NQEAPI
from nautobot_ssot.integrations.forward_networks.clients.snapshots import SnapshotsAPI

__all__ = (
    "ForwardNetworksClient",
    "CollectionAPI",
    "DevicesAPI",
    "DeviceTagsAPI",
    "LocationsAPI",
    "NetworkAPI",
    "NQEAPI",
    "SnapshotsAPI",
)
