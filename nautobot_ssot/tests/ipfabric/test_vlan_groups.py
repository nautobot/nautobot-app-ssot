"""Tests for the VLAN Group a Location's VLANs are filed under.

Nautobot enforces `(vlan_group, vid)` and `(vlan_group, name)` and enforces neither where a VLAN has
no group, so the group is what makes one VLAN ID mean one VLAN at a Location.
"""

import unittest.mock

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device, Location, LocationType
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Status
from nautobot.ipam.models import VLAN, VLANGroup

from nautobot_ssot.integrations.ipfabric.utilities.nbutils import create_vlan, get_vlan_group_for_location
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache


class _VlanGroupTestCase(TestCase):
    """A Location whose LocationType holds VLANs, with two of them already there."""

    def setUp(self):
        populate_status_choices()
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        self.active = Status.objects.get(name="Active")
        location_type, _ = LocationType.objects.get_or_create(name="group-site")
        location_type.content_types.add(
            ContentType.objects.get_for_model(Device), ContentType.objects.get_for_model(VLAN)
        )
        self.location = Location.objects.create(name="group-site1", location_type=location_type, status=self.active)
        self.vlans = {}
        for vid in (10, 20):
            vlan = VLAN.objects.create(name=f"vlan{vid}", vid=vid, status=self.active)
            vlan.locations.add(self.location)
            self.vlans[vid] = vlan


class TestVlanGroupPerLocation(_VlanGroupTestCase):
    """A Location's VLANs belong in a Group of its own, which is what constrains the VLAN ID.

    Nautobot enforces `(vlan_group, vid)` and `(vlan_group, name)` and enforces neither where the
    group is null, so without one a Location can hold two VLANs of the same ID.
    """

    def create(self, vid, name, group=None):
        """Run `create_vlan` for this test's Location."""
        return create_vlan(
            vlan_name=name,
            vlan_id=vid,
            vlan_status="Active",
            location_obj=self.location,
            description="",
            vlan_group=group,
        )

    def test_a_group_is_created_for_the_location_and_named_after_it(self):
        group = get_vlan_group_for_location(self.location, create=True)

        self.assertIsNotNone(group)
        self.assertEqual(group.name, self.location.name)
        self.assertEqual(group.location, self.location)

    def test_the_same_group_is_returned_on_a_later_run(self):
        first = get_vlan_group_for_location(self.location, create=True)
        job_scoped_cache.clear_all()

        self.assertEqual(get_vlan_group_for_location(self.location, create=True), first)

    def test_a_group_of_that_name_at_another_location_is_left_alone(self):
        """A VLAN Group name is unique across Nautobot, so one elsewhere belongs to somebody else."""
        other = Location.objects.create(
            name="other-site", location_type=self.location.location_type, status=self.active
        )
        VLANGroup.objects.create(name=self.location.name, location=other)
        logger = unittest.mock.MagicMock()

        self.assertIsNone(get_vlan_group_for_location(self.location, create=True, logger=logger))
        self.assertIn("already belongs to another Location", str(logger.warning.call_args_list))

    def test_strictness_reports_a_missing_group_rather_than_creating_one(self):
        logger = unittest.mock.MagicMock()

        self.assertIsNone(get_vlan_group_for_location(self.location, create=False, logger=logger))
        self.assertFalse(VLANGroup.objects.filter(name=self.location.name).exists())
        self.assertIn("No VLAN Group named", str(logger.warning.call_args_list))

    def test_a_new_vlan_is_filed_under_the_group(self):
        group = get_vlan_group_for_location(self.location, create=True)

        vlan = self.create(30, "new-vlan", group=group)

        self.assertEqual(vlan.vlan_group, group)

    def test_a_vlan_that_predates_the_group_is_adopted_into_it(self):
        """The constraint only covers what is actually in the group."""
        group = get_vlan_group_for_location(self.location, create=True)
        self.assertIsNone(self.vlans[10].vlan_group, "Set up ungrouped, as an earlier sync left it.")

        self.create(10, self.vlans[10].name, group=group)

        self.vlans[10].refresh_from_db()
        self.assertEqual(self.vlans[10].vlan_group, group)

    def test_the_group_makes_a_duplicate_vlan_id_impossible(self):
        """What the whole change is for: the database refuses the second one."""
        group = get_vlan_group_for_location(self.location, create=True)
        self.create(10, self.vlans[10].name, group=group)

        with self.assertRaises(Exception):
            duplicate = VLAN(vid=10, name="another", status=self.active, vlan_group=group)
            duplicate.validated_save()

    def test_a_second_vlan_of_one_name_is_reported_and_skipped(self):
        """A group makes the name unique too, which it is not without one."""
        group = get_vlan_group_for_location(self.location, create=True)
        # A VLAN new to Nautobot, so the name given here is the one it is written under.
        self.create(30, "shared-name", group=group)
        logger = unittest.mock.MagicMock()

        refused = create_vlan(
            vlan_name="shared-name",
            vlan_id=40,
            vlan_status="Active",
            location_obj=self.location,
            description="",
            logger=logger,
            vlan_group=group,
        )

        self.assertIsNone(refused)
        reported = str(logger.error.call_args_list)
        self.assertIn("already holds a different VLAN named", reported)
        self.assertIn("shared-name", reported)
