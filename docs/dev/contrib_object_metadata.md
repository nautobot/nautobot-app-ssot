# ObjectMetadata-Backed Fields (`ObjectMetadataAnnotation`)

`ObjectMetadataAnnotation` marks a DiffSync model field whose value lives in Nautobot
`ObjectMetadata` instead of a model field or custom field. Use it to persist an external
system's identifier (e.g. a record ID) on a Nautobot object so future syncs can correlate
the two records.

## Usage

```python
from typing import Annotated, Optional

from nautobot.dcim.models import Manufacturer
from nautobot_ssot.contrib import NautobotModel, ObjectMetadataAnnotation


class ManufacturerModel(NautobotModel):
    _model = Manufacturer
    _modelname = "manufacturer"
    _identifiers = ("name",)
    _attributes = ("external_id",)

    name: str
    external_id: Annotated[
        Optional[str], ObjectMetadataAnnotation(metadata_type_name="External System ID")
    ] = None
```

On load, `external_id` is read from the object's `ObjectMetadata` of type
`"External System ID"`. On create/update, the value is written back to that metadata (one
whole-object row per annotated field).

## Prerequisite: the MetadataType is integration-owned

Like `CustomFieldAnnotation` and `CustomRelationshipAnnotation`, contrib does **not** create
the backing schema. Your integration must create the `MetadataType` and attach the relevant
content type(s) before syncing (e.g. in a prerequisite step or migration):

```python
from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import Manufacturer
from nautobot.extras.models.metadata import MetadataType

metadata_type, _ = MetadataType.objects.get_or_create(
    name="External System ID", defaults={"data_type": "text"}
)
metadata_type.content_types.add(ContentType.objects.get_for_model(Manufacturer))
```

Reads are lenient (missing type or row resolves to `None`). Writes are strict: a missing or
misconfigured `MetadataType` raises `ObjectCrudException`. A `None` value is a no-op
(existing metadata is left unchanged; syncing `None` does not clear it).
