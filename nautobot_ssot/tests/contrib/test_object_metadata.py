"""Tests for the generic ObjectMetadataAnnotation contrib feature."""

from __future__ import annotations

from typing import Annotated, Optional, get_args, get_type_hints
from unittest.mock import MagicMock

from diffsync.exceptions import ObjectCrudException
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Manufacturer
from nautobot.extras.models.metadata import MetadataType, ObjectMetadata

from nautobot_ssot.contrib import NautobotAdapter, NautobotModel, ObjectMetadataAnnotation
from nautobot_ssot.contrib.types import CustomAnnotation

METADATA_TYPE_NAME = "External System ID"


class _ManufacturerWithExternalId(NautobotModel):
    """Test DiffSync model: a Manufacturer with a metadata-backed external_id."""

    _model = Manufacturer
    _modelname = "manufacturer"
    _identifiers = ("name",)
    _attributes = ("external_id",)

    name: str
    external_id: Annotated[Optional[str], ObjectMetadataAnnotation(metadata_type_name=METADATA_TYPE_NAME)] = None


class _ManufacturerAdapter(NautobotAdapter):
    manufacturer = _ManufacturerWithExternalId
    top_level = ("manufacturer",)


class ObjectMetadataAnnotationTypeTests(TestCase):
    """The annotation dataclass behaves like the other contrib annotations."""

    def test_is_custom_annotation_subclass(self):
        annotation = ObjectMetadataAnnotation(metadata_type_name="External System ID")
        self.assertIsInstance(annotation, CustomAnnotation)

    def test_default_data_type_is_text(self):
        self.assertEqual(ObjectMetadataAnnotation(metadata_type_name="X").data_type, "text")

    def test_data_type_override(self):
        self.assertEqual(ObjectMetadataAnnotation(metadata_type_name="X", data_type="url").data_type, "url")

    def test_detectable_via_typing(self):
        class _Model:
            external_id: Annotated[Optional[str], ObjectMetadataAnnotation(metadata_type_name="External System ID")] = (
                None
            )
            name: str = ""

        hints = get_type_hints(_Model, include_extras=True)
        annotations = [a for a in get_args(hints["external_id"]) if isinstance(a, ObjectMetadataAnnotation)]
        self.assertEqual(len(annotations), 1)
        self.assertEqual(annotations[0].metadata_type_name, "External System ID")
        self.assertEqual([a for a in get_args(hints.get("name", str)) if isinstance(a, ObjectMetadataAnnotation)], [])


class ObjectMetadataReadTests(TestCase):
    """Loading reads the annotated field from ObjectMetadata."""

    @classmethod
    def setUpTestData(cls):
        cls.manufacturer_ct = ContentType.objects.get_for_model(Manufacturer)
        cls.metadata_type = MetadataType.objects.create(name=METADATA_TYPE_NAME, data_type="text")
        cls.metadata_type.content_types.add(cls.manufacturer_ct)

    def _add_metadata(self, obj, value):
        metadata = ObjectMetadata(metadata_type=self.metadata_type, assigned_object=obj, scoped_fields=[])
        metadata.value = value
        metadata.validated_save()

    def test_loads_metadata_value_into_field(self):
        manufacturer = Manufacturer.objects.create(name="Cisco")
        self._add_metadata(manufacturer, "SN-123")

        adapter = _ManufacturerAdapter(job=MagicMock())
        adapter.load()

        loaded = adapter.get(_ManufacturerWithExternalId, "Cisco")
        self.assertEqual(loaded.external_id, "SN-123")

    def test_missing_metadata_row_loads_none(self):
        Manufacturer.objects.create(name="Juniper")  # no metadata row

        adapter = _ManufacturerAdapter(job=MagicMock())
        adapter.load()

        self.assertIsNone(adapter.get(_ManufacturerWithExternalId, "Juniper").external_id)

    def test_no_n_plus_one_queries(self):
        # One manufacturer with metadata.
        first = Manufacturer.objects.create(name="Vendor-1")
        self._add_metadata(first, "SN-1")
        # Warm up ContentType / app caches so the comparison isn't skewed by first-call lookups.
        _ManufacturerAdapter(job=MagicMock()).load()
        with CaptureQueriesContext(connection) as one_obj:
            _ManufacturerAdapter(job=MagicMock()).load()

        # Several more manufacturers with metadata.
        for index in range(2, 6):
            extra = Manufacturer.objects.create(name=f"Vendor-{index}")
            self._add_metadata(extra, f"SN-{index}")
        with CaptureQueriesContext(connection) as five_obj:
            _ManufacturerAdapter(job=MagicMock()).load()

        # Query count must not grow with the number of objects (prefetch, not per-row).
        self.assertEqual(len(one_obj.captured_queries), len(five_obj.captured_queries))


class ObjectMetadataWriteTests(TestCase):
    """Create/update write the annotated field to ObjectMetadata."""

    @classmethod
    def setUpTestData(cls):
        cls.manufacturer_ct = ContentType.objects.get_for_model(Manufacturer)
        cls.metadata_type = MetadataType.objects.create(name=METADATA_TYPE_NAME, data_type="text")
        cls.metadata_type.content_types.add(cls.manufacturer_ct)

    def _metadata_value(self, obj):
        metadata = obj.associated_object_metadata.filter(metadata_type=self.metadata_type).first()
        return metadata.value if metadata else None

    def test_create_writes_metadata(self):
        adapter = _ManufacturerAdapter(job=MagicMock())
        _ManufacturerWithExternalId.create(adapter, {"name": "Cisco"}, {"external_id": "SN-123"})

        manufacturer = Manufacturer.objects.get(name="Cisco")
        self.assertEqual(self._metadata_value(manufacturer), "SN-123")
        metadata = manufacturer.associated_object_metadata.get(metadata_type=self.metadata_type)
        self.assertEqual(metadata.scoped_fields, [])

    def test_update_changes_metadata_in_place(self):
        adapter = _ManufacturerAdapter(job=MagicMock())
        _ManufacturerWithExternalId.create(adapter, {"name": "Cisco"}, {"external_id": "SN-123"})

        load_adapter = _ManufacturerAdapter(job=MagicMock())
        load_adapter.load()
        loaded = load_adapter.get(_ManufacturerWithExternalId, "Cisco")
        loaded.update({"external_id": "SN-999"})

        manufacturer = Manufacturer.objects.get(name="Cisco")
        self.assertEqual(self._metadata_value(manufacturer), "SN-999")
        # Exactly one row of this type (updated in place, not duplicated).
        self.assertEqual(manufacturer.associated_object_metadata.filter(metadata_type=self.metadata_type).count(), 1)

    def test_none_value_is_noop(self):
        adapter = _ManufacturerAdapter(job=MagicMock())
        _ManufacturerWithExternalId.create(adapter, {"name": "Aruba"}, {"external_id": None})

        manufacturer = Manufacturer.objects.get(name="Aruba")
        self.assertEqual(manufacturer.associated_object_metadata.filter(metadata_type=self.metadata_type).count(), 0)


class ObjectMetadataWriteErrorTests(TestCase):
    """Writes fail loudly when the backing MetadataType is missing or misconfigured."""

    def test_missing_metadata_type_raises(self):
        # No MetadataType named METADATA_TYPE_NAME exists.
        adapter = _ManufacturerAdapter(job=MagicMock())
        with self.assertRaises(ObjectCrudException) as context:
            _ManufacturerWithExternalId.create(adapter, {"name": "Cisco"}, {"external_id": "SN-1"})
        self.assertIn(METADATA_TYPE_NAME, str(context.exception))

    def test_content_type_not_attached_raises(self):
        # MetadataType exists but the Manufacturer content type is NOT attached.
        MetadataType.objects.create(name=METADATA_TYPE_NAME, data_type="text")
        adapter = _ManufacturerAdapter(job=MagicMock())
        with self.assertRaises(ObjectCrudException):
            _ManufacturerWithExternalId.create(adapter, {"name": "Cisco"}, {"external_id": "SN-1"})


class _FakeJobMeta:
    data_source = "Test Source"


class _FakeJob:
    """Minimal stand-in for a Nautobot Job (avoids mutating MagicMock's shared class)."""

    Meta = _FakeJobMeta

    def __init__(self):
        self.logger = MagicMock()


class ObjectMetadataCoexistenceTests(TestCase):
    """The annotation feature coexists with the adapter 'Last sync' metadata feature."""

    @classmethod
    def setUpTestData(cls):
        cls.manufacturer_ct = ContentType.objects.get_for_model(Manufacturer)
        cls.metadata_type = MetadataType.objects.create(name=METADATA_TYPE_NAME, data_type="text")
        cls.metadata_type.content_types.add(cls.manufacturer_ct)

    def test_annotation_and_last_sync_metadata_dont_collide(self):
        adapter = _ManufacturerAdapter(job=_FakeJob())
        adapter.get_or_create_metadatatype()  # enables the "Last sync from Test Source" feature

        _ManufacturerWithExternalId.create(adapter, {"name": "Cisco"}, {"external_id": "SN-123"})

        manufacturer = Manufacturer.objects.get(name="Cisco")
        external = manufacturer.associated_object_metadata.get(metadata_type=self.metadata_type)
        self.assertEqual(external.value, "SN-123")
        last_sync = manufacturer.associated_object_metadata.get(metadata_type=adapter.metadata_type)
        self.assertEqual(last_sync.metadata_type.name, "Last sync from Test Source")
