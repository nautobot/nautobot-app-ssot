"""Constants for the Proxmox VE SSoT integration."""

from nautobot.dcim.choices import InterfaceTypeChoices

# SSoT tag applied to every synced object.
SSOT_TAG_NAME = "SSoT Synced from Proxmox"
SSOT_TAG_DESCRIPTION = "Object synced at some point from Proxmox VE to Nautobot"

# Custom field stamped with the date of the last sync.
SSOT_CUSTOM_FIELD_KEY = "last_synced_from_proxmox_on"
SSOT_CUSTOM_FIELD_LABEL = "Last synced from Proxmox on"

# Custom relationship linking a VirtualMachine to its host node Device (one-to-many).
HOST_RELATIONSHIP_LABEL = "Proxmox VM Host"
HOST_RELATIONSHIP_KEY = "proxmox_vm_host"

# Node hardware/version detail stored on the node Device's custom fields.
NODE_PVE_VERSION_CF = "proxmox_pve_version"
NODE_CPU_COUNT_CF = "proxmox_cpu_count"
NODE_MEMORY_GB_CF = "proxmox_memory_gb"

# ClusterType created for Proxmox VE clusters.
CLUSTER_TYPE_NAME = "Proxmox VE"

# Node-as-Device prerequisites created for Proxmox VE nodes.
NODE_MANUFACTURER_NAME = "Proxmox"
NODE_DEVICE_TYPE_NAME = "Proxmox Node"
NODE_DEVICE_ROLE_NAME = "Proxmox Node"
NODE_LOCATION_NAME = "Proxmox VE Default Location"

# Maps Proxmox VE node network interface types to Nautobot DCIM interface types.
NODE_INTERFACE_TYPE_MAP = {
    "eth": InterfaceTypeChoices.TYPE_1GE_FIXED,
    "bond": InterfaceTypeChoices.TYPE_LAG,
    "OVSBond": InterfaceTypeChoices.TYPE_LAG,
    "bridge": InterfaceTypeChoices.TYPE_BRIDGE,
    "OVSBridge": InterfaceTypeChoices.TYPE_BRIDGE,
    "vlan": InterfaceTypeChoices.TYPE_VIRTUAL,
}
