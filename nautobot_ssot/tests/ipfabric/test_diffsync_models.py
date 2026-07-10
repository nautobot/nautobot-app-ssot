"""Tests for IPFabric diffsync models.

Focused on the model-specific branching logic — early returns, conditional
calls, regression guards for fixed bugs. Nautobot ORM calls and the
`nbutils` helpers are mocked; the heavy lifting is covered by their own
test suites.
"""

import contextlib
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from nautobot_ssot.integrations.ipfabric.diffsync import diffsync_models
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import (
    Device,
    DiffSyncExtras,
    Interface,
    Location,
    Vlan,
)

# ============================================================
# Shared helpers
# ============================================================

_UNSET = object()
_NBUTILS = "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils"


def _nb_patch(name, **kwargs):
    """Patch a helper attribute on `tonb_nbutils` referenced from the model module."""
    return mock.patch(f"{_NBUTILS}.{name}", **kwargs)


def _make_adapter():
    """Minimal mock adapter sufficient for invoking model methods directly."""
    adapter = mock.MagicMock()
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


@contextlib.contextmanager
def _patch_device_create_helpers(
    *,
    device_type=_UNSET,
    role=_UNSET,
    status=_UNSET,
    location=_UNSET,
    platform=_UNSET,
):
    """Patch the five `Device.create` collaborator helpers in one shot.

    Each kwarg overrides the helper's `return_value`. `_UNSET` defaults to a fresh
    `MagicMock()`. Pass `None` to trigger the helper-failure branch.
    """
    helpers = (
        ("get_or_create_device_type_object", device_type),
        ("get_or_create_device_role_object", role),
        ("get_or_create_status_object", status),
        ("get_or_create_location_object", location),
        ("get_or_create_platform_object", platform),
    )
    with contextlib.ExitStack() as stack:
        ns = SimpleNamespace()
        for helper_name, value in helpers:
            return_value = mock.MagicMock() if value is _UNSET else value
            setattr(ns, helper_name, stack.enter_context(_nb_patch(helper_name, return_value=return_value)))
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

    @_nb_patch("tag_object")
    @_nb_patch("get_or_create_status_object")
    def test_safe_delete_changes_status_and_tags_when_status_differs(self, mock_status, mock_tag_object):
        """Status differs -> status updated, tag added, tag_object called once."""
        mock_status.return_value = "safe-deleted-status"
        nb_obj = mock.MagicMock()
        nb_obj.status = "active-status"
        nb_obj.tags.filter.return_value.exists.return_value = False

        self.diff_model.safe_delete(nb_obj, "Decommissioning", self.adapter.safe_delete_tag)

        self.assertEqual(nb_obj.status, "safe-deleted-status")
        nb_obj.tags.add.assert_called_once_with(self.adapter.safe_delete_tag)
        mock_tag_object.assert_called_once()

    @_nb_patch("tag_object")
    @_nb_patch("get_or_create_status_object")
    def test_safe_delete_skips_when_tag_already_present_and_status_unchanged(self, mock_status, mock_tag_object):
        """Tag already on object and status already correct -> no save, no tag_object."""
        mock_status.return_value = "safe-deleted-status"
        nb_obj = mock.MagicMock()
        nb_obj.status = "safe-deleted-status"  # already matches
        nb_obj.tags.filter.return_value.exists.return_value = True  # tag already present

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


class TestDeviceModel(_ModelTestBase):
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
            mock.patch.object(diffsync_models.DeviceType.objects, "filter") as mock_dt_filter,
            mock.patch.object(diffsync_models.NautobotDevice.objects, "get_or_create") as mock_get_or_create,
        ):
            mock_dt_filter.return_value.first.return_value = mock.MagicMock()
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
            mock.patch.object(diffsync_models.DeviceType.objects, "filter"),
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
            mock.patch.object(diffsync_models.DeviceType.objects, "filter"),
        ):
            self._call_device_create(role="DesiredRole")

        role_obj.cf.__setitem__.assert_called_once_with("ipfabric_type", "DesiredRole")
        role_obj.validated_save.assert_called_once()

    def test_create_uses_helper_when_devicetype_filter_empty(self):
        """Empty DeviceType filter -> calls `get_or_create_device_type_object` helper."""
        with (
            mock.patch.object(diffsync_models.DeviceType.objects, "filter") as mock_dt_filter,
            # Helper for DT supplied here, location=None bails early
            _patch_device_create_helpers(location=None) as helpers,
        ):
            mock_dt_filter.return_value.first.return_value = None  # filter is empty
            self._call_device_create()

        helpers.get_or_create_device_type_object.assert_called_once_with(
            device_type="m", vendor_name="v", logger=self.adapter.job.logger
        )

    def test_create_warns_when_devicetype_helper_returns_none(self):
        """DeviceType helper also fails -> warning logged."""
        with (
            mock.patch.object(diffsync_models.DeviceType.objects, "filter") as mock_dt_filter,
            _patch_device_create_helpers(device_type=None),
        ):
            mock_dt_filter.return_value.first.return_value = None
            result = self._call_device_create()

        self.assertIsNone(result)
        self._assert_log_contains(self.adapter.job.logger.warning, "DeviceType")

    def test_create_warns_when_platform_helper_returns_none(self):
        """Platform + device_type_object both set -> helper called; None return warns."""
        device_type_obj = mock.MagicMock()
        with (
            mock.patch.object(diffsync_models.DeviceType.objects, "filter") as mock_dt_filter,
            _patch_device_create_helpers(platform=None, location=None) as helpers,
        ):
            mock_dt_filter.return_value.first.return_value = device_type_obj
            self._call_device_create(platform="ios")

        helpers.get_or_create_platform_object.assert_called_once()
        self._assert_log_contains(self.adapter.job.logger.warning, "will not have a Platform assigned")

    def test_create_warns_when_platform_set_but_devicetype_missing(self):
        """No device_type_object but platform supplied -> warning."""
        with (
            mock.patch.object(diffsync_models.DeviceType.objects, "filter") as mock_dt_filter,
            _patch_device_create_helpers(device_type=None),
        ):
            mock_dt_filter.return_value.first.return_value = None
            self._call_device_create(platform="ios")

        self._assert_log_contains(self.adapter.job.logger.warning, "since the DeviceType could not be retrieved")

    def test_create_logs_error_when_role_validated_save_fails(self):
        """Role validated_save raises -> error logged, create continues."""
        role_obj = mock.MagicMock()
        role_obj.cf.get.return_value = "OldRole"  # mismatch triggers the save path
        role_obj.validated_save.side_effect = diffsync_models.ValidationError("boom")

        with (
            _patch_device_create_helpers(role=role_obj, location=None),
            mock.patch.object(diffsync_models.DeviceType.objects, "filter"),
        ):
            self._call_device_create(role="DesiredRole")

        role_obj.validated_save.assert_called_once()
        self._assert_log_contains(self.adapter.job.logger.error, "Unable to perform a validated_save() on Role")

    def test_create_warns_when_role_helper_returns_none(self):
        """Role helper returns None -> warning, no cf write."""
        with (
            _patch_device_create_helpers(role=None, location=None),
            mock.patch.object(diffsync_models.DeviceType.objects, "filter"),
        ):
            result = self._call_device_create()

        self.assertIsNone(result)
        self._assert_log_contains(self.adapter.job.logger.warning, "to get or create a Role")

    def test_create_warns_when_status_helper_returns_none(self):
        """Status helper returns None -> warning."""
        with _patch_device_create_helpers(status=None), mock.patch.object(diffsync_models.DeviceType.objects, "filter"):
            result = self._call_device_create()

        self.assertIsNone(result)
        self._assert_log_contains(self.adapter.job.logger.warning, "to get or create a Status")

    def test_create_with_vc_assigns_to_virtual_chassis(self):
        """With vc_name set -> VC helpers called and super().create() runs."""
        new_device = mock.MagicMock()
        vc_obj = mock.MagicMock()
        with (
            mock.patch.object(diffsync_models.DeviceType.objects, "filter") as mock_dt_filter,
            _patch_device_create_helpers(),
            mock.patch.object(diffsync_models.NautobotDevice.objects, "get_or_create", return_value=(new_device, True)),
            _nb_patch("tag_object"),
            _nb_patch("get_or_create_virtual_chassis_object", return_value=vc_obj) as mock_vc_helper,
            _nb_patch("assign_device_to_virtual_chassis") as mock_assign,
            mock.patch.object(diffsync_models.DiffSyncModel, "create", return_value="ok"),
        ):
            mock_dt_filter.return_value.first.return_value = mock.MagicMock()
            result = self._call_device_create(vc_name="stack-A", vc_position=1, vc_priority=5, vc_master=True)

        mock_vc_helper.assert_called_once_with("stack-A", logger=self.adapter.job.logger)
        mock_assign.assert_called_once()
        self.assertEqual(result, "ok")

    def test_create_handles_vc_helper_exception(self):
        """VC helper raises -> error logged, super().create() still runs."""
        new_device = mock.MagicMock()
        with (
            mock.patch.object(diffsync_models.DeviceType.objects, "filter") as mock_dt_filter,
            _patch_device_create_helpers(),
            mock.patch.object(diffsync_models.NautobotDevice.objects, "get_or_create", return_value=(new_device, True)),
            _nb_patch("tag_object"),
            _nb_patch(
                "get_or_create_virtual_chassis_object",
                side_effect=diffsync_models.ValidationError("vc boom"),
            ),
            mock.patch.object(diffsync_models.DiffSyncModel, "create", return_value="ok"),
        ):
            mock_dt_filter.return_value.first.return_value = mock.MagicMock()
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
            _nb_patch("get_or_create_device_type_object", return_value=mock.MagicMock()) as mock_dt_helper,
            _nb_patch("tag_object"),
            mock.patch.object(diffsync_models.DiffSyncModel, "update", return_value="ok"),
        ):
            diff_model.update({"model": "new-model"})

        mock_dt_helper.assert_called_once_with(
            device_type="new-model", vendor_name="cisco", logger=self.adapter.job.logger
        )

    def test_update_calls_platform_helper_when_platform_in_attrs(self):
        """`platform` in attrs + Manufacturer found -> `get_or_create_platform_object` called."""
        diff_model, nb_device = self._setup_update(vendor="cisco")

        with (
            mock.patch.object(diffsync_models.NautobotDevice.objects, "get", return_value=nb_device),
            mock.patch.object(diffsync_models.Manufacturer.objects, "get", return_value="mfg"),
            _nb_patch("get_or_create_platform_object", return_value=mock.MagicMock()) as mock_plat_helper,
            _nb_patch("tag_object"),
            mock.patch.object(diffsync_models.DiffSyncModel, "update", return_value="ok"),
        ):
            diff_model.update({"platform": "ios"})

        mock_plat_helper.assert_called_once_with(platform="ios", manufacturer_obj="mfg", logger=self.adapter.job.logger)

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

        mock_loc_helper.assert_called_once_with("new-loc", logger=self.adapter.job.logger)
        self.assertIs(nb_device.location, new_location)


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
        shared_ip = mock.MagicMock(name="shared_ip")
        shared_ip.interfaces.exclude.return_value.exists.return_value = True

        exclusive_ip = mock.MagicMock(name="exclusive_ip")
        exclusive_ip.interfaces.exclude.return_value.exists.return_value = False

        interface_obj = mock.MagicMock()
        interface_obj.id = "iface-uuid"
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
        """Update flows through prefetch, clears existing IPs, adds new."""
        diff_model, device, interface_obj = self._setup_interface_update()
        interface_obj.ip_addresses.all.return_value = [mock.MagicMock()]  # existing IPs present
        new_ip = mock.MagicMock()

        with (
            _nb_patch("get_tagged_device", return_value=device),
            _nb_patch("create_ip", return_value=new_ip),
            _nb_patch("tag_object"),
            mock.patch.object(diffsync_models.DiffSyncModel, "update", return_value="ok"),
        ):
            result = diff_model.update({"ip_address": "10.0.0.5", "subnet_mask": "255.255.255.0"})

        interface_obj.ip_addresses.set.assert_called_once_with([])
        interface_obj.ip_addresses.add.assert_called_once_with(new_ip)
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
