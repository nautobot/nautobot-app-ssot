"""Sample data-source and data-target Jobs."""

# Skip colon check for multiple statements on one line.
# flake8: noqa: E701

from typing import Optional, Mapping, List
from uuid import UUID
from django.templatetags.static import static
from django.urls import reverse

from nautobot.dcim.models import Location, LocationType
from nautobot.extras.jobs import StringVar
from nautobot.ipam.models import Prefix
from nautobot.tenancy.models import Tenant

from diffsync import DiffSync
from diffsync.enum import DiffSyncFlags

import requests

from nautobot_ssot.contrib import NautobotModel, NautobotAdapter
from nautobot_ssot.jobs.base import DataMapping, DataSource, DataTarget


# In a more complex Job, you would probably want to move the DiffSyncModel subclasses into a separate Python module(s).

name = "SSoT Examples"  # pylint: disable=invalid-name


class LocationTypeModel(NautobotModel):
    """Shared data model representing a LocationType in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _model = LocationType
    _modelname = "locationtype"
    _identifiers = ("name",)
    # To keep this example simple, we don't include **all** attributes of a Location here. But you could!
    _attributes = ("description", "nestable")

    # Data type declarations for all identifiers and attributes
    name: str
    description: str
    nestable: bool

    # Not in _attributes or _identifiers, hence not included in diff calculations
    pk: Optional[UUID]


class LocationModel(NautobotModel):
    """Shared data model representing a Location in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _model = Location
    _modelname = "location"
    _identifiers = ("name",)
    # To keep this example simple, we don't include **all** attributes of a Location here. But you could!
    _attributes = ("location_type__name", "status__name", "parent__name", "description")

    # Data type declarations for all identifiers and attributes
    name: str
    location_type__name: str
    status__name: str
    parent__name: Optional[str]
    description: str

    # Not in _attributes or _identifiers, hence not included in diff calculations
    pk: Optional[UUID]


class PrefixModel(NautobotModel):
    """Shared data model representing a Prefix in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _model = Prefix
    _modelname = "prefix"
    _identifiers = ("prefix", "tenant__name")
    # To keep this example simple, we don't include **all** attributes of a Prefix here. But you could!
    _attributes = ("description", "status__name")

    # Data type declarations for all identifiers and attributes
    prefix: str
    tenant__name: Optional[str]
    status__name: str
    description: str

    # Not in _attributes or _identifiers, hence not included in diff calculations
    pk: Optional[UUID]


class TenantModel(NautobotModel):
    """Shared data model representing a Tenant in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _model = Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _children = {"prefix": "prefixes"}

    name: str
    prefixes: List[PrefixModel] = []

    pk: Optional[UUID]


class LocationRemoteModel(LocationModel):
    """Implementation of Location create/update/delete methods for updating remote Nautobot data."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create a new Location in remote Nautobot.

        Args:
            diffsync (NautobotRemote): DiffSync adapter owning this Site
            ids (dict): Initial values for this model's _identifiers
            attrs (dict): Initial values for this model's _attributes
        """
        diffsync.post(
            "/api/dcim/locations/",
            {
                "name": ids["name"],
                "description": attrs["description"],
                "status": attrs["status__name"],
                "location_type": attrs["location_type__name"],
                "parent": {"name": attrs["parent__name"]} if attrs["parent__name"] else None,
            },
        )
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update an existing Site record in remote Nautobot.

        Args:
            attrs (dict): Updated values for this record's _attributes
        """
        data = {}
        if "description" in attrs:
            data["description"] = attrs["description"]
        if "status" in attrs:
            data["status"] = attrs["status__name"]
        if "parent__name" in attrs:
            if attrs["parent__name"]:
                data["parent"] = {"name": attrs["parent__name"]}
            else:
                data["parent"] = None
        self.diffsync.patch(f"/api/dcim/locations/{self.pk}/", data)
        return super().update(attrs)

    def delete(self):
        """Delete an existing Site record from remote Nautobot."""
        self.diffsync.delete(f"/api/dcim/locations/{self.pk}/")
        return super().delete()


class TenantRemoteModel(TenantModel):
    """Implementation of Tenant create/update/delete methods for updating remote Nautobot data."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create a new Tenant in remote Nautobot."""
        diffsync.post(
            "/api/tenancy/tenants/",
            {
                "name": ids["name"],
            },
        )
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Updating tenants is not supported because we don't have any attributes."""
        raise NotImplementedError("Can't update tenants - they only have a name.")

    def delete(self):
        """Delete a Tenant in remote Nautobot."""
        self.diffsync.delete(f"/api/tenancy/tenants/{self.pk}/")
        return super().delete()


class PrefixRemoteModel(PrefixModel):
    """Implementation of Prefix create/update/delete methods for updating remote Nautobot data."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create a new Prefix in remote Nautobot.

        Args:
            diffsync (NautobotRemote): DiffSync adapter owning this Prefix
            ids (dict): Initial values for this model's _identifiers
            attrs (dict): Initial values for this model's _attributes
        """
        diffsync.post(
            "/api/ipam/prefixes/",
            {
                "prefix": ids["prefix"],
                "tenant": {"name": ids["tenant__name"]} if ids["tenant__name"] else None,
                "description": attrs["description"],
                "status": attrs["status__name"],
            },
        )
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update an existing Site record in remote Nautobot.

        Args:
            attrs (dict): Updated values for this record's _attributes
        """
        data = {}
        if "description" in attrs:
            data["description"] = attrs["description"]
        if "status" in attrs:
            data["status"] = attrs["status__name"]
        self.diffsync.patch(f"/api/dcim/locations/{self.pk}/", data)
        return super().update(attrs)

    def delete(self):
        """Delete an existing Site record from remote Nautobot."""
        self.diffsync.delete(f"/api/dcim/locations/{self.pk}/")
        return super().delete()


# In a more complex Job, you would probably want to move each DiffSync subclass into a separate Python module.


class NautobotRemote(DiffSync):
    """DiffSync adapter class for loading data from a remote Nautobot instance using Python requests.

    In a more realistic example, you'd probably use PyNautobot here instead of raw requests,
    but we didn't want to add PyNautobot as a dependency of this app just to make an example more realistic.
    """

    # Model classes used by this adapter class
    locationtype = LocationTypeModel
    location = LocationRemoteModel
    tenant = TenantRemoteModel
    prefix = PrefixRemoteModel

    # Top-level class labels, i.e. those classes that are handled directly rather than as children of other models
    top_level = ["locationtype", "location", "tenant"]

    def __init__(self, *args, url=None, token=None, job=None, **kwargs):
        """Instantiate this class, but do not load data immediately from the remote system.

        Args:
            url (str): URL of the remote Nautobot system
            token (str): REST API authentication token
            job (Job): The running Job instance that owns this DiffSync adapter instance
        """
        super().__init__(*args, **kwargs)
        if not url or not token:
            raise ValueError("Both url and token must be specified!")
        if not url.startswith("http"):
            raise ValueError("The url must start with a schema.")
        self.url = url
        self.token = token
        self.job = job
        self.headers = {
            "Accept": "application/json",
            "Authorization": f"Token {self.token}",
        }

    def _get_api_data(self, url_path: str) -> Mapping:
        """Returns data from a url_path using pagination."""
        data = requests.get(f"{self.url}/{url_path}", headers=self.headers, params={"limit": 0}, timeout=60).json()
        result_data = data["results"]
        while data["next"]:
            data = requests.get(data["next"], headers=self.headers, params={"limit": 0}, timeout=60).json()
            result_data.extend(data["results"])
        return result_data

    def load(self):
        """Load Region and Site data from the remote Nautobot instance."""
        for lt_entry in self._get_api_data("api/dcim/location-types/"):
            location_type = self.locationtype(
                name=lt_entry["name"],
                description=lt_entry["description"],
                nestable=lt_entry["nestable"],
                pk=lt_entry["id"],
            )
            self.add(location_type)
            self.job.logger.debug(f"Loaded {location_type} LocationType from remote Nautobot instance")

        for loc_entry in self._get_api_data("api/dcim/locations/?depth=1"):
            location_args = {
                "name": loc_entry["name"],
                "status__name": loc_entry["status"]["name"] if loc_entry["status"].get("name") else "Active",
                "location_type__name": loc_entry["location_type"]["name"],
                "description": loc_entry["description"],
                "pk": loc_entry["id"],
            }
            if loc_entry["parent"]:
                location_args["parent_name"] = loc_entry["parent"]["name"]
            new_location = self.location(**location_args)
            self.add(new_location)
            self.job.logger.debug(f"Loaded {new_location} Location from remote Nautobot instance")

        for prefix_entry in self._get_api_data("api/ipam/prefixes/?depth=1"):
            prefix = self.prefix(
                prefix=prefix_entry["prefix"],
                description=prefix_entry["description"],
                status__name=prefix_entry["status"]["name"] if prefix_entry["status"].get("name") else "Active",
                tenant__name=prefix_entry["tenant"]["name"] if prefix_entry["tenant"] else "",
                pk=prefix_entry["id"],
            )
            self.add(prefix)
            self.job.logger.debug(f"Loaded {prefix} from remote Nautobot instance")

    def post(self, path, data):
        """Send an appropriately constructed HTTP POST request."""
        response = requests.post(f"{self.url}{path}", headers=self.headers, json=data, timeout=60)
        response.raise_for_status()
        return response

    def patch(self, path, data):
        """Send an appropriately constructed HTTP PATCH request."""
        response = requests.patch(f"{self.url}{path}", headers=self.headers, json=data, timeout=60)
        response.raise_for_status()
        return response

    def delete(self, path):
        """Send an appropriately constructed HTTP DELETE request."""
        response = requests.delete(f"{self.url}{path}", headers=self.headers, timeout=60)
        response.raise_for_status()
        return response


class NautobotLocal(NautobotAdapter):
    """DiffSync adapter class for loading data from the local Nautobot instance."""

    # Model classes used by this adapter class
    locationtype = LocationTypeModel
    location = LocationModel
    tenant = TenantModel
    prefix = PrefixModel

    # Top-level class labels, i.e. those classes that are handled directly rather than as children of other models
    top_level = ["locationtype", "location", "prefix"]

    def load(self):
        """Load LocationType and Location data from the local Nautobot instance."""
        for loc_type in LocationType.objects.all():
            new_lt = self.locationtype(
                name=loc_type.name,
                description=loc_type.description,
                nestable=loc_type.nestable,
                pk=loc_type.pk,
            )
            self.add(new_lt)
            self.job.logger.debug(f"Loaded {new_lt} LocationType from local Nautobot instance")

        for location in Location.objects.all():
            loc_model = self.location(
                name=location.name,
                status=location.status.name,
                location_type=location.location_type.name,
                parent__name=location.parent.name if location.parent else "",
                description=location.description,
                pk=location.pk,
            )
            self.add(loc_model)
            self.job.logger.debug(f"Loaded {loc_model} Location from local Nautobot instance")

        for prefix in Prefix.objects.all():
            prefix_model = self.prefix(
                prefix=str(prefix.prefix),
                description=prefix.description,
                status=prefix.status.name,
                tenant__name=prefix.tenant.name if prefix.tenant else "",
                pk=prefix.pk,
            )
            self.add(prefix_model)
            self.job.logger.debug(f"Loaded {prefix_model} from local Nautobot instance")


# The actual Data Source and Data Target Jobs are relatively simple to implement
# once you have the above DiffSync scaffolding in place.


class ExampleDataSource(DataSource):
    """Sync Region and Site data from a remote Nautobot instance into the local Nautobot instance."""

    source_url = StringVar(
        description="Remote Nautobot instance to load Sites and Regions from", default="https://demo.nautobot.com"
    )
    source_token = StringVar(description="REST API authentication token for remote Nautobot instance", default="a" * 40)

    def __init__(self):
        """Initialize ExampleDataSource."""
        super().__init__()
        self.diffsync_flags = (
            self.diffsync_flags | DiffSyncFlags.SKIP_UNMATCHED_DST  # pylint:disable=unsupported-binary-operation
        )

    class Meta:
        """Metaclass attributes of ExampleDataSource."""

        name = "Example Data Source"
        description = 'Example "data source" Job for loading data into Nautobot from another system.'
        data_source = "Nautobot (remote)"
        data_source_icon = static("img/nautobot_logo.png")

    @classmethod
    def data_mappings(cls):
        """This Job maps Region and Site objects from the remote system to the local system."""
        return (
            DataMapping("Region (remote)", None, "Region (local)", reverse("dcim:location_list")),
            DataMapping("Site (remote)", None, "Site (local)", reverse("dcim:location_list")),
            DataMapping("Prefix (remote)", None, "Prefix (local)", reverse("ipam:prefix_list")),
        )

    def run(
        self, dryrun, memory_profiling, source_url, source_token, *args, **kwargs
    ):  # pylint:disable=arguments-differ
        """Run sync."""
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        self.source_url = source_url
        self.source_token = source_token
        super().run(dryrun, memory_profiling, *args, **kwargs)

    def load_source_adapter(self):
        """Method to instantiate and load the SOURCE adapter into `self.source_adapter`."""
        self.source_adapter = NautobotRemote(url=self.source_url, token=self.source_token, job=self)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Method to instantiate and load the TARGET adapter into `self.target_adapter`."""
        self.target_adapter = NautobotLocal(job=self, sync=self.sync)
        self.target_adapter.load()
        self.logger.info(f"Found {self.target_adapter.count('region')} regions")

    def lookup_object(self, model_name, unique_id):
        """Look up a Nautobot object based on the DiffSync model name and unique ID."""
        if model_name == "region":
            try:
                return Location.objects.get(
                    name=unique_id, location_type=LocationType.objects.get_or_create(name="Region")[0]
                )
            except Location.DoesNotExist:
                pass
        elif model_name == "site":
            try:
                return Location.objects.get(
                    name=unique_id, location_type=LocationType.objects.get_or_create(name="Site")[0]
                )
            except Location.DoesNotExist:
                pass
        elif model_name == "prefix":
            try:
                return Prefix.objects.get(
                    prefix=unique_id.split("__")[0], tenant__name=unique_id.split("__")[1] or None
                )
            except Prefix.DoesNotExist:
                pass
        return None


class ExampleDataTarget(DataTarget):
    """Sync Region and Site data from the local Nautobot instance to a remote Nautobot instance."""

    target_url = StringVar(description="Remote Nautobot instance to update", default="https://demo.nautobot.com")
    target_token = StringVar(description="REST API authentication token for remote Nautobot instance", default="a" * 40)

    def __init__(self):
        """Initialize ExampleDataTarget."""
        super().__init__()
        self.diffsync_flags = (
            self.diffsync_flags | DiffSyncFlags.SKIP_UNMATCHED_DST  # pylint:disable=unsupported-binary-operation
        )

    class Meta:
        """Metaclass attributes of ExampleDataTarget."""

        name = "Example Data Target"
        description = 'Example "data target" Job for syncing data from Nautobot to another system'
        data_target = "Nautobot (remote)"
        data_target_icon = static("img/nautobot_logo.png")

    @classmethod
    def data_mappings(cls):
        """This Job maps Region and Site objects from the local system to the remote system."""
        return (
            DataMapping("Region (local)", reverse("dcim:location_list"), "Region (remote)", None),
            DataMapping("Site (local)", reverse("dcim:location_list"), "Site (remote)", None),
            DataMapping("Prefix (local)", reverse("ipam:prefix_list"), "Prefix (remote)", None),
        )

    def load_source_adapter(self):
        """Method to instantiate and load the SOURCE adapter into `self.source_adapter`."""
        self.source_adapter = NautobotLocal(job=self, sync=self.sync)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Method to instantiate and load the TARGET adapter into `self.target_adapter`."""
        self.target_adapter = NautobotRemote(url=self.target_url, token=self.target_token, job=self)
        self.target_adapter.load()

    def lookup_object(self, model_name, unique_id):
        """Look up a Nautobot object based on the DiffSync model name and unique ID."""
        if model_name == "region":
            try:
                return Location.objects.get(
                    name=unique_id, location_type=LocationType.objects.get_or_create(name="Region")[0]
                )
            except Location.DoesNotExist:
                pass
        elif model_name == "site":
            try:
                return Location.objects.get(
                    name=unique_id, location_type=LocationType.objects.get_or_create(name="Site")
                )
            except Location.DoesNotExist:
                pass
        elif model_name == "prefix":
            try:
                return Prefix.objects.get(
                    prefix=unique_id.split("__")[0], tenant__name=unique_id.split("__")[1] or None
                )
            except Prefix.DoesNotExist:
                pass
        return None
