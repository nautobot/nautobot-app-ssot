"""Tests for IPFabric diffsync models.

Focused on the model-specific branching logic — early returns, conditional
calls, regression guards for fixed bugs. Nautobot ORM calls and the
`nbutils` helpers are mocked; the heavy lifting is covered by their own
test suites.
"""

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


def _make_adapter():
    """Minimal mock adapter sufficient for invoking model methods directly."""
    adapter = mock.MagicMock()
    adapter.job = mock.MagicMock()
    adapter.job.debug = False
    adapter.ssot_tag = mock.MagicMock(name="ssot_tag")
    adapter.safe_delete_tag = mock.MagicMock(name="safe_delete_tag")
    adapter.safe_delete_tag.id = "tag-uuid"
    return adapter


# ============================================================
# DiffSyncExtras.safe_delete
# ============================================================


class TestSafeDelete(SimpleTestCase):
    """Test `DiffSyncExtras.safe_delete` branching logic."""

    def setUp(self):
        self.adapter = _make_adapter()
        # Vlan is the smallest model; any model would work since safe_delete
        # is defined on the shared base class.
        self.diff_model = Vlan(name="v", vid=10, status="Active", location="loc")
        self.diff_model.adapter = self.adapter

    @mock.patch("nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.tag_object")
    @mock.patch("nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.get_or_create_status_object")
    def test_safe_delete_changes_status_and_tags_when_status_differs(self, mock_status, mock_tag_object):
        """Status differs -> status updated, tag added, tag_object called once."""
        mock_status.return_value = "safe-deleted-status"
        nautobot_obj = mock.MagicMock()
        nautobot_obj.status = "active-status"
        nautobot_obj.tags.filter.return_value.exists.return_value = False

        self.diff_model.safe_delete(nautobot_obj, "Decommissioning", self.adapter.safe_delete_tag)

        self.assertEqual(nautobot_obj.status, "safe-deleted-status")
        nautobot_obj.tags.add.assert_called_once_with(self.adapter.safe_delete_tag)
        mock_tag_object.assert_called_once()

    @mock.patch("nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.tag_object")
    @mock.patch("nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.get_or_create_status_object")
    def test_safe_delete_skips_when_tag_already_present_and_status_unchanged(self, mock_status, mock_tag_object):
        """Tag already on object and status already correct -> no save, no tag_object."""
        already_status = "safe-deleted-status"
        mock_status.return_value = already_status
        nautobot_obj = mock.MagicMock()
        nautobot_obj.status = already_status  # already matches
        nautobot_obj.tags.filter.return_value.exists.return_value = True  # tag already present

        self.diff_model.safe_delete(nautobot_obj, "Decommissioning", self.adapter.safe_delete_tag)

        nautobot_obj.tags.add.assert_not_called()
        mock_tag_object.assert_not_called()

    @mock.patch("nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.tag_object")
    def test_safe_delete_no_tag_arg_is_a_noop_for_tagging(self, mock_tag_object):
        """Defensive guard: when safe_delete_tag is None, tags.add is never called."""
        nautobot_obj = mock.MagicMock(spec=["tags"])  # has tags but no status attr

        self.diff_model.safe_delete(nautobot_obj, safe_delete_status=None, safe_delete_tag=None)

        nautobot_obj.tags.add.assert_not_called()
        mock_tag_object.assert_not_called()


# ============================================================
# Location lifecycle
# ============================================================


class TestLocationModel(SimpleTestCase):
    """Test `Location.create/update/delete` branching logic."""

    def setUp(self):
        self.adapter = _make_adapter()

    @mock.patch(
        "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.get_or_create_location_object",
        return_value=None,
    )
    def test_create_returns_none_when_helper_fails(self, _mock_helper):
        """If `get_or_create_location_object` returns None, `create` returns None and does not call super()."""
        with mock.patch.object(diffsync_models.DiffSyncModel, "create") as mock_super_create:
            result = Location.create(
                adapter=self.adapter,
                ids={"name": "X"},
                attrs={"site_id": "Y", "status": "Active"},
            )
        self.assertIsNone(result)
        mock_super_create.assert_not_called()

    @mock.patch(
        "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.get_or_create_location_object"
    )
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
        """`DoesNotExist` lookup -> logged and `super().delete()` not invoked."""
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


# ============================================================
# Device lifecycle
# ============================================================


class TestDeviceModel(SimpleTestCase):
    """Test `Device.create/update` branching and regression guards."""

    def setUp(self):
        self.adapter = _make_adapter()
        self.adapter.job.debug = False

    @mock.patch(
        "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.get_or_create_location_object",
        return_value=None,
    )
    @mock.patch("nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.get_or_create_status_object")
    @mock.patch(
        "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.get_or_create_device_role_object"
    )
    @mock.patch("nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.DeviceType.objects.filter")
    def test_create_short_circuits_when_location_missing(self, mock_dt_filter, mock_role, mock_status, _mock_loc):
        """Any required helper returning None means Device.create returns None without saving."""
        mock_dt_filter.return_value.first.return_value = mock.MagicMock()
        mock_role.return_value = mock.MagicMock()
        mock_status.return_value = mock.MagicMock()

        with mock.patch.object(diffsync_models.NautobotDevice.objects, "get_or_create") as mock_get_or_create:
            result = Device.create(
                adapter=self.adapter,
                ids={"name": "d1"},
                attrs={"model": "m", "vendor": "v", "location_name": "loc"},
            )

        self.assertIsNone(result)
        mock_get_or_create.assert_not_called()

    @mock.patch(
        "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.get_or_create_device_role_object"
    )
    def test_create_skips_role_cf_save_when_value_already_matches(self, mock_role_helper):
        """Regression: Role.validated_save() must not run when cf['ipfabric_type'] already matches role_name."""
        role_obj = mock.MagicMock()
        role_obj.cf.get.return_value = "DesiredRole"  # already matches
        mock_role_helper.return_value = role_obj

        # Force the rest of the create() to bail before super() by making location lookup fail
        with (
            mock.patch(
                "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.get_or_create_location_object",
                return_value=None,
            ),
            mock.patch(
                "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.get_or_create_status_object"
            ),
            mock.patch.object(diffsync_models.DeviceType.objects, "filter"),
        ):
            Device.create(
                adapter=self.adapter,
                ids={"name": "d1"},
                attrs={"model": "m", "vendor": "v", "role": "DesiredRole", "location_name": "loc"},
            )

        role_obj.validated_save.assert_not_called()
        # cf was never written either
        role_obj.cf.__setitem__.assert_not_called()

    @mock.patch(
        "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.get_or_create_device_role_object"
    )
    def test_create_writes_and_saves_role_cf_when_value_differs(self, mock_role_helper):
        """When cf['ipfabric_type'] does not match, set it and run validated_save() exactly once."""
        role_obj = mock.MagicMock()
        role_obj.cf.get.return_value = "OldRole"  # differs from DesiredRole
        mock_role_helper.return_value = role_obj

        with (
            mock.patch(
                "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.get_or_create_location_object",
                return_value=None,
            ),
            mock.patch(
                "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.get_or_create_status_object"
            ),
            mock.patch.object(diffsync_models.DeviceType.objects, "filter"),
        ):
            Device.create(
                adapter=self.adapter,
                ids={"name": "d1"},
                attrs={"model": "m", "vendor": "v", "role": "DesiredRole", "location_name": "loc"},
            )

        role_obj.cf.__setitem__.assert_called_once_with("ipfabric_type", "DesiredRole")
        role_obj.validated_save.assert_called_once()

    def test_update_detects_vc_attrs_present_for_non_name_keys(self):
        """Regression: ``vc_attrs_present`` must be True if any VC-prefixed key is in attrs.

        The previous implementation used ``vc_name or vc_master or vc_position or vc_priority`` and
        could miss legitimate ``vc_master=False`` or zero-valued updates. Now membership is checked
        via ``any(k in attrs for k in (...))``.
        """
        diff_model = Device(name="d", location_name="loc", vc_name="stack-A")
        diff_model.adapter = self.adapter

        _device = mock.MagicMock()
        _device.status.name = "Active"

        with (
            mock.patch.object(diffsync_models.NautobotDevice.objects, "get", return_value=_device),
            mock.patch("nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.tag_object"),
            mock.patch(
                "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.get_or_create_virtual_chassis_object"
            ) as mock_get_vc,
            mock.patch(
                "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.assign_device_to_virtual_chassis"
            ) as mock_assign,
            mock.patch.object(diffsync_models.DiffSyncModel, "update"),
        ):
            mock_get_vc.return_value = mock.MagicMock()
            # vc_position alone in attrs (no vc_name) should still trigger the VC code path
            diff_model.update({"vc_position": 3})

        mock_get_vc.assert_called_once_with("stack-A", logger=self.adapter.job.logger)
        mock_assign.assert_called_once()


# ============================================================
# Interface lifecycle
# ============================================================


class TestInterfaceModel(SimpleTestCase):
    """Test `Interface.create/update/delete` branching and regression guards."""

    def setUp(self):
        self.adapter = _make_adapter()

    @mock.patch(
        "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.get_tagged_device",
        return_value=None,
    )
    def test_create_warns_when_tagged_device_not_found(self, _mock_get_device):
        """Missing parent device -> warning logged, no super().create()."""
        with mock.patch.object(diffsync_models.DiffSyncModel, "create") as mock_super:
            result = Interface.create(
                adapter=self.adapter,
                ids={"name": "eth0", "device_name": "nope"},
                attrs={
                    "ip_address": None,
                    "subnet_mask": None,
                    "status": "Active",
                },
            )
        self.assertIsNone(result)
        mock_super.assert_not_called()
        self.adapter.job.logger.warning.assert_called_once()

    def test_create_primary_ipv4_saves_device_only_once(self):
        """Regression: ip_version dispatch uses ``if/elif`` so device.save() is called exactly once."""
        device_obj = mock.MagicMock()
        interface_obj = mock.MagicMock()
        ip_obj = mock.MagicMock()
        ip_obj.ip_version = 4

        with (
            mock.patch(
                "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.get_tagged_device",
                return_value=device_obj,
            ),
            mock.patch(
                "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.create_interface",
                return_value=interface_obj,
            ),
            mock.patch(
                "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.create_ip",
                return_value=ip_obj,
            ),
            mock.patch.object(diffsync_models.DiffSyncModel, "create"),
        ):
            Interface.create(
                adapter=self.adapter,
                ids={"name": "eth0", "device_name": "d1"},
                attrs={
                    "ip_address": "10.0.0.1",
                    "subnet_mask": "255.255.255.0",
                    "ip_is_primary": True,
                    "status": "Active",
                },
            )

        # IPv4 path sets primary_ip4 and saves once; primary_ip6 should not be touched.
        self.assertIs(device_obj.primary_ip4, ip_obj)
        device_obj.save.assert_called_once()

    def test_delete_only_safe_deletes_unshared_ips(self):
        """Regression: when an IP is also on another interface, the IP must not be safe-deleted."""
        adapter = self.adapter
        # Build the interface returned from the prefetch chain.
        shared_ip = mock.MagicMock(name="shared_ip")
        shared_ip.interfaces.exclude.return_value.exists.return_value = True  # on another interface

        exclusive_ip = mock.MagicMock(name="exclusive_ip")
        exclusive_ip.interfaces.exclude.return_value.exists.return_value = False  # only this interface

        interface_obj = mock.MagicMock()
        interface_obj.id = "iface-uuid"
        interface_obj.ip_addresses.all.return_value = [shared_ip, exclusive_ip]

        device = mock.MagicMock()
        device.interfaces.prefetch_related.return_value.get.return_value = interface_obj

        diff_model = Interface(name="eth0", device_name="d1", status="Active")
        diff_model.adapter = adapter

        with (
            mock.patch(
                "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.get_tagged_device",
                return_value=device,
            ),
            mock.patch.object(DiffSyncExtras, "safe_delete") as mock_safe_delete,
            mock.patch.object(diffsync_models.DiffSyncModel, "delete"),
        ):
            diff_model.delete()

        # safe_delete called exactly twice: once for exclusive_ip, once for the interface itself.
        # NEVER called for shared_ip.
        safe_delete_targets = [call.args[0] for call in mock_safe_delete.call_args_list]
        self.assertIn(exclusive_ip, safe_delete_targets)
        self.assertIn(interface_obj, safe_delete_targets)
        self.assertNotIn(shared_ip, safe_delete_targets)


# ============================================================
# Vlan lifecycle
# ============================================================


class TestVlanModel(SimpleTestCase):
    """Test `Vlan.create/update/delete` branching and regression guards."""

    def setUp(self):
        self.adapter = _make_adapter()

    def test_update_writes_attrs_description_to_vlan(self):
        """Regression: ``vlan.description = attrs['description']`` (was ``vlan.description = vlan.description``).

        Without this fix, VLAN description changes would silently no-op.
        """
        diff_model = Vlan(name="v", vid=10, status="Active", location="loc")
        diff_model.adapter = self.adapter

        nautobot_vlan = mock.MagicMock()
        nautobot_vlan.status = "Active"
        nautobot_vlan.description = "old"

        with (
            mock.patch.object(diffsync_models.NautobotLocation.objects, "get", return_value=mock.MagicMock()),
            mock.patch.object(diffsync_models.VLAN.objects, "get", return_value=nautobot_vlan),
            mock.patch("nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.tag_object"),
            mock.patch.object(diffsync_models.DiffSyncModel, "update", return_value="ok"),
        ):
            result = diff_model.update({"description": "new"})

        self.assertEqual(nautobot_vlan.description, "new")
        self.assertEqual(result, "ok")

    def test_update_returns_none_when_location_missing(self):
        """`Location.DoesNotExist` -> error log, no VLAN lookup attempted, no super().update()."""
        diff_model = Vlan(name="v", vid=10, status="Active", location="ghost")
        diff_model.adapter = self.adapter

        with (
            mock.patch.object(
                diffsync_models.NautobotLocation.objects,
                "get",
                side_effect=diffsync_models.NautobotLocation.DoesNotExist,
            ),
            mock.patch.object(diffsync_models.VLAN.objects, "get") as mock_vlan_get,
            mock.patch.object(diffsync_models.DiffSyncModel, "update") as mock_super,
        ):
            result = diff_model.update({"description": "new"})

        self.assertIsNone(result)
        mock_vlan_get.assert_not_called()
        mock_super.assert_not_called()
        self.adapter.job.logger.error.assert_called_once()

    @mock.patch(
        "nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models.tonb_nbutils.create_vlan",
        return_value=None,
    )
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
