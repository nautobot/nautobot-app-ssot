"""Test the Nautobot Cable utilities used by the IPFabric integration."""

from unittest import mock

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import Error as DjangoBaseDBError
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Cable, Device, DeviceType, Interface, Location, LocationType, Manufacturer
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Role, Status

from nautobot_ssot.integrations.ipfabric.constants import LAST_SYNCHRONIZED_CF_NAME
from nautobot_ssot.integrations.ipfabric.utilities import cables
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache

_CABLES = "nautobot_ssot.integrations.ipfabric.utilities.cables"


class TestCableUtilities(TestCase):
    """Test cases for the cable helpers in `utilities/cables.py`."""

    def setUp(self):
        populate_status_choices()
        # The tag and status helpers cache ORM objects for the life of a job. Left alone, an
        # object cached inside one test's transaction outlives its row and the next test
        # writes a dangling foreign key.
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        self.active_status = Status.objects.get(name="Active")
        self.connected_status = Status.objects.get(name="Connected")
        device_ct = ContentType.objects.get_for_model(Device)
        role = Role.objects.create(name="cable-test")
        role.content_types.add(device_ct)
        site_lt, _ = LocationType.objects.get_or_create(name="cable-site")
        site_lt.content_types.add(device_ct)
        location = Location.objects.create(name="cable-site1", location_type=site_lt, status=self.active_status)
        manufacturer = Manufacturer.objects.create(name="cable-man")
        device_type = DeviceType.objects.create(model="cable-type", manufacturer=manufacturer)
        self.device = Device.objects.create(
            name="cable-dev1", status=self.active_status, role=role, location=location, device_type=device_type
        )
        self.int_a = self._interface("eth0")
        self.int_b = self._interface("eth1")

    def _interface(self, name, interface_type="1000base-t"):
        return Interface.objects.create(name=name, device=self.device, type=interface_type, status=self.active_status)

    # ------------------------------------------------------------------
    # cabled_interfaces
    # ------------------------------------------------------------------

    def test_cabled_interfaces_returns_only_cabled(self):
        """Only Interfaces terminating a Cable are returned."""
        uncabled = self._interface("eth2")
        Cable(termination_a=self.int_a, termination_b=self.int_b, status=self.connected_status).validated_save()

        returned = set(cables.cabled_interfaces(Device.objects.filter(pk=self.device.pk)))

        self.assertEqual({self.int_a, self.int_b}, returned)
        self.assertNotIn(uncabled, returned)

    def test_cabled_interfaces_foreign_key_layout(self):
        """The pre-3.2 branch builds a valid query, which is the one that runs on Nautobot 3.0 and 3.1."""
        Cable(termination_a=self.int_a, termination_b=self.int_b, status=self.connected_status).validated_save()

        with mock.patch(f"{_CABLES}.CABLE_TERMINATIONS_ARE_JOINED", False):
            returned = set(cables.cabled_interfaces(Device.objects.filter(pk=self.device.pk)))

        self.assertEqual({self.int_a, self.int_b}, returned)

    # ------------------------------------------------------------------
    # create_cable
    # ------------------------------------------------------------------

    def test_create_cable(self):
        """A Cable is created between the two Interfaces, tagged and stamped as synced."""
        cable = cables.create_cable(self.int_a, self.int_b, "Connected")

        self.assertIsNotNone(cable)
        self.assertEqual(cable.status, self.connected_status)
        self.assertEqual({cable.termination_a_id, cable.termination_b_id}, {self.int_a.pk, self.int_b.pk})
        self.assertTrue(cable.tags.filter(name="SSoT Synced from IPFabric").exists())
        self.assertEqual(cable.cf["system_of_record"], "IPFabric")
        self.assertIsNotNone(cable.cf[LAST_SYNCHRONIZED_CF_NAME])

    def test_create_cable_returns_none_when_status_unavailable(self):
        """No Cable is created if the Status cannot be resolved."""
        logger = mock.MagicMock()
        with mock.patch(f"{_CABLES}.get_or_create_status_object", return_value=None):
            cable = cables.create_cable(self.int_a, self.int_b, "Nonexistent", logger=logger)

        self.assertIsNone(cable)
        self.assertEqual(Cable.objects.count(), 0)
        logger.error.assert_called_once()

    def test_create_cable_returns_none_on_validation_error(self):
        """Nautobot refuses to cable virtual Interfaces, which is reported rather than raised."""
        logger = mock.MagicMock()
        virtual = self._interface("vlan10", interface_type="virtual")

        cable = cables.create_cable(self.int_a, virtual, "Connected", logger=logger)

        self.assertIsNone(cable)
        self.assertEqual(Cable.objects.count(), 0)
        logger.error.assert_called_once()

    def test_create_cable_warns_when_tagging_fails(self):
        """A tagging failure is a warning; the Cable itself is still returned."""
        logger = mock.MagicMock()
        with mock.patch(f"{_CABLES}.tag_object", side_effect=ValidationError("tag boom")):
            cable = cables.create_cable(self.int_a, self.int_b, "Connected", logger=logger)

        self.assertIsNotNone(cable)
        logger.warning.assert_called_once()

    # ------------------------------------------------------------------
    # update_cable_status
    # ------------------------------------------------------------------

    def _cable(self, status=None):
        cable = Cable(
            termination_a=self.int_a,
            termination_b=self.int_b,
            status=status or self.connected_status,
        )
        cable.validated_save()
        return cable

    def test_update_cable_status_changes_status(self):
        """A differing Status is replaced and the Cable stamped as synced."""
        cable = self._cable(status=Status.objects.get(name="Planned"))

        self.assertTrue(cables.update_cable_status(cable, "Connected"))

        cable.refresh_from_db()
        self.assertEqual(cable.status, self.connected_status)
        self.assertEqual(cable.cf["system_of_record"], "IPFabric")

    def test_update_cable_status_leaves_matching_status_alone(self):
        """A Status that already matches is not re-resolved."""
        cable = self._cable()

        with mock.patch(f"{_CABLES}.get_or_create_status_object") as mock_status:
            self.assertTrue(cables.update_cable_status(cable, "Connected"))

        mock_status.assert_not_called()
        cable.refresh_from_db()
        self.assertEqual(cable.status, self.connected_status)

    def test_update_cable_status_returns_false_when_status_unavailable(self):
        """An unresolvable Status leaves the Cable untouched."""
        logger = mock.MagicMock()
        cable = self._cable()

        with mock.patch(f"{_CABLES}.get_or_create_status_object", return_value=None):
            self.assertFalse(cables.update_cable_status(cable, "Nonexistent", logger=logger))

        cable.refresh_from_db()
        self.assertEqual(cable.status, self.connected_status)
        logger.error.assert_called_once()

    def test_update_cable_status_returns_false_when_save_fails(self):
        """A failure to save is reported and returns False."""
        logger = mock.MagicMock()
        cable = self._cable()

        with mock.patch(f"{_CABLES}.tag_object", side_effect=DjangoBaseDBError("save boom")):
            self.assertFalse(cables.update_cable_status(cable, "Connected", logger=logger))

        logger.error.assert_called_once()

    # ------------------------------------------------------------------
    # cable_connects
    # ------------------------------------------------------------------

    def test_cable_connects(self):
        """Endpoint order does not matter, and a different Interface does not match."""
        other = self._interface("eth3")
        cable = self._cable()

        self.assertTrue(cables.cable_connects(cable, self.int_a, self.int_b))
        self.assertTrue(cables.cable_connects(cable, self.int_b, self.int_a))
        self.assertFalse(cables.cable_connects(cable, self.int_a, other))

    def test_canonical_endpoints_orders_by_device_then_interface(self):
        """Endpoints sort on the (device, interface) pair so both adapters agree on the A side."""
        self.assertEqual(
            (("dev-a", "eth0"), ("dev-b", "eth0")),
            cables.canonical_endpoints(("dev-b", "eth0"), ("dev-a", "eth0")),
        )
        self.assertEqual(
            (("dev-a", "eth0"), ("dev-a", "eth1")),
            cables.canonical_endpoints(("dev-a", "eth1"), ("dev-a", "eth0")),
        )
