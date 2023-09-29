"""DiffSync model class definitions for nautobot-ssot-device42."""

from nautobot_ssot.integrations.device42.diffsync.models.base.assets import (
    PatchPanel,
    PatchPanelFrontPort,
    PatchPanelRearPort,
)
from nautobot_ssot.integrations.device42.diffsync.models.base.circuits import Circuit, Provider
from nautobot_ssot.integrations.device42.diffsync.models.base.dcim import (
    Building,
    Cluster,
    Connection,
    Device,
    Hardware,
    Port,
    Rack,
    Room,
    Vendor,
)
from nautobot_ssot.integrations.device42.diffsync.models.base.ipam import VLAN, IPAddress, Subnet, VRFGroup
from nautobot_ssot.integrations.device42.diffsync.models.nautobot.assets import (
    NautobotPatchPanel,
    NautobotPatchPanelFrontPort,
    NautobotPatchPanelRearPort,
)
from nautobot_ssot.integrations.device42.diffsync.models.nautobot.circuits import NautobotCircuit, NautobotProvider
from nautobot_ssot.integrations.device42.diffsync.models.nautobot.dcim import (
    NautobotBuilding,
    NautobotCluster,
    NautobotConnection,
    NautobotDevice,
    NautobotHardware,
    NautobotPort,
    NautobotRack,
    NautobotRoom,
    NautobotVendor,
)

__all__ = (
    "PatchPanel",
    "PatchPanelFrontPort",
    "PatchPanelRearPort",
    "Provider",
    "Circuit",
    "Building",
    "Room",
    "Rack",
    "Vendor",
    "Hardware",
    "Cluster",
    "Device",
    "Port",
    "Connection",
    "VRFGroup",
    "Subnet",
    "IPAddress",
    "VLAN",
    "NautobotCircuit",
    "NautobotProvider",
    "NautobotPatchPanel",
    "NautobotPatchPanelFrontPort",
    "NautobotPatchPanelRearPort",
    "NautobotBuilding",
    "NautobotCluster",
    "NautobotConnection",
    "NautobotDevice",
    "NautobotHardware",
    "NautobotPort",
    "NautobotRack",
    "NautobotRoom",
    "NautobotVendor",
)
