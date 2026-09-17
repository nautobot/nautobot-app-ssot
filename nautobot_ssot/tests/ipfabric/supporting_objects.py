"""Shared scaffolding for the two controls that stop an IP Fabric sync creating a supporting object.

Manufacturers, Device Types, Roles, Platforms and Locations are created as a side effect of syncing a
Device. Two independent controls can withhold that: taking the type out of the sync scope, and being
strict about it. Both funnel through `DiffSyncModelAdapters.may_create`, so what the sync does when
the supporting object is absent is one behaviour reached two ways, and the fixture that sets up a
Nautobot holding some supporting objects and not others is the same for both.

Named without a `test_` prefix so the runner does not collect it. `test_supporting_object_scope.py`
and `test_strict_mode.py` supply the control; this supplies the estate they run against.
"""

import unittest.mock

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer, Platform, VirtualChassis
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import CustomField, Role, Status

from nautobot_ssot.integrations.ipfabric.diffsync.adapters_shared import DiffSyncModelAdapters
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Device as DeviceModel
from nautobot_ssot.integrations.ipfabric.sync_scope import SYNCABLE_OBJECTS, SyncScope
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache

KNOWN_VENDOR = "known-vendor"
KNOWN_MODEL = "known-model"
KNOWN_ROLE = "known-role"
KNOWN_PLATFORM = "known-platform"
KNOWN_STACK = "known-stack"

UNKNOWN_VENDOR = "unknown-vendor"
UNKNOWN_MODEL = "unknown-model"
UNKNOWN_ROLE = "unknown-role"
UNKNOWN_PLATFORM = "unknown-platform"
UNKNOWN_STACK = "unknown-stack"
UNKNOWN_LOCATION = "unknown-site"


def scope_without(*keys):
    """Return a scope with every object type selected except the named ones."""
    return SyncScope(syncable.key for syncable in SYNCABLE_OBJECTS if syncable.key not in keys)


class SupportingObjectTestCase(TestCase):
    """Create Devices against a Nautobot that holds some supporting objects and not others."""

    def setUp(self):
        # Helpers memoize real ORM objects, which would outlive this test's transaction.
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)

        populate_status_choices()
        self.active_status = Status.objects.get(name="Active")
        device_ct = ContentType.objects.get_for_model(Device)

        self.manufacturer = Manufacturer.objects.create(name=KNOWN_VENDOR)
        self.device_type = DeviceType.objects.create(model=KNOWN_MODEL, manufacturer=self.manufacturer)
        self.platform = Platform.objects.create(name=KNOWN_PLATFORM, manufacturer=self.manufacturer)
        VirtualChassis.objects.create(name=KNOWN_STACK)

        # `get_or_create_device_role_object` matches on this custom field rather than the name.
        role_cf, _ = CustomField.objects.get_or_create(
            type=CustomFieldTypeChoices.TYPE_TEXT,
            key="ipfabric_type",
            defaults={"label": "IPFabric Type"},
        )
        role_cf.content_types.add(ContentType.objects.get_for_model(Role))
        self.role = Role.objects.create(name=KNOWN_ROLE)
        self.role.content_types.add(device_ct)
        self.role.cf["ipfabric_type"] = KNOWN_ROLE
        self.role.validated_save()

        site_type, _ = LocationType.objects.get_or_create(name="Site")
        site_type.content_types.add(device_ct)
        self.location = Location.objects.create(name="site1", location_type=site_type, status=self.active_status)

        # A real Adapter, since `DiffSyncModel.create` validates the type; only the job is mocked.
        self.adapter = DiffSyncModelAdapters(scope=scope_without())
        self.adapter.job = unittest.mock.MagicMock()

    def create_device(self, name="dev1", **overrides):
        """Run `Device.create` for a Device whose supporting objects default to the known ones."""
        attrs = {
            "location_name": self.location.name,
            "model": KNOWN_MODEL,
            "vendor": KNOWN_VENDOR,
            "role": KNOWN_ROLE,
            "status": "Active",
            "platform": KNOWN_PLATFORM,
            "serial_number": "abc123",
        }
        attrs.update(overrides)
        return DeviceModel.create(self.adapter, ids={"name": name}, attrs=attrs)

    def assert_warned(self, fragment):
        """Assert the job logged a warning containing the given text."""
        logged = [str(call) for call in self.adapter.job.logger.warning.call_args_list]
        self.assertTrue(
            any(fragment in line for line in logged), f"Expected a warning containing {fragment!r}: {logged}"
        )
