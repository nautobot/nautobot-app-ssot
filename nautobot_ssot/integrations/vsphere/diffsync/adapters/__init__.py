"""Collection of adapters."""

from .adapter_nautobot import NBAdapter
from .adapter_vsphere import VsphereDiffSync

__all__ = ("NBAdapter", "VsphereDiffSync")
