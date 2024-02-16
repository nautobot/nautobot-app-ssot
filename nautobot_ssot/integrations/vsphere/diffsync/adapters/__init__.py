"""Collection of adapters."""

from .adapter_nautobot import Adapter
from .adapter_vsphere import VsphereDiffSync

__all__ = ("Adapter", "VsphereDiffSync")
