"""Unit tests for the IPFabric DiffSync adapter class."""
import unittest

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from nautobot.dcim.models import (
    Device,
    DeviceType,
    Location,
    LocationType,
    Manufacturer,
    Platform,
)
from nautobot.extras.models import Role, Status

from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync


class TestNautobotAdapter(TestCase):
    """Test cases for InfoBlox Nautobot adapter."""

    def setUp(self):
        device_ct = ContentType.objects.get_for_model(Device)
        active_status = Status.objects.get(name="Active")
        role = Role.objects.create(name="test")
        role.content_types.add(device_ct)
        site_lt, _ = LocationType.objects.get_or_create(name="site")
        site_lt.content_types.add(device_ct)
        self.site1 = Location.objects.create(name="site1", location_type=site_lt, status=active_status)
        site2 = Location.objects.create(name="site2", location_type=site_lt, status=active_status)
        man1 = Manufacturer.objects.create(name="man1")
        man2 = Manufacturer.objects.create(name="man2")
        dev_type1 = DeviceType.objects.create(model="dev_type1", manufacturer=man1)
        dev_type2 = DeviceType.objects.create(model="dev_type2", manufacturer=man2)
        platform1 = Platform.objects.create(name="platform1", manufacturer=man1)
        Device.objects.create(
            name="dev1",
            serial="abc",
            status=active_status,
            role=role,
            location=self.site1,
            device_type=dev_type1,
            platform=platform1,
        )
        Device.objects.create(
            name="dev2",
            serial="def",
            status=active_status,
            role=role,
            location=self.site1,
            device_type=dev_type1,
            platform=platform1,
        )
        Device.objects.create(
            name="dev3",
            serial="xyz",
            status=active_status,
            role=role,
            location=site2,
            device_type=dev_type2,
        )
        self.nb_adapter = NautobotDiffSync(
            job=unittest.mock.Mock(),
            sync=unittest.mock.Mock(),
            sync_ipfabric_tagged_only=False,
            location_filter=None,
        )
