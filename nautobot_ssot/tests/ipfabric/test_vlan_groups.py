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

from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Vlan as VlanModel
from nautobot_ssot.integrations.ipfabric.utilities.nbutils import (
    create_vlan,
    get_vlan_group_for_location,
    vlan_group_is_attainable,
)
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


class TestAdoptingVlansThatPredateTheGroup(_VlanGroupTestCase):
    """What a real estate upgrades into: VLANs Nautobot already holds, filed under no group.

    The group reaching only the VLANs a run creates would leave those untouched and unconstrained,
    which is why being in a group is an attribute the diff reports rather than a side effect of
    creation.
    """

    def diff_model(self, vlan, may_create=True):
        """Return a Vlan model bound to a stub adapter, as the Nautobot side loads an existing VLAN."""
        adapter = unittest.mock.MagicMock()
        adapter.may_create.return_value = may_create
        model = VlanModel(
            vid=vlan.vid,
            location=self.location.name,
            name=vlan.name,
            status="Active",
            in_vlan_group=False,
            vlan_pk=vlan.pk,
        )
        model.adapter = adapter
        return model

    def test_a_vlan_is_adopted_although_nothing_else_about_it_changed(self):
        """The reported case: identity and attributes match, so only the group is left to apply."""
        vlan = self.vlans[10]
        self.assertIsNone(vlan.vlan_group)

        self.diff_model(vlan).update({"in_vlan_group": True})

        vlan.refresh_from_db()
        self.assertIsNotNone(vlan.vlan_group, "A VLAN that predates the group has to be moved into it.")
        self.assertEqual(vlan.vlan_group.name, self.location.name)

    def test_adopting_one_vlan_constrains_the_location(self):
        """The point of the group: a second VLAN of that ID can no longer be filed beside it."""
        self.diff_model(self.vlans[10]).update({"in_vlan_group": True})
        group = VLANGroup.objects.get(name=self.location.name)

        self.assertEqual(VLAN.objects.filter(vlan_group=group, vid=10).count(), 1)
        with self.assertRaises(Exception):
            VLAN(name="another", vid=10, status=self.active, vlan_group=group).validated_save()

    def test_a_vlan_already_in_a_group_is_left_where_it_is(self):
        """Re-filing would fight whatever put it there, and thrash a VLAN shared between Locations."""
        other = VLANGroup.objects.create(name="somebody-elses-group")
        vlan = self.vlans[20]
        vlan.vlan_group = other
        vlan.validated_save()

        self.diff_model(vlan).update({"in_vlan_group": True})

        vlan.refresh_from_db()
        self.assertEqual(vlan.vlan_group, other)

    def test_a_name_already_taken_in_the_group_leaves_the_vlan_ungrouped(self):
        """A group makes the name unique too, so the collision is reported rather than raised."""
        group = get_vlan_group_for_location(self.location, create=True)
        VLAN.objects.create(name="vlan10", vid=999, status=self.active, vlan_group=group)
        vlan = self.vlans[10]

        model = self.diff_model(vlan)
        model.update({"in_vlan_group": True})

        vlan.refresh_from_db()
        self.assertIsNone(vlan.vlan_group, "Filing it would have broken the name constraint.")
        model.adapter.job.logger.warning.assert_called()


class TestWhetherAGroupCanBeHadAtAll(_VlanGroupTestCase):
    """Both sides have to agree a group is out of reach, or the difference is diffed every run."""

    def test_a_location_whose_group_can_be_created(self):
        self.assertTrue(vlan_group_is_attainable(self.location.name, create=True))

    def test_a_group_of_that_name_owned_by_another_location_is_not_attainable(self):
        other_location = Location.objects.create(
            name="group-site2", location_type=self.location.location_type, status=self.active
        )
        VLANGroup.objects.create(name=self.location.name, location=other_location)

        self.assertFalse(vlan_group_is_attainable(self.location.name, create=False))
        self.assertFalse(
            vlan_group_is_attainable(self.location.name, create=True),
            "Creating is no help when the name is taken.",
        )

    def test_strictness_makes_a_missing_group_unattainable(self):
        self.assertFalse(vlan_group_is_attainable(self.location.name, create=False))

    def test_an_existing_group_at_this_location_is_attainable_under_strictness(self):
        get_vlan_group_for_location(self.location, create=True)

        self.assertTrue(vlan_group_is_attainable(self.location.name, create=False))
