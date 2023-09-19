"""Sample data-source and data-target Jobs."""
# Skip colon check for multiple statements on one line.
# flake8: noqa: E701

from typing import Optional, Mapping, List
from uuid import UUID
from django.templatetags.static import static
from django.urls import reverse

from nautobot.dcim.models import Region, Site
from nautobot.ipam.models import Prefix
from nautobot.tenancy.models import Tenant
from nautobot.extras.jobs import Job, StringVar

from diffsync import DiffSync
from diffsync.enum import DiffSyncFlags

import requests

from nautobot_ssot.contrib import NautobotModel, NautobotAdapter
from nautobot_ssot.jobs.base import DataMapping, DataSource, DataTarget


# In a more complex Job, you would probably want to move the DiffSyncModel subclasses into a separate Python module(s).

name = "SSoT Examples"  # pylint: disable=invalid-name


class RegionModel(NautobotModel):
    """Shared data model representing a Region in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _model = Region
    _modelname = "region"
    _identifiers = ("name",)
    _attributes = ("slug", "description", "parent__name")

    # Data type declarations for all identifiers and attributes
    name: str
    slug: str
    description: str
    parent__name: Optional[str]  # may be None

    # Not in _attributes or _identifiers, hence not included in diff calculations
    pk: Optional[UUID]


class SiteModel(NautobotModel):
    """Shared data model representing a Site in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _model = Site
    _modelname = "site"
    _identifiers = ("name",)
    # To keep this example simple, we don't include **all** attributes of a Site here. But you could!
    _attributes = ("slug", "status__slug", "region__name", "description")

    # Data type declarations for all identifiers and attributes
    name: str
    slug: str
    status__slug: str
    region__name: Optional[str]  # may be None
    description: str

    # Not in _attributes or _identifiers, hence not included in diff calculations
    pk: Optional[UUID]


class PrefixModel(NautobotModel):
    """Shared data model representing a Prefix in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _model = Prefix
    _modelname = "prefix"
    _identifiers = ("network", "prefix_length", "tenant__slug")
    # To keep this example simple, we don't include **all** attributes of a Prefix here. But you could!
    _attributes = ("description", "status__slug")

    # Data type declarations for all identifiers and attributes
    network: str
    prefix_length: str
    tenant__slug: str
    status__slug: str
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


class RegionRemoteModel(RegionModel):
    """Implementation of Region create/update/delete methods for updating remote Nautobot data."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create a new Region record in remote Nautobot.

        Args:
            diffsync (NautobotRemote): DiffSync adapter owning this Region
            ids (dict): Initial values for this model's _identifiers
            attrs (dict): Initial values for this model's _attributes
        """
        diffsync.post(
            "/api/dcim/regions/",
            {
                "name": ids["name"],
                "slug": attrs["slug"],
                "description": attrs["description"],
                "parent": {"name": attrs["parent__name"]} if attrs["parent__name"] else None,
            },
        )
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update an existing Region record in remote Nautobot.

        Args:
            attrs (dict): Updated values for this record's _attributes
        """
        data = {}
        if "slug" in attrs:
            data["slug"] = attrs["slug"]
        if "description" in attrs:
            data["description"] = attrs["description"]
        if "parent__name" in attrs:
            if attrs["parent__name"]:
                data["parent"] = {"name": attrs["parent__name"]}
            else:
                data["parent"] = None
        self.diffsync.patch(f"/api/dcim/regions/{self.pk}/", data)
        return super().update(attrs)

    def delete(self):
        """Delete an existing Region record from remote Nautobot."""
        self.diffsync.delete(f"/api/dcim/regions/{self.pk}/")
        return super().delete()


class SiteRemoteModel(SiteModel):
    """Implementation of Site create/update/delete methods for updating remote Nautobot data."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create a new Site in remote Nautobot.

        Args:
            diffsync (NautobotRemote): DiffSync adapter owning this Site
            ids (dict): Initial values for this model's _identifiers
            attrs (dict): Initial values for this model's _attributes
        """
        diffsync.post(
            "/api/dcim/sites/",
            {
                "name": ids["name"],
                "slug": attrs["slug"],
                "description": attrs["description"],
                "status": attrs["status__slug"],
                "region": {"name": attrs["region__name"]} if attrs["region__name"] else None,
            },
        )
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update an existing Site record in remote Nautobot.

        Args:
            attrs (dict): Updated values for this record's _attributes
        """
        data = {}
        if "slug" in attrs:
            data["slug"] = attrs["slug"]
        if "description" in attrs:
            data["description"] = attrs["description"]
        if "status__slug" in attrs:
            data["status"] = attrs["status__slug"]
        if "region__name" in attrs:
            if attrs["region__name"]:
                data["region"] = {"name": attrs["region__name"]}
            else:
                data["region"] = None
        self.diffsync.patch(f"/api/dcim/sites/{self.pk}/", data)
        return super().update(attrs)

    def delete(self):
        """Delete an existing Site record from remote Nautobot."""
        self.diffsync.delete(f"/api/dcim/sites/{self.pk}/")
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
                "tenant": {"slug": ids["tenant__slug"]} if ids["tenant__slug"] else None,
                "description": attrs["description"],
                "status": attrs["status__slug"],
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
        if "status__slug" in attrs:
            data["status"] = attrs["status__slug"]
        self.diffsync.patch(f"/api/dcim/sites/{self.pk}/", data)
        return super().update(attrs)

    def delete(self):
        """Delete an existing Site record from remote Nautobot."""
        self.diffsync.delete(f"/api/dcim/sites/{self.pk}/")
        return super().delete()


# In a more complex Job, you would probably want to move each DiffSync subclass into a separate Python module.


class NautobotRemote(DiffSync):
    """DiffSync adapter class for loading data from a remote Nautobot instance using Python requests.

    In a more realistic example, you'd probably use PyNautobot here instead of raw requests,
    but we didn't want to add PyNautobot as a dependency of this plugin just to make an example more realistic.
    """

    # Model classes used by this adapter class
    region = RegionRemoteModel
    site = SiteRemoteModel
    tenant = TenantRemoteModel
    prefix = PrefixRemoteModel

    # Top-level class labels, i.e. those classes that are handled directly rather than as children of other models
    top_level = ["region", "site", "tenant"]

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
        self.url = url
        self.token = token
        self.job = job
        self.headers = {
            "Accept": "application/json",
            "Authorization": f"Token {self.token}",
        }

    def _get_api_data(self, url_path: str) -> Mapping:
        """Returns data from a url_path using pagination."""
        response = requests.get(f"{self.url}/{url_path}", headers=self.headers, params={"limit": 0}, timeout=60)
        response.raise_for_status()
        data = response.json()
        result_data = data["results"]
        while data["next"]:
            data = requests.get(data["next"], headers=self.headers, params={"limit": 0}, timeout=60).json()
            result_data.extend(data["results"])
        return result_data

    def load(self):
        """Load Region and Site data from the remote Nautobot instance."""
        for region_entry in self._get_api_data("api/dcim/regions/"):
            region = self.region(
                name=region_entry["name"],
                slug=region_entry["slug"],
                description=region_entry["description"],
                parent__name=region_entry["parent"]["name"] if region_entry["parent"] else None,
                pk=region_entry["id"],
            )
            self.add(region)
            self.job.log_debug(message=f"Loaded {region} from remote Nautobot instance")

        for site_entry in self._get_api_data("api/dcim/sites/"):
            site = self.site(
                name=site_entry["name"],
                slug=site_entry["slug"],
                status__slug=site_entry["status"]["value"] if site_entry["status"] else "active",
                region__name=site_entry["region"]["name"] if site_entry["region"] else None,
                description=site_entry["description"],
                pk=site_entry["id"],
            )
            self.add(site)
            self.job.log_debug(message=f"Loaded {site} from remote Nautobot instance")

        for tenant_entry in self._get_api_data("api/tenancy/tenants/"):
            tenant = self.tenant(
                name=tenant_entry["name"],
            )
            self.add(tenant)
            for prefix_entry in self._get_api_data(f"api/ipam/prefixes/?tenant={tenant_entry['slug']}"):
                network, prefix_length = prefix_entry["prefix"].split("/")
                prefix = self.prefix(
                    network=network,
                    prefix_length=prefix_length,
                    description=prefix_entry["description"],
                    status__slug="active",  # Hardcode to get around custom statuses (don't want to sync those as well)
                    tenant__slug=prefix_entry["tenant"]["slug"] if prefix_entry["tenant"] else "",
                    pk=prefix_entry["id"],
                )
                self.add(prefix)
                tenant.add_child(prefix)
                self.job.log_debug(message=f"Loaded {prefix} from remote Nautobot instance")

    def post(self, path, data):
        """Send an appropriately constructed HTTP POST request."""
        response = requests.post(f"{self.url}{path}", headers=self.headers, timeout=60, json=data)
        response.raise_for_status()
        return response

    def patch(self, path, data):
        """Send an appropriately constructed HTTP PATCH request."""
        response = requests.patch(f"{self.url}{path}", headers=self.headers, timeout=60, json=data)
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
    region = RegionModel
    site = SiteModel
    tenant = TenantModel
    prefix = PrefixModel

    # Top-level class labels, i.e. those classes that are handled directly rather than as children of other models
    top_level = ["region", "site", "tenant"]


# The actual Data Source and Data Target Jobs are relatively simple to implement
# once you have the above DiffSync scaffolding in place.


class ExampleDataSource(DataSource, Job):
    """Sync Region and Site data from a remote Nautobot instance into the local Nautobot instance."""

    source_url = StringVar(
        description="Remote Nautobot instance to load Sites and Regions from", default="https://demo.nautobot.com"
    )
    source_token = StringVar(description="REST API authentication token for remote Nautobot instance", default="a" * 40)

    def __init__(self):
        """Initialize ExampleDataSource."""
        super().__init__()
        self.diffsync_flags = (
            self.diffsync_flags | DiffSyncFlags.SKIP_UNMATCHED_DST  # pylint: disable=unsupported-binary-operation
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
            DataMapping("Region (remote)", None, "Region (local)", reverse("dcim:region_list")),
            DataMapping("Site (remote)", None, "Site (local)", reverse("dcim:site_list")),
            DataMapping("Prefix (remote)", None, "Prefix (local)", reverse("ipam:prefix_list")),
        )

    def load_source_adapter(self):
        """Method to instantiate and load the SOURCE adapter into `self.source_adapter`."""
        self.source_adapter = NautobotRemote(url=self.kwargs["source_url"], token=self.kwargs["source_token"], job=self)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Method to instantiate and load the TARGET adapter into `self.target_adapter`."""
        self.target_adapter = NautobotLocal()
        self.target_adapter.load()
        self.log_info(obj=None, message=f"Found {self.target_adapter.count('region')} regions")

    def lookup_object(self, model_name, unique_id):
        """Look up a Nautobot object based on the DiffSync model name and unique ID."""
        if model_name == "region":
            try:
                return Region.objects.get(name=unique_id)
            except Region.DoesNotExist:
                pass
        elif model_name == "site":
            try:
                return Site.objects.get(name=unique_id)
            except Site.DoesNotExist:
                pass
        elif model_name == "prefix":
            try:
                return Prefix.objects.get(
                    prefix=unique_id.split("__")[0], tenant__slug=unique_id.split("__")[1] or None
                )
            except Prefix.DoesNotExist:
                pass
        return None


class ExampleDataTarget(DataTarget, Job):
    """Sync Region and Site data from the local Nautobot instance to a remote Nautobot instance."""

    target_url = StringVar(description="Remote Nautobot instance to update", default="https://demo.nautobot.com")
    target_token = StringVar(description="REST API authentication token for remote Nautobot instance", default="a" * 40)

    def __init__(self):
        """Initialize ExampleDataTarget."""
        super().__init__()
        self.diffsync_flags = (
            self.diffsync_flags | DiffSyncFlags.SKIP_UNMATCHED_DST  # pylint: disable=unsupported-binary-operation
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
            DataMapping("Region (local)", reverse("dcim:region_list"), "Region (remote)", None),
            DataMapping("Site (local)", reverse("dcim:site_list"), "Site (remote)", None),
            DataMapping("Prefix (local)", reverse("ipam:prefix_list"), "Prefix (remote)", None),
        )

    def load_source_adapter(self):
        """Method to instantiate and load the SOURCE adapter into `self.source_adapter`."""
        self.source_adapter = NautobotLocal()
        self.source_adapter.load()

    def load_target_adapter(self):
        """Method to instantiate and load the TARGET adapter into `self.target_adapter`."""
        self.target_adapter = NautobotRemote(url=self.kwargs["target_url"], token=self.kwargs["target_token"], job=self)
        self.target_adapter.load()

    def lookup_object(self, model_name, unique_id):
        """Look up a Nautobot object based on the DiffSync model name and unique ID."""
        if model_name == "region":
            try:
                return Region.objects.get(name=unique_id)
            except Region.DoesNotExist:
                pass
        elif model_name == "site":
            try:
                return Site.objects.get(name=unique_id)
            except Site.DoesNotExist:
                pass
        elif model_name == "prefix":
            try:
                return Prefix.objects.get(
                    prefix=unique_id.split("__")[0], tenant__slug=unique_id.split("__")[1] or None
                )
            except Prefix.DoesNotExist:
                pass
        return None
