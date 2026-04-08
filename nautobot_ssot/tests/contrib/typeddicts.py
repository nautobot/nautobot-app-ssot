"""Tests for contrib.NautobotModel."""

from typing import TypedDict


class SoftwareImageFileDict(TypedDict):
    """Example software image file dict."""

    image_file_name: str


class TagDict(TypedDict):
    """Exampe tag Dict."""

    name: str


class DeviceDict(TypedDict):
    """Example device dict."""

    name: str
