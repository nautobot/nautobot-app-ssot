"""Tests for the shared integration metadata utilities."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Location, LocationType
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Status
from nautobot.extras.models.metadata import MetadataType, MetadataTypeDataTypeChoices, ObjectMetadata

from nautobot_ssot.integrations.metadata_utils import add_or_update_metadata_on_object, get_last_sync_value

DATA_SOURCE = "DNA Center"
METADATA_TYPE_NAME = f"Last Sync from {DATA_SOURCE}"
SCOPED_FIELDS = {"dcim.location": ["name", "location_type", "status"]}


class TestGetLastSyncValue(TestCase):
    """Test formatting of the last sync value for each supported MetadataType data type."""

    now = datetime(2025, 9, 1, 7, 33, 53, 123456)

    def test_date_type_returns_date_only(self):
        """A DATE MetadataType gets a YYYY-MM-DD value."""
        metadata_type = MetadataType(name="date-type", data_type=MetadataTypeDataTypeChoices.TYPE_DATE)
        self.assertEqual(get_last_sync_value(metadata_type, now=self.now), "2025-09-01")

    def test_datetime_type_returns_iso_datetime(self):
        """A DATETIME MetadataType gets a YYYY-MM-DDTHH:MM:SS value."""
        metadata_type = MetadataType(name="datetime-type", data_type=MetadataTypeDataTypeChoices.TYPE_DATETIME)
        self.assertEqual(get_last_sync_value(metadata_type, now=self.now), "2025-09-01T07:33:53")


class TestAddOrUpdateMetadataOnObject(TestCase):
    """Test add_or_update_metadata_on_object against DATE and DATETIME MetadataTypes."""

    def setUp(self):
        """Create a Location to attach metadata to and a mock adapter."""
        super().setUp()
        populate_status_choices()
        location_type = LocationType.objects.get_or_create(name="Site")[0]
        status = Status.objects.get(name="Active")
        self.location = Location.objects.create(name="HQ", location_type=location_type, status=status)
        self.job = MagicMock()
        self.job.data_source = DATA_SOURCE
        self.job.debug = False
        self.adapter = SimpleNamespace(job=self.job)

    def _sync(self):
        metadata = add_or_update_metadata_on_object(
            adapter=self.adapter, obj=self.location, scoped_fields=SCOPED_FIELDS
        )
        metadata.validated_save()
        return metadata

    def test_creates_datetime_type_by_default(self):
        """A fresh install gets a DATETIME MetadataType and a datetime value that passes validation."""
        metadata = self._sync()
        metadata_type = MetadataType.objects.get(name=METADATA_TYPE_NAME)
        self.assertEqual(metadata_type.data_type, MetadataTypeDataTypeChoices.TYPE_DATETIME)
        stored = ObjectMetadata.objects.get(pk=metadata.pk)
        self.assertIsInstance(datetime.fromisoformat(str(stored.value)), datetime)
        self.assertEqual(sorted(stored.scoped_fields), sorted(SCOPED_FIELDS["dcim.location"]))
        self.job.logger.info.assert_not_called()

    def test_existing_date_type_gets_date_value(self):
        """A pre-existing DATE MetadataType (created by older releases) gets a YYYY-MM-DD value."""
        MetadataType.objects.create(name=METADATA_TYPE_NAME, data_type=MetadataTypeDataTypeChoices.TYPE_DATE)
        metadata = self._sync()
        stored = ObjectMetadata.objects.get(pk=metadata.pk)
        self.assertEqual(str(stored.value), datetime.now().date().isoformat())
        self.assertEqual(
            MetadataType.objects.get(name=METADATA_TYPE_NAME).data_type, MetadataTypeDataTypeChoices.TYPE_DATE
        )

    def test_existing_date_type_updates_existing_metadata(self):
        """Updating existing ObjectMetadata of a DATE MetadataType also succeeds, logging the notice once."""
        MetadataType.objects.create(name=METADATA_TYPE_NAME, data_type=MetadataTypeDataTypeChoices.TYPE_DATE)
        first = self._sync()
        second = self._sync()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(str(second.value), datetime.now().date().isoformat())
        self.job.logger.info.assert_called_once()
