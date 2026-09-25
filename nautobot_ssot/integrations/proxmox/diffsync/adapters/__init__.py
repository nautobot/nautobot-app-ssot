"""Collection of adapters."""

from .adapter_nautobot import NBAdapter
from .adapter_proxmox import ProxmoxDiffSync

__all__ = ("NBAdapter", "ProxmoxDiffSync")
