# pylint: disable=too-many-lines
"""Tests for IPFabric diffsync models.

Focused on the model-specific branching logic — early returns, conditional
calls, regression guards for fixed bugs. Nautobot ORM calls and the
`nbutils` helpers are mocked; the heavy lifting is covered by their own
test suites.
"""

import contextlib
from types import SimpleNamespace
from unittest import mock
from uuid import UUID

from django.test import SimpleTestCase

from nautobot_ssot.integrations.ipfabric.diffsync import diffsync_models
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import (
    Cable,
    Device,
    DiffSyncExtras,
    Interface,
    Location,
    Vlan,
)
from nautobot_ssot.integrations.ipfabric.sync_scope import SYNCABLE_OBJECTS, SyncScope

# ============================================================
# Shared helpers
# ============================================================

_UNSET = object()
_NBUTILS = "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils"
_CABLES = "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_cables"


def _nb_patch(name, **kwargs):
    """Patch a helper attribute on `tonb_nbutils` referenced from the model module."""
    return mock.patch(f"{_NBUTILS}.{name}", **kwargs)


def _cable_patch(name, **kwargs):
    """Patch a helper attribute on `tonb_cables` referenced from the model module."""
    return mock.patch(f"{_CABLES}.{name}", **kwargs)


def _make_adapter(scope=None):
    """Minimal mock adapter sufficient for invoking model methods directly.

    Carries a real `SyncScope` rather than a mock, since the resolvers branch on it and a mock reads
    as every object type being in scope whether or not that is what the test meant.
    """
    adapter = mock.MagicMock()
    adapter.scope = scope if scope is not None else SyncScope(syncable.key for syncable in SYNCABLE_OBJECTS)
    adapter.job = mock.MagicMock()
    adapter.job.debug = False
    adapter.ssot_tag = mock.MagicMock(name="ssot_tag")
    adapter.safe_delete_tag = mock.MagicMock(name="safe_delete_tag")
    adapter.safe_delete_tag.id = "tag-uuid"
    return adapter


def _active_device_mock():
    """Return a Nautobot Device mock whose status reads 'Active'."""
    nb_device = mock.MagicMock()
    nb_device.status.name = "Active"
    return nb_device


# Maps the kwargs `_patch_device_create_helpers` accepts to the helpers they stand for.
_CREATE_HELPERS = {
    "device_type": "get_or_create_device_type_object",
    "role": "get_or_create_device_role_object",
    "status": "get_or_create_status_object",
    "location": "get_or_create_location_object",
    "platform": "get_or_create_platform_object",
    "manufacturer": "get_or_create_manufacturer_object",
}

# Lookup-only helpers, which run first in the resolvers. Patched to return None so that the
# get-or-create path is the one each test exercises.
_CREATE_LOOKUPS = (
    "get_device_type_object",
    "get_device_role_object",
    "get_location_object",
    "get_platform_object",
    "get_manufacturer_object",
)


@contextlib.contextmanager
def _patch_device_create_helpers(**overrides):
    """Patch the `Device.create` collaborator helpers in one shot.

    Each kwarg names an entry in `_CREATE_HELPERS` and overrides that helper's `return_value`. An
    unnamed helper returns a fresh `MagicMock()`; pass `None` to trigger its failure branch. The
    yielded namespace exposes every patch under its full helper name.
    """
    unknown = set(overrides) - set(_CREATE_HELPERS)
    assert not unknown, f"Unknown helper override(s): {sorted(unknown)}"

    with contextlib.ExitStack() as stack:
        ns = SimpleNamespace()
        for kwarg, helper_name in _CREATE_HELPERS.items():
            return_value = overrides.get(kwarg, _UNSET)
            if return_value is _UNSET:
                return_value = mock.MagicMock()
            setattr(ns, helper_name, stack.enter_context(_nb_patch(helper_name, return_value=return_value)))
        for helper_name in _CREATE_LOOKUPS:
            setattr(ns, helper_name, stack.enter_context(_nb_patch(helper_name, return_value=None)))
        yield ns


class _ModelTestBase(SimpleTestCase):
    """Shared scaffolding for diffsync model tests."""

    def setUp(self):
        self.adapter = _make_adapter()

    def _assert_log_contains(self, logger_method, fragment):
        """Assert at least one call to `logger_method` contains the substring `fragment`."""
        self.assertTrue(
            any(fragment in str(c.args[0]) for c in logger_method.call_args_list),
            f"Expected log containing {fragment!r}; got {logger_method.call_args_list!r}",
        )


# ============================================================
# DiffSyncExtras.safe_delete
# ============================================================


class TestSafeDelete(_ModelTestBase):
    """Test `DiffSyncExtras.safe_delete` branching logic."""

    def setUp(self):
        super().setUp()
        # Vlan is the smallest model; safe_delete is defined on the shared base.
        self.diff_model = Vlan(name="v", vid=10, status="Active", location="loc")
        self.diff_model.adapter = self.adapter

    @_nb_patch("get_tagged_pks", return_value=frozenset())
    @_nb_patch("tag_object")
    @_nb_patch("get_or_create_status_object")
    def test_safe_delete_changes_status_and_tags_when_status_differs(
        self, mock_status, mock_tag_object, _mock_tagged_pks
    ):
        """Status differs -> status updated, safe delete tag passed to tag_object, called once."""
        mock_status.return_value = "safe-deleted-status"
        nb_obj = mock.MagicMock()
        nb_obj.status = "active-status"

        self.diff_model.safe_delete(nb_obj, "Decommissioning", self.adapter.safe_delete_tag)

        self.assertEqual(nb_obj.status, "safe-deleted-status")
        # The tag is applied by `tag_object`, alongside the synced from tag, in one call.
        mock_tag_object.assert_called_once()
        self.assertEqual(mock_tag_object.call_args.kwargs["extra_tags"], (self.adapter.safe_delete_tag,))

    @_nb_patch("tag_object")
    @_nb_patch("get_or_create_status_object")
    def test_safe_delete_skips_when_tag_already_present_and_status_unchanged(self, mock_status, mock_tag_object):
        """Tag already on object and status already correct -> no save, no tag_object."""
        mock_status.return_value = "safe-deleted-status"
        nb_obj = mock.MagicMock()
        nb_obj.status = "safe-deleted-status"  # already matches

        with _nb_patch("get_tagged_pks", return_value=frozenset({nb_obj.pk})):
            self.diff_model.safe_delete(nb_obj, "Decommissioning", self.adapter.safe_delete_tag)

        nb_obj.tags.add.assert_not_called()
        mock_tag_object.assert_not_called()

    @_nb_patch("tag_object")
    def test_safe_delete_no_tag_arg_is_a_noop_for_tagging(self, mock_tag_object):
        """Defensive guard: when safe_delete_tag is None, tags.add is never called."""
        nb_obj = mock.MagicMock(spec=["tags"])  # has tags but no status attr

        self.diff_model.safe_delete(nb_obj, safe_delete_status=None, safe_delete_tag=None)

        nb_obj.tags.add.assert_not_called()
        mock_tag_object.assert_not_called()


# ============================================================
# Location lifecycle
# ============================================================


class TestLocationModel(_ModelTestBase):
    """Test `Location.create/update/delete` branching logic."""

    @_nb_patch("get_or_create_location_object", return_value=None)
    def test_create_returns_none_when_helper_fails(self, _mock_helper):
        """If `get_or_create_location_object` returns None, `create` returns None and skips super()."""
        with mock.patch.object(diffsync_models.DiffSyncModel, "create") as mock_super:
            result = Location.create(
                adapter=self.adapter,
                ids={"name": "X"},
                attrs={"site_id": "Y", "status": "Active"},
            )
        self.assertIsNone(result)
        mock_super.assert_not_called()

    @_nb_patch("get_or_create_location_object")
    def test_create_calls_super_when_helper_succeeds(self, mock_helper):
        """Successful helper call leads to super().create() being invoked."""
        mock_helper.return_value = mock.MagicMock()
        with mock.patch.object(diffsync_models.DiffSyncModel, "create", return_value="created") as mock_super:
            result = Location.create(
                adapter=self.adapter,
                ids={"name": "X"},
                attrs={"site_id": "Y", "status": "Active"},
            )
        self.assertEqual(result, "created")
        mock_super.assert_called_once()

    def test_delete_returns_none_when_location_does_not_exist(self):
        """DoesNotExist lookup -> logged and super().delete() not invoked."""
        diff_model = Location(name="missing", site_id=None, status="Active")
        diff_model.adapter = self.adapter

        with (
            mock.patch.object(
                diffsync_models.NautobotLocation.objects,
                "get",
                side_effect=diffsync_models.NautobotLocation.DoesNotExist,
            ),
            mock.patch.object(diffsync_models.DiffSyncModel, "delete") as mock_super_delete,
        ):
            result = diff_model.delete()

        self.assertIsNone(result)
        mock_super_delete.assert_not_called()
        self.adapter.job.logger.error.assert_called_once()

    def test_update_status_active_sets_status_and_removes_safe_tag(self):
        """Status flip to Active rewrites status and removes the safe-delete tag."""
        diff_model = Location(name="X", site_id=None, status="Decommissioning")
        diff_model.adapter = self.adapter

        nb_loc = mock.MagicMock()
        nb_loc.status = "Decommissioning"  # differs from "Active"

        with (
            mock.patch.object(diffsync_models.NautobotLocation.objects, "get", return_value=nb_loc),
            _nb_patch("get_or_create_status_object", return_value="active-status-obj") as mock_status,
            _nb_patch("tag_object"),
            mock.patch.object(diffsync_models.DiffSyncModel, "update", return_value="ok"),
        ):
            result = diff_model.update({"status": "Active"})

        mock_status.assert_called_once()
        self.assertEqual(nb_loc.status, "active-status-obj")
        nb_loc.tags.remove.assert_called_once_with(self.adapter.safe_delete_tag)
        self.assertEqual(result, "ok")


# ============================================================
# Device lifecycle
# ============================================================


class TestSupportingObjectResolvers(_ModelTestBase):
    """Unit tests for the resolvers that turn a get-or-create into a lookup."""

    def test_resolve_platform_needs_a_manufacturer_to_create_under(self):
        """In scope but with no Manufacturer resolved, there is nothing to file a new Platform under."""
        self.assertIsNone(diffsync_models.resolve_platform(self.adapter, "ios", None))

    def test_resolve_platform_out_of_scope_ignores_the_manufacturer(self):
        """Out of scope the Platform is matched on its name, so a missing Manufacturer is no obstacle."""
        self.adapter.scope = SyncScope(syncable.key for syncable in SYNCABLE_OBJECTS if syncable.key != "platforms")
        with _nb_patch("get_platform_object", return_value="found") as mock_lookup:
            self.assertEqual(diffsync_models.resolve_platform(self.adapter, "ios", None), "found")
        mock_lookup.assert_called_once_with("ios", logger=self.adapter.job.logger)


class TestDeviceModel(_ModelTestBase):  # pylint: disable=too-many-public-methods
    """Test `Device.create/update` branching and regression guards."""

    _BASE_CREATE_ATTRS = {"model": "m", "vendor": "v", "location_name": "loc"}

    def _call_device_create(self, **attr_overrides):
        """Invoke `Device.create` with the standard ids and attrs (with overrides merged in)."""
        attrs = {**self._BASE_CREATE_ATTRS, **attr_overrides}
        return Device.create(adapter=self.adapter, ids={"name": "d1"}, attrs=attrs)

    def test_create_short_circuits_when_location_missing(self):
        """Any required helper returning None means Device.create returns None without saving."""
        with (
            _patch_device_create_helpers(location=None),
            mock.patch.object(diffsync_models.NautobotDevice.objects, "get_or_create") as mock_get_or_create,
        ):
            result = self._call_device_create()

        self.assertIsNone(result)
        mock_get_or_create.assert_not_called()

    def test_create_skips_role_cf_save_when_value_already_matches(self):
        """Regression: Role.validated_save() must not run when cf['ipfabric_type'] already matches role_name."""
        role_obj = mock.MagicMock()
        role_obj.cf.get.return_value = "DesiredRole"  # already matches

        # Force bail before super() by making location lookup fail
        with (
            _patch_device_create_helpers(role=role_obj, location=None),
        ):
            self._call_device_create(role="DesiredRole")

        role_obj.validated_save.assert_not_called()
        role_obj.cf.__setitem__.assert_not_called()

    def test_create_writes_and_saves_role_cf_when_value_differs(self):
        """When cf['ipfabric_type'] does not match, set it and run validated_save() exactly once."""
        role_obj = mock.MagicMock()
        role_obj.cf.get.return_value = "OldRole"  # differs from DesiredRole

        with (
            _patch_device_create_helpers(role=role_obj, location=None),
        ):
            self._call_device_create(role="DesiredRole")

        role_obj.cf.__setitem__.assert_called_once_with("ipfabric_type", "DesiredRole")
        role_obj.validated_save.assert_called_once()

    def test_create_uses_helper_when_no_devicetype_exists(self):
        """No existing DeviceType -> calls `get_or_create_device_type_object` helper."""
        manufacturer = mock.MagicMock()
        # location=None bails early, after the DeviceType has been resolved
        with _patch_device_create_helpers(location=None, manufacturer=manufacturer) as helpers:
            self._call_device_create()

        helpers.get_or_create_device_type_object.assert_called_once_with(
            device_type="m", vendor_name="v", logger=self.adapter.job.logger, manufacturer_obj=manufacturer
        )

    def test_create_reuses_an_existing_devicetype(self):
        """An existing DeviceType is used whatever the scope, without a create being attempted."""
        existing = mock.MagicMock()
        with _patch_device_create_helpers(location=None) as helpers:
            helpers.get_device_type_object.return_value = existing
            self._call_device_create()

        helpers.get_or_create_device_type_object.assert_not_called()

    def test_create_does_not_create_a_devicetype_out_of_scope(self):
        """Deselecting Device Types stops one being created for a model Nautobot does not have."""
        self.adapter.scope = SyncScope(syncable.key for syncable in SYNCABLE_OBJECTS if syncable.key != "device_types")
        with _patch_device_create_helpers(location=None) as helpers:
            result = self._call_device_create()

        helpers.get_or_create_device_type_object.assert_not_called()
        self.assertIsNone(result)
        self._assert_log_contains(self.adapter.job.logger.warning, "DeviceType")

    def test_create_does_not_create_a_manufacturer_out_of_scope(self):
        """A sync told not to add vendors must not add one in order to add a Device Type."""
        self.adapter.scope = SyncScope(syncable.key for syncable in SYNCABLE_OBJECTS if syncable.key != "manufacturers")
        with _patch_device_create_helpers(location=None) as helpers:
            self._call_device_create()

        helpers.get_or_create_manufacturer_object.assert_not_called()
        helpers.get_or_create_device_type_object.assert_not_called()
        self._assert_log_contains(self.adapter.job.logger.warning, "no Manufacturer named v could be resolved")

    def test_create_warns_when_devicetype_helper_returns_none(self):
        """DeviceType helper also fails -> warning logged."""
        with _patch_device_create_helpers(device_type=None):
            result = self._call_device_create()

        self.assertIsNone(result)
        self._assert_log_contains(self.adapter.job.logger.warning, "DeviceType")

    def test_create_warns_when_platform_helper_returns_none(self):
        """Platform + device_type_object both set -> helper called; None return warns."""
        device_type_obj = mock.MagicMock()
        with _patch_device_create_helpers(platform=None, location=None) as helpers:
            helpers.get_device_type_object.return_value = device_type_obj
            self._call_device_create(platform="ios")

        helpers.get_or_create_platform_object.assert_called_once()
        self._assert_log_contains(self.adapter.job.logger.warning, "will not have a Platform assigned")

    def test_create_warns_when_platform_set_but_devicetype_missing(self):
        """No device_type_object but platform supplied -> warning."""
        with _patch_device_create_helpers(device_type=None):
            self._call_device_create(platform="ios")

        self._assert_log_contains(self.adapter.job.logger.warning, "since the DeviceType could not be retrieved")

    def test_create_logs_error_when_role_validated_save_fails(self):
        """Role validated_save raises -> error logged, create continues."""
        role_obj = mock.MagicMock()
        role_obj.cf.get.return_value = "OldRole"  # mismatch triggers the save path
        role_obj.validated_save.side_effect = diffsync_models.ValidationError("boom")

        with (
            _patch_device_create_helpers(role=role_obj, location=None),
        ):
            self._call_device_create(role="DesiredRole")

        role_obj.validated_save.assert_called_once()
        self._assert_log_contains(self.adapter.job.logger.error, "Unable to perform a validated_save() on Role")

    def test_create_warns_when_role_helper_returns_none(self):
        """Role helper returns None -> warning, no cf write."""
        with (
            _patch_device_create_helpers(role=None, location=None),
        ):
            result = self._call_device_create()

        self.assertIsNone(result)
        self._assert_log_contains(self.adapter.job.logger.warning, "to get or create a Role")

    def test_create_warns_when_status_helper_returns_none(self):
        """Status helper returns None -> warning."""
        with _patch_device_create_helpers(status=None):
            result = self._call_device_create()

        self.assertIsNone(result)
        self._assert_log_contains(self.adapter.job.logger.warning, "to get or create a Status")

    def test_create_with_vc_assigns_to_virtual_chassis(self):
        """With vc_name set -> VC helpers called and super().create() runs."""
        new_device = mock.MagicMock()
        vc_obj = mock.MagicMock()
        with (
            _patch_device_create_helpers(),
            mock.patch.object(diffsync_models.NautobotDevice.objects, "get_or_create", return_value=(new_device, True)),
            _nb_patch("tag_object"),
            _nb_patch("get_or_create_virtual_chassis_object", return_value=vc_obj) as mock_vc_helper,
            _nb_patch("assign_device_to_virtual_chassis") as mock_assign,
            mock.patch.object(diffsync_models.DiffSyncModel, "create", return_value="ok"),
        ):
            result = self._call_device_create(vc_name="stack-A", vc_position=1, vc_priority=5, vc_master=True)

        mock_vc_helper.assert_called_once_with("stack-A", logger=self.adapter.job.logger)
        mock_assign.assert_called_once()
        self.assertEqual(result, "ok")

    def test_create_handles_vc_helper_exception(self):
        """VC helper raises -> error logged, super().create() still runs."""
        new_device = mock.MagicMock()
        with (
            _patch_device_create_helpers(),
            mock.patch.object(diffsync_models.NautobotDevice.objects, "get_or_create", return_value=(new_device, True)),
            _nb_patch("tag_object"),
            _nb_patch(
                "get_or_create_virtual_chassis_object",
                side_effect=diffsync_models.ValidationError("vc boom"),
            ),
            mock.patch.object(diffsync_models.DiffSyncModel, "create", return_value="ok"),
        ):
            self._call_device_create(vc_name="stack-A")

        self._assert_log_contains(self.adapter.job.logger.error, "VirtualChassis data")

    # --- Device.update -----------------------------------------------------

    def _setup_update(self, **device_kwargs):
        """Build a Device diffsync model and its 'Active' Nautobot stand-in."""
        diff_model = Device(name="d", location_name="loc", **device_kwargs)
        diff_model.adapter = self.adapter
        return diff_model, _active_device_mock()

    def test_update_detects_vc_attrs_present_for_non_name_keys(self):
        """Regression: vc_attrs_present must be True if any VC-prefixed key is in attrs.

        Previous impl used `vc_name or vc_master or vc_position or vc_priority` and could
        miss legitimate `vc_master=False` or zero-valued updates. Membership check now used.
        """
        diff_model, nb_device = self._setup_update(vc_name="stack-A")

        with (
            mock.patch.object(diffsync_models.NautobotDevice.objects, "get", return_value=nb_device),
            _nb_patch("tag_object"),
            _nb_patch("get_or_create_virtual_chassis_object") as mock_get_vc,
            _nb_patch("assign_device_to_virtual_chassis") as mock_assign,
            mock.patch.object(diffsync_models.DiffSyncModel, "update"),
        ):
            mock_get_vc.return_value = mock.MagicMock()
            # vc_position alone in attrs (no vc_name) must still trigger the VC code path.
            diff_model.update({"vc_position": 3})

        mock_get_vc.assert_called_once_with("stack-A", logger=self.adapter.job.logger)
        mock_assign.assert_called_once()

    def test_update_status_active_sets_status_and_removes_safe_tag(self):
        """Status flip to Active rewrites status and removes safe-delete tag."""
        diff_model, nb_device = self._setup_update()
        nb_device.status.name = "Decommissioning"  # differs from "Active"

        with (
            mock.patch.object(diffsync_models.NautobotDevice.objects, "get", return_value=nb_device),
            _nb_patch("get_or_create_status_object", return_value="active-status-obj") as mock_status,
            _nb_patch("tag_object"),
            mock.patch.object(diffsync_models.DiffSyncModel, "update", return_value="ok"),
        ):
            diff_model.update({"status": "Active"})

        mock_status.assert_called_once()
        self.assertEqual(nb_device.status, "active-status-obj")
        nb_device.tags.remove.assert_called_once_with(self.adapter.safe_delete_tag)

    def test_update_calls_device_type_helper_when_model_in_attrs(self):
        """`model` in attrs -> `get_or_create_device_type_object` is called."""
        diff_model, nb_device = self._setup_update(vendor="cisco")

        with (
            mock.patch.object(diffsync_models.NautobotDevice.objects, "get", return_value=nb_device),
            _nb_patch("get_device_type_object", return_value=None),
            _nb_patch("get_or_create_manufacturer_object", return_value="mfg"),
            _nb_patch("get_or_create_device_type_object", return_value=mock.MagicMock()) as mock_dt_helper,
            _nb_patch("tag_object"),
            mock.patch.object(diffsync_models.DiffSyncModel, "update", return_value="ok"),
        ):
            diff_model.update({"model": "new-model"})

        mock_dt_helper.assert_called_once_with(
            device_type="new-model",
            vendor_name="cisco",
            logger=self.adapter.job.logger,
            manufacturer_obj="mfg",
        )

    def test_update_calls_platform_helper_when_platform_in_attrs(self):
        """`platform` in attrs + Manufacturer found -> `get_or_create_platform_object` called."""
        diff_model, nb_device = self._setup_update(vendor="cisco")

        with (
            mock.patch.object(diffsync_models.NautobotDevice.objects, "get", return_value=nb_device),
            _nb_patch("get_or_create_manufacturer_object", return_value="mfg"),
            _nb_patch("get_or_create_platform_object", return_value=mock.MagicMock()) as mock_plat_helper,
            _nb_patch("tag_object"),
            mock.patch.object(diffsync_models.DiffSyncModel, "update", return_value="ok"),
        ):
            diff_model.update({"platform": "ios"})

        mock_plat_helper.assert_called_once_with(platform="ios", manufacturer_obj="mfg", logger=self.adapter.job.logger)

    def test_update_warns_when_the_platform_cannot_be_resolved(self):
        """A Platform that cannot be resolved is reported rather than silently dropped."""
        diff_model, nb_device = self._setup_update(vendor="cisco")

        with (
            mock.patch.object(diffsync_models.NautobotDevice.objects, "get", return_value=nb_device),
            _nb_patch("get_or_create_manufacturer_object", return_value=None),
            _nb_patch("get_platform_object", return_value=None),
            _nb_patch("tag_object"),
            mock.patch.object(diffsync_models.DiffSyncModel, "update", return_value="ok"),
        ):
            diff_model.update({"platform": "ios"})

        self._assert_log_contains(self.adapter.job.logger.warning, "with a Platform of ios")

    def test_update_resolves_the_role_through_the_scope(self):
        """`role` in attrs goes through the resolver, so a Role is not created out of scope."""
        diff_model, nb_device = self._setup_update()
        new_role = mock.MagicMock(name="new_role")

        with (
            mock.patch.object(diffsync_models.NautobotDevice.objects, "get", return_value=nb_device),
            _nb_patch("get_or_create_device_role_object", return_value=new_role) as mock_role_helper,
            _nb_patch("tag_object"),
            mock.patch.object(diffsync_models.DiffSyncModel, "update", return_value="ok"),
        ):
            diff_model.update({"role": "new-role"})

        mock_role_helper.assert_called_once()
        self.assertIs(nb_device.role, new_role)

    def test_update_calls_location_helper_when_location_name_in_attrs(self):
        """`location_name` in attrs -> `get_or_create_location_object` called and assigned."""
        diff_model, nb_device = self._setup_update()
        new_location = mock.MagicMock(name="new_location")

        with (
            mock.patch.object(diffsync_models.NautobotDevice.objects, "get", return_value=nb_device),
            _nb_patch("get_or_create_location_object", return_value=new_location) as mock_loc_helper,
            _nb_patch("tag_object"),
            mock.patch.object(diffsync_models.DiffSyncModel, "update", return_value="ok"),
        ):
            diff_model.update({"location_name": "new-loc"})

        mock_loc_helper.assert_called_once_with(
            location_name="new-loc", location_id=None, logger=self.adapter.job.logger
        )
        self.assertIs(nb_device.location, new_location)


class TestResolveLocation(_ModelTestBase):
    """Test the single place that decides whether a sync may create a Location."""

    def test_creates_when_locations_are_in_scope(self):
        self.adapter.scope.locations = True

        with _nb_patch("get_or_create_location_object", return_value="created") as mock_helper:
            resolved = diffsync_models.resolve_location(self.adapter, "loc", "site-id")

        self.assertEqual(resolved, "created")
        mock_helper.assert_called_once_with(location_name="loc", location_id="site-id", logger=self.adapter.job.logger)

    def test_only_looks_up_when_locations_are_out_of_scope(self):
        """Another system owns Locations, so a missing one is theirs to create, not this sync's."""
        self.adapter.scope.locations = False

        with (
            _nb_patch("get_location_object", return_value="found") as mock_lookup,
            _nb_patch("get_or_create_location_object") as mock_create,
        ):
            resolved = diffsync_models.resolve_location(self.adapter, "loc", "site-id")

        self.assertEqual(resolved, "found")
        mock_lookup.assert_called_once_with("loc", logger=self.adapter.job.logger)
        mock_create.assert_not_called()


# ============================================================
# Interface lifecycle
# ============================================================


class TestInterfaceModel(_ModelTestBase):
    """Test `Interface.create/update/delete` branching and regression guards."""

    _BASE_CREATE_IDS = {"name": "eth0", "device_name": "d1"}

    def _call_interface_create(self, **attr_overrides):
        attrs = {"ip_address": None, "subnet_mask": None, "status": "Active"}
        attrs.update(attr_overrides)
        return Interface.create(adapter=self.adapter, ids=self._BASE_CREATE_IDS, attrs=attrs)

    @_nb_patch("get_tagged_device", return_value=None)
    def test_create_warns_when_tagged_device_not_found(self, _mock_get_device):
        """Missing parent device -> warning logged, no super().create()."""
        with mock.patch.object(diffsync_models.DiffSyncModel, "create") as mock_super:
            result = self._call_interface_create()
        self.assertIsNone(result)
        mock_super.assert_not_called()
        self.adapter.job.logger.warning.assert_called_once()

    def _exercise_create_primary_ip(self, ip_version, ip_address):
        """Shared helper for the IPv4/IPv6 primary-IP create paths."""
        device_obj = mock.MagicMock()
        interface_obj = mock.MagicMock()
        ip_obj = mock.MagicMock()
        ip_obj.ip_version = ip_version

        with (
            _nb_patch("get_tagged_device", return_value=device_obj),
            _nb_patch("create_interface", return_value=interface_obj),
            _nb_patch("create_ip", return_value=ip_obj),
            mock.patch.object(diffsync_models.DiffSyncModel, "create"),
        ):
            self._call_interface_create(
                ip_address=ip_address,
                subnet_mask="255.255.255.0",
                ip_is_primary=True,
            )
        return device_obj, ip_obj

    def test_create_primary_ipv4_saves_device_only_once(self):
        """Regression: ip_version dispatch uses if/elif so device.save() is called exactly once."""
        device_obj, ip_obj = self._exercise_create_primary_ip(ip_version=4, ip_address="10.0.0.1")
        self.assertIs(device_obj.primary_ip4, ip_obj)
        device_obj.save.assert_called_once()

    def test_create_primary_ipv6_saves_device_only_once(self):
        """`ip_version == 6` takes the elif branch; primary_ip6 set, save called once."""
        device_obj, ip_obj = self._exercise_create_primary_ip(ip_version=6, ip_address="2001:db8::1")
        self.assertIs(device_obj.primary_ip6, ip_obj)
        device_obj.save.assert_called_once()

    def test_delete_only_safe_deletes_unshared_ips(self):
        """Regression: when an IP is also on another interface, the IP must not be safe-deleted."""
        interface_obj = mock.MagicMock()
        interface_obj.id = "iface-uuid"
        other_interface = mock.MagicMock(name="other_interface")
        other_interface.id = "other-iface-uuid"

        # The prefetched Interfaces of each address, which is where the check reads from.
        shared_ip = mock.MagicMock(name="shared_ip")
        shared_ip.interfaces.all.return_value = [interface_obj, other_interface]

        exclusive_ip = mock.MagicMock(name="exclusive_ip")
        exclusive_ip.interfaces.all.return_value = [interface_obj]

        interface_obj.ip_addresses.all.return_value = [shared_ip, exclusive_ip]

        device = mock.MagicMock()
        device.interfaces.prefetch_related.return_value.get.return_value = interface_obj

        diff_model = Interface(name="eth0", device_name="d1", status="Active")
        diff_model.adapter = self.adapter

        with (
            _nb_patch("get_tagged_device", return_value=device),
            mock.patch.object(DiffSyncExtras, "safe_delete") as mock_safe_delete,
            mock.patch.object(diffsync_models.DiffSyncModel, "delete"),
        ):
            diff_model.delete()

        targets = [call.args[0] for call in mock_safe_delete.call_args_list]
        self.assertIn(exclusive_ip, targets)
        self.assertIn(interface_obj, targets)
        self.assertNotIn(shared_ip, targets)

    def _setup_interface_update(self):
        """Build a diff model + a mocked device/interface returned from the prefetch chain."""
        diff_model = Interface(name="eth0", device_name="d1", status="Active")
        diff_model.adapter = self.adapter

        device = mock.MagicMock(name="device")
        interface_obj = mock.MagicMock(name="interface")
        device.interfaces.prefetch_related.return_value.get.return_value = interface_obj
        return diff_model, device, interface_obj

    def test_update_replaces_existing_ip_address(self):
        """Existing addresses are cleared, and `create_ip` is left to assign the new one."""
        diff_model, device, interface_obj = self._setup_interface_update()
        interface_obj.ip_addresses.all.return_value = [mock.MagicMock()]  # existing IPs present
        new_ip = mock.MagicMock()

        with (
            _nb_patch("get_tagged_device", return_value=device),
            _nb_patch("create_ip", return_value=new_ip) as create_ip,
            _nb_patch("tag_object"),
            mock.patch.object(diffsync_models.DiffSyncModel, "update", return_value="ok"),
        ):
            result = diff_model.update({"ip_address": "10.0.0.5", "subnet_mask": "255.255.255.0"})

        interface_obj.ip_addresses.set.assert_called_once_with([])
        self.assertEqual(create_ip.call_args.kwargs["object_pk"], interface_obj)
        interface_obj.ip_addresses.add.assert_not_called()
        self.assertEqual(result, "ok")

    def test_update_primary_ipv6_saves_device(self):
        """`ip_version == 6` -> primary_ip6 set and `device.save()` called once."""
        diff_model, device, interface_obj = self._setup_interface_update()
        existing_ip = mock.MagicMock()
        existing_ip.ip_version = 6
        interface_obj.ip_addresses.first.return_value = existing_ip

        with (
            _nb_patch("get_tagged_device", return_value=device),
            _nb_patch("tag_object"),
            mock.patch.object(diffsync_models.DiffSyncModel, "update", return_value="ok"),
        ):
            diff_model.update({"ip_is_primary": True})

        self.assertIs(device.primary_ip6, existing_ip)
        device.save.assert_called_once()


# ============================================================
# Vlan lifecycle
# ============================================================


class TestVlanModel(_ModelTestBase):
    """Test `Vlan.create/update/delete` branching and regression guards."""

    def _make_vlan_diff(self, location="loc"):
        diff_model = Vlan(name="v", vid=10, status="Active", location=location)
        diff_model.adapter = self.adapter
        return diff_model

    def test_update_writes_attrs_description_to_vlan(self):
        """Regression: `vlan.description = attrs['description']` (was `vlan.description = vlan.description`).

        Without this fix, VLAN description changes would silently no-op.
        """
        diff_model = self._make_vlan_diff()
        nb_vlan = mock.MagicMock()
        nb_vlan.status = "Active"
        nb_vlan.description = "old"

        with (
            mock.patch.object(diffsync_models.NautobotLocation.objects, "get", return_value=mock.MagicMock()),
            mock.patch.object(diffsync_models.VLAN.objects, "get", return_value=nb_vlan),
            _nb_patch("tag_object"),
            mock.patch.object(diffsync_models.DiffSyncModel, "update", return_value="ok"),
        ):
            result = diff_model.update({"description": "new"})

        self.assertEqual(nb_vlan.description, "new")
        self.assertEqual(result, "ok")

    def _assert_vlan_update_returns_none(self, *, location_side_effect=None, vlan_side_effect=None):
        """Shared assertion: VLAN.update bails out (returns None, super() not invoked)."""
        diff_model = self._make_vlan_diff()
        location_kw = (
            {"side_effect": location_side_effect} if location_side_effect else {"return_value": mock.MagicMock()}
        )
        vlan_kw = {"side_effect": vlan_side_effect} if vlan_side_effect else {"return_value": mock.MagicMock()}

        with (
            mock.patch.object(diffsync_models.NautobotLocation.objects, "get", **location_kw),
            mock.patch.object(diffsync_models.VLAN.objects, "get", **vlan_kw) as mock_vlan_get,
            mock.patch.object(diffsync_models.DiffSyncModel, "update") as mock_super,
        ):
            result = diff_model.update({"description": "new"})

        self.assertIsNone(result)
        mock_super.assert_not_called()
        self.adapter.job.logger.error.assert_called_once()
        return mock_vlan_get

    def test_update_returns_none_when_location_missing(self):
        """`Location.DoesNotExist` -> error log, no VLAN lookup attempted, no super().update()."""
        mock_vlan_get = self._assert_vlan_update_returns_none(
            location_side_effect=diffsync_models.NautobotLocation.DoesNotExist
        )
        mock_vlan_get.assert_not_called()

    def test_update_returns_none_when_location_multiple_objects(self):
        """`Location.MultipleObjectsReturned` -> error log + return None."""
        mock_vlan_get = self._assert_vlan_update_returns_none(
            location_side_effect=diffsync_models.NautobotLocation.MultipleObjectsReturned
        )
        mock_vlan_get.assert_not_called()

    def test_update_returns_none_when_vlan_multiple_objects(self):
        """`VLAN.MultipleObjectsReturned` -> error log + return None."""
        self._assert_vlan_update_returns_none(vlan_side_effect=diffsync_models.VLAN.MultipleObjectsReturned)

    def test_update_returns_none_when_vlan_does_not_exist(self):
        """`VLAN.DoesNotExist` -> error log + return None."""
        self._assert_vlan_update_returns_none(vlan_side_effect=diffsync_models.VLAN.DoesNotExist)

    @_nb_patch("create_vlan", return_value=None)
    def test_create_returns_none_when_helper_fails(self, _mock_create_vlan):
        """When `create_vlan` returns None, `Vlan.create` short-circuits without calling super()."""
        with (
            mock.patch.object(diffsync_models.NautobotLocation.objects, "get", return_value=mock.MagicMock()),
            mock.patch.object(diffsync_models.DiffSyncModel, "create") as mock_super,
        ):
            result = Vlan.create(
                adapter=self.adapter,
                ids={"name": "v", "location": "loc"},
                attrs={"vid": 10, "status": "Active", "description": "d"},
            )

        self.assertIsNone(result)
        mock_super.assert_not_called()

    def test_update_status_active_sets_status_and_removes_safe_tag(self):
        """Status flip to Active rewrites VLAN status and removes safe-delete tag."""
        diff_model = self._make_vlan_diff()
        nb_vlan = mock.MagicMock()
        nb_vlan.status = "Decommissioning"  # differs from "Active"

        with (
            mock.patch.object(diffsync_models.NautobotLocation.objects, "get", return_value=mock.MagicMock()),
            mock.patch.object(diffsync_models.VLAN.objects, "get", return_value=nb_vlan),
            _nb_patch("get_or_create_status_object", return_value="active-status-obj") as mock_status,
            _nb_patch("tag_object"),
            mock.patch.object(diffsync_models.DiffSyncModel, "update", return_value="ok"),
        ):
            diff_model.update({"status": "Active"})

        mock_status.assert_called_once()
        self.assertEqual(nb_vlan.status, "active-status-obj")
        nb_vlan.tags.remove.assert_called_once_with(self.adapter.safe_delete_tag)

    def test_update_returns_none_when_tag_object_fails(self):
        """`tag_object` raises -> warning log + return None (no super().update())."""
        diff_model = self._make_vlan_diff()
        nb_vlan = mock.MagicMock()
        nb_vlan.status = "Active"

        with (
            mock.patch.object(diffsync_models.NautobotLocation.objects, "get", return_value=mock.MagicMock()),
            mock.patch.object(diffsync_models.VLAN.objects, "get", return_value=nb_vlan),
            _nb_patch("tag_object", side_effect=diffsync_models.ValidationError("tag boom")),
            mock.patch.object(diffsync_models.DiffSyncModel, "update") as mock_super,
        ):
            result = diff_model.update({"description": "new"})

        self.assertIsNone(result)
        mock_super.assert_not_called()
        self.adapter.job.logger.warning.assert_called_once()


# ============================================================
# Cable lifecycle
# ============================================================


class TestCableModel(_ModelTestBase):
    """Test `Cable.create/update/delete` branching logic."""

    IDS = {
        "termination_a_device": "dev1",
        "termination_a_name": "eth0",
        "termination_b_device": "dev2",
        "termination_b_name": "eth0",
    }
    ATTRS = {"status": "Connected"}

    def _make_cable_diff(self):
        """Return a Cable diffsync model bound to the mock adapter."""
        diff_model = Cable(**self.IDS, **self.ATTRS)
        diff_model.adapter = self.adapter
        return diff_model

    @staticmethod
    def _uncabled_interface():
        """Return an Interface mock that is not currently cabled."""
        interface = mock.MagicMock()
        interface.cable = None
        return interface

    def test_create_returns_none_when_an_interface_is_missing(self):
        """A link cannot be created unless both of its Interfaces resolve."""
        with (
            _nb_patch("get_tagged_interface", side_effect=[self._uncabled_interface(), None]),
            _cable_patch("create_cable") as mock_create_cable,
            mock.patch.object(diffsync_models.DiffSyncModel, "create") as mock_super,
        ):
            result = Cable.create(adapter=self.adapter, ids=self.IDS, attrs=self.ATTRS)

        self.assertIsNone(result)
        mock_create_cable.assert_not_called()
        mock_super.assert_not_called()
        self._assert_log_contains(self.adapter.job.logger.warning, "dev1:eth0 <-> dev2:eth0")

    def test_create_adopts_an_existing_matching_cable(self):
        """A Cable already recording this link is updated in place, not replaced."""
        existing = mock.MagicMock()
        interface_a = mock.MagicMock()
        interface_a.cable = existing

        with (
            _nb_patch("get_tagged_interface", side_effect=[interface_a, mock.MagicMock()]),
            _cable_patch("cable_connects", return_value=True),
            _cable_patch("update_cable_status", return_value=True) as mock_update_status,
            _cable_patch("create_cable") as mock_create_cable,
            mock.patch.object(diffsync_models.DiffSyncModel, "create", return_value="ok"),
        ):
            result = Cable.create(adapter=self.adapter, ids=self.IDS, attrs=self.ATTRS)

        self.assertEqual(result, "ok")
        mock_update_status.assert_called_once()
        mock_create_cable.assert_not_called()
        existing.delete.assert_not_called()

    def test_create_refuses_to_displace_a_cable_in_safe_delete_mode(self):
        """Safe delete mode never removes the Cable occupying an Interface, so the link is skipped."""
        occupied = mock.MagicMock()

        with (
            mock.patch.object(Cable, "safe_delete_mode", True),
            _nb_patch("get_tagged_interface", side_effect=[occupied, self._uncabled_interface()]),
            _cable_patch("cable_connects", return_value=False),
            _cable_patch("create_cable") as mock_create_cable,
            mock.patch.object(diffsync_models.DiffSyncModel, "create") as mock_super,
        ):
            result = Cable.create(adapter=self.adapter, ids=self.IDS, attrs=self.ATTRS)

        self.assertIsNone(result)
        occupied.cable.delete.assert_not_called()
        mock_create_cable.assert_not_called()
        mock_super.assert_not_called()
        self._assert_log_contains(self.adapter.job.logger.warning, "Safe Delete Mode")

    def test_create_displaces_a_stale_cable_when_safe_delete_is_off(self):
        """With safe delete off, the Cable holding the Interface is removed so the link can move."""
        occupied = mock.MagicMock()
        stale_cable = occupied.cable

        with (
            mock.patch.object(Cable, "safe_delete_mode", False),
            _nb_patch("get_tagged_interface", side_effect=[occupied, self._uncabled_interface()]),
            _cable_patch("cable_connects", return_value=False),
            _cable_patch("create_cable", return_value=mock.MagicMock()) as mock_create_cable,
            mock.patch.object(diffsync_models.DiffSyncModel, "create", return_value="ok"),
        ):
            result = Cable.create(adapter=self.adapter, ids=self.IDS, attrs=self.ATTRS)

        self.assertEqual(result, "ok")
        stale_cable.delete.assert_called_once()
        mock_create_cable.assert_called_once()

    def test_create_returns_none_when_displacing_the_stale_cable_fails(self):
        """If the occupying Cable cannot be removed, the new link is not created."""
        occupied = mock.MagicMock()
        occupied.cable.delete.side_effect = diffsync_models.ProtectedError("protected", set())

        with (
            mock.patch.object(Cable, "safe_delete_mode", False),
            _nb_patch("get_tagged_interface", side_effect=[occupied, self._uncabled_interface()]),
            _cable_patch("cable_connects", return_value=False),
            _cable_patch("create_cable") as mock_create_cable,
            mock.patch.object(diffsync_models.DiffSyncModel, "create") as mock_super,
        ):
            result = Cable.create(adapter=self.adapter, ids=self.IDS, attrs=self.ATTRS)

        self.assertIsNone(result)
        mock_create_cable.assert_not_called()
        mock_super.assert_not_called()

    def test_delete_safe_mode_changes_status_instead_of_removing(self):
        """Safe delete mode tags the Cable and moves it to the safe delete Status."""
        diff_model = self._make_cable_diff()
        nb_cable = mock.MagicMock()

        with (
            mock.patch.object(Cable, "safe_delete_mode", True),
            mock.patch.object(Cable, "retrieve_cable", return_value=nb_cable),
            mock.patch.object(Cable, "safe_delete") as mock_safe_delete,
            mock.patch.object(diffsync_models.DiffSyncModel, "delete", return_value="ok"),
        ):
            result = diff_model.delete()

        self.assertEqual(result, "ok")
        nb_cable.delete.assert_not_called()
        mock_safe_delete.assert_called_once_with(
            nb_cable, diffsync_models.SAFE_DELETE_CABLE_STATUS, self.adapter.safe_delete_tag
        )

    def test_delete_removes_the_cable_immediately_when_safe_delete_is_off(self):
        """Cables are deleted inline rather than queued, so a relocated link can claim the Interface."""
        diff_model = self._make_cable_diff()
        nb_cable = mock.MagicMock()

        with (
            mock.patch.object(Cable, "safe_delete_mode", False),
            mock.patch.object(Cable, "retrieve_cable", return_value=nb_cable),
            mock.patch.object(Cable, "safe_delete") as mock_safe_delete,
            mock.patch.object(diffsync_models.DiffSyncModel, "delete", return_value="ok"),
        ):
            result = diff_model.delete()

        self.assertEqual(result, "ok")
        nb_cable.delete.assert_called_once()
        # safe_delete is what would have queued it for `sync_complete()` instead.
        mock_safe_delete.assert_not_called()

    def test_delete_is_a_noop_when_the_cable_is_already_gone(self):
        """A Cable removed earlier in the same sync still completes its diffsync bookkeeping."""
        diff_model = self._make_cable_diff()

        with (
            mock.patch.object(Cable, "retrieve_cable", return_value=None),
            mock.patch.object(diffsync_models.DiffSyncModel, "delete", return_value="ok") as mock_super,
        ):
            result = diff_model.delete()

        self.assertEqual(result, "ok")
        mock_super.assert_called_once()
        self.adapter.job.logger.error.assert_not_called()

    def test_update_returns_none_when_the_cable_is_missing(self):
        """An absent Cable is an error on update, since the diff expected it to be there."""
        diff_model = self._make_cable_diff()

        with (
            mock.patch.object(Cable, "retrieve_cable", return_value=None),
            mock.patch.object(diffsync_models.DiffSyncModel, "update") as mock_super,
        ):
            result = diff_model.update({"status": "Planned"})

        self.assertIsNone(result)
        mock_super.assert_not_called()
        self._assert_log_contains(self.adapter.job.logger.error, "dev1:eth0 <-> dev2:eth0")

    def test_update_removes_safe_delete_tag_when_status_returns_to_default(self):
        """A link seen again by IP Fabric loses the safe delete tag it picked up while absent."""
        diff_model = self._make_cable_diff()
        nb_cable = mock.MagicMock()

        with (
            mock.patch.object(Cable, "retrieve_cable", return_value=nb_cable),
            _cable_patch("update_cable_status", return_value=True),
            mock.patch.object(diffsync_models.DiffSyncModel, "update", return_value="ok"),
        ):
            result = diff_model.update({"status": diffsync_models.DEFAULT_CABLE_STATUS})

        self.assertEqual(result, "ok")
        nb_cable.tags.remove.assert_called_once_with(self.adapter.safe_delete_tag)

    def test_update_keeps_safe_delete_tag_for_a_non_default_status(self):
        """Any other Status leaves the tag in place."""
        diff_model = self._make_cable_diff()
        nb_cable = mock.MagicMock()

        with (
            mock.patch.object(Cable, "retrieve_cable", return_value=nb_cable),
            _cable_patch("update_cable_status", return_value=True),
            mock.patch.object(diffsync_models.DiffSyncModel, "update", return_value="ok"),
        ):
            diff_model.update({"status": "Planned"})

        nb_cable.tags.remove.assert_not_called()

    def test_retrieve_cable_rejects_a_cable_to_a_different_peer(self):
        """An Interface cabled somewhere else is not this link, so nothing is returned."""
        diff_model = self._make_cable_diff()
        interface_a = mock.MagicMock()
        interface_a.cable = mock.MagicMock()

        with (
            _nb_patch("get_tagged_interface", side_effect=[interface_a, mock.MagicMock()]),
            _cable_patch("cable_connects", return_value=False),
        ):
            self.assertIsNone(diff_model.retrieve_cable())

    def test_create_returns_none_when_adopting_an_existing_cable_fails(self):
        """If the existing Cable's Status cannot be corrected, the link is not recorded."""
        interface_a = mock.MagicMock()

        with (
            _nb_patch("get_tagged_interface", side_effect=[interface_a, mock.MagicMock()]),
            _cable_patch("cable_connects", return_value=True),
            _cable_patch("update_cable_status", return_value=False),
            mock.patch.object(diffsync_models.DiffSyncModel, "create") as mock_super,
        ):
            result = Cable.create(adapter=self.adapter, ids=self.IDS, attrs=self.ATTRS)

        self.assertIsNone(result)
        mock_super.assert_not_called()

    def test_create_returns_none_when_cable_creation_fails(self):
        """A failed `create_cable` short-circuits without calling super()."""
        with (
            _nb_patch("get_tagged_interface", side_effect=[self._uncabled_interface(), self._uncabled_interface()]),
            _cable_patch("cable_connects", return_value=False),
            _cable_patch("create_cable", return_value=None),
            mock.patch.object(diffsync_models.DiffSyncModel, "create") as mock_super,
        ):
            result = Cable.create(adapter=self.adapter, ids=self.IDS, attrs=self.ATTRS)

        self.assertIsNone(result)
        mock_super.assert_not_called()

    def test_retrieve_cable_by_pk_skips_the_endpoint_walk(self):
        """A model carrying `cable_pk` looks the Cable up directly."""
        diff_model = Cable(**self.IDS, **self.ATTRS, cable_pk=UUID("00000000-0000-0000-0000-00000000abcd"))
        diff_model.adapter = self.adapter
        nb_cable = mock.MagicMock()

        with (
            mock.patch.object(diffsync_models.NautobotCable.objects, "filter") as mock_filter,
            _nb_patch("get_tagged_interface") as mock_get_interface,
        ):
            mock_filter.return_value.select_related.return_value.first.return_value = nb_cable
            result = diff_model.retrieve_cable()

        self.assertIs(result, nb_cable)
        mock_get_interface.assert_not_called()

    def test_retrieve_cable_returns_none_when_an_interface_is_missing(self):
        """Without `cable_pk`, an unresolvable Interface means the Cable cannot be found."""
        diff_model = self._make_cable_diff()

        with _nb_patch("get_tagged_interface", side_effect=[None, None]):
            self.assertIsNone(diff_model.retrieve_cable())

    def test_retrieve_cable_returns_the_matching_cable(self):
        """Without `cable_pk`, the Cable on the A side is returned when it connects both ends."""
        diff_model = self._make_cable_diff()
        interface_a = mock.MagicMock()

        with (
            _nb_patch("get_tagged_interface", side_effect=[interface_a, mock.MagicMock()]),
            _cable_patch("cable_connects", return_value=True),
        ):
            self.assertIs(diff_model.retrieve_cable(), interface_a.cable)

    def test_update_returns_none_when_the_status_update_fails(self):
        """A failed Status update leaves the diffsync model untouched."""
        diff_model = self._make_cable_diff()

        with (
            mock.patch.object(Cable, "retrieve_cable", return_value=mock.MagicMock()),
            _cable_patch("update_cable_status", return_value=False),
            mock.patch.object(diffsync_models.DiffSyncModel, "update") as mock_super,
        ):
            result = diff_model.update({"status": "Planned"})

        self.assertIsNone(result)
        mock_super.assert_not_called()

    def test_delete_returns_none_when_removal_fails(self):
        """A Cable that cannot be removed is reported and the model is not marked deleted."""
        diff_model = self._make_cable_diff()
        nb_cable = mock.MagicMock()
        nb_cable.delete.side_effect = diffsync_models.ProtectedError("protected", set())

        with (
            mock.patch.object(Cable, "safe_delete_mode", False),
            mock.patch.object(Cable, "retrieve_cable", return_value=nb_cable),
            mock.patch.object(diffsync_models.DiffSyncModel, "delete") as mock_super,
        ):
            result = diff_model.delete()

        self.assertIsNone(result)
        mock_super.assert_not_called()
        self.adapter.job.logger.error.assert_called_once()
