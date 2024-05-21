# Upgrading from SSoT 2.x to 3.x

As part of the changes required for utilizing DiffSync 2.0 and pydantic v2 any SSoT Apps that were written prior to SSoT 3.x will need to be updated. The following pieces will need to be changed:

- Replace instances of `DiffSync` class with `Adapter` class.
- Set default value of `None` for any `Optional` class attributes on `DiffSyncModel` or `NautobotModel` objects.
- Replace any kwargs using `diffsync` to be `adapter`.

## Replace DiffSync class with Adapter class

Any places in your SSoT App where you've imported DiffSync, replace with Adapter. For example:

```python
from diffsync import DiffSync

class NautobotAdapter(DiffSync)
```

```python
from diffsync import Adapter

class NautobotAdapter(Adapter)
```

## Set defaults for Optional

One of the changes with pydantic v2 is that any variables that are Optional must have a default of None defined. This needs to be done on your class attributes like below:

```python
class DeviceModel(NautobotModel):

    _model = Device
    _modelname = "device"
    _identifiers = ("name", "location__name", "location__parent__name")
    _attributes = (
        "location__location_type__name",
        "location__parent__location_type__name",
        "device_type__manufacturer__name",
        "device_type__model",
        "platform__name",
        "role__name",
        "serial",
        "status__name",
    )

    name: str
    location__name: str
    location__location_type__name: str
    location__parent__name: Optional[str]
    location__parent__location_type__name: Optional[str]
    device_type__manufacturer__name: str
    device_type__model: str
    platform__name: Optional[str]
    role__name: str
    serial: str
    status__name: str
```

is changed to the following:

```python
class DeviceModel(NautobotModel):

    _model = Device
    _modelname = "device"
    _identifiers = ("name", "location__name", "location__parent__name")
    _attributes = (
        "location__location_type__name",
        "location__parent__location_type__name",
        "device_type__manufacturer__name",
        "device_type__model",
        "platform__name",
        "role__name",
        "serial",
        "status__name",
    )

    name: str
    location__name: str
    location__location_type__name: str
    location__parent__name: Optional[str] = None
    location__parent__location_type__name: Optional[str] = None
    device_type__manufacturer__name: str
    device_type__model: str
    platform__name: Optional[str] = None
    role__name: str
    serial: str
    status__name: str
```

## Replace diffsync kwarg with adapter

Any instances where you're referring to the diffsync kwarg needs to be updated to be adapter instead:

```python
self.diffsync.job.logger.warning("Example")
```

```python
self.adapter.job.logger.warning("Example")
```
