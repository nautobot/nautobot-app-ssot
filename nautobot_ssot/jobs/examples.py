"""Sample data-source and data-target Jobs."""
from typing import Optional, Mapping
from uuid import UUID
from django.contrib.contenttypes.models import ContentType
from django.templatetags.static import static
from django.urls import reverse

from nautobot.dcim.models import Region, Site
from nautobot.ipam.models import Prefix
from nautobot.tenancy.models import Tenant
from nautobot.extras.jobs import Job, StringVar
from nautobot.extras.models import Status

from diffsync import DiffSync, DiffSyncModel
from diffsync.enum import DiffSyncFlags

import requests

from nautobot_ssot.jobs.base import DataMapping, DataSource, DataTarget


# In a more complex Job, you would probably want to move the DiffSyncModel subclasses into a separate Python module(s).

name = "SSoT Examples"  # pylint: disable=invalid-name


class RegionModel(DiffSyncModel):
    """Shared data model representing a Region in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _modelname = "region"
    _identifiers = ("name",)
    _attributes = ("slug", "description", "parent_name")

    # Data type declarations for all identifiers and attributes
    name: str
    slug: str
    description: str
    parent_name: Optional[str]  # may be None

    # Not in _attributes or _identifiers, hence not included in diff calculations
    pk: Optional[UUID]


class SiteModel(DiffSyncModel):
    """Shared data model representing a Site in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _modelname = "site"
    _identifiers = ("name",)
    # To keep this example simple, we don't include **all** attributes of a Site here. But you could!
    _attributes = ("slug", "status_slug", "region_name", "description")

    # Data type declarations for all identifiers and attributes
    name: str
    slug: str
    status_slug: str
    region_name: Optional[str]  # may be None
    description: str

    # Not in _attributes or _identifiers, hence not included in diff calculations
    pk: Optional[UUID]


class PrefixModel(DiffSyncModel):
    """Shared data model representing a Prefix in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _modelname = "prefix"
    _identifiers = ("prefix", "tenant_slug")
    # To keep this example simple, we don't include **all** attributes of a Prefix here. But you could!
    _attributes = ("description", "status_slug")

    # Data type declarations for all identifiers and attributes
    prefix: str
    tenant_slug: str
    status_slug: str
    description: str

    # Not in _attributes or _identifiers, hence not included in diff calculations
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
                "parent": {"name": attrs["parent_name"]} if attrs["parent_name"] else None,
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
        if "parent_name" in attrs:
            if attrs["parent_name"]:
                data["parent"] = {"name": attrs["parent_name"]}
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
                "status": attrs["status_slug"],
                "region": {"name": attrs["region_name"]} if attrs["region_name"] else None,
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
        if "status_slug" in attrs:
            data["status"] = attrs["status_slug"]
        if "region_name" in attrs:
            if attrs["region_name"]:
                data["region"] = {"name": attrs["region_name"]}
            else:
                data["region"] = None
        self.diffsync.patch(f"/api/dcim/sites/{self.pk}/", data)
        return super().update(attrs)

    def delete(self):
        """Delete an existing Site record from remote Nautobot."""
        self.diffsync.delete(f"/api/dcim/sites/{self.pk}/")
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
                "tenant": {"slug": ids["tenant_slug"]} if ids["tenant_slug"] else None,
                "description": attrs["description"],
                "status": attrs["status_slug"],
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
        if "status_slug" in attrs:
            data["status"] = attrs["status_slug"]
        self.diffsync.patch(f"/api/dcim/sites/{self.pk}/", data)
        return super().update(attrs)

    def delete(self):
        """Delete an existing Site record from remote Nautobot."""
        self.diffsync.delete(f"/api/dcim/sites/{self.pk}/")
        return super().delete()


class RegionLocalModel(RegionModel):
    """Implementation of Region create/update/delete methods for updating local Nautobot data."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create a new Region record in local Nautobot.

        Args:
            diffsync (NautobotLocal): DiffSync adapter owning this Region
            ids (dict): Initial values for this model's _identifiers
            attrs (dict): Initial values for this model's _attributes
        """
        region = Region(
            name=ids["name"],
            slug=attrs["slug"],
            description=attrs["description"],
        )
        if attrs["parent_name"]:
            region.parent = Region.objects.get(name=attrs["parent_name"])
        region.validated_save()
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update an existing Region record in local Nautobot.

        Args:
            attrs (dict): Updated values for any of this model's _attributes
        """
        region = Region.objects.get(name=self.name)

        for attr_name in ("slug", "description"):
            if attr_name in attrs:
                setattr(region, attr_name, attrs[attr_name])

        if "parent_name" in attrs:
            region.parent = Region.objects.get(name=attrs["parent_name"])

        region.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete an existing Region record from local Nautobot."""
        region = Region.objects.get(name=self.name)
        region.delete()
        return super().delete()


class SiteLocalModel(SiteModel):
    """Implementation of Site create/update/delete methods for updating local Nautobot data."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create a new Site record in local Nautobot.

        Args:
            diffsync (NautobotLocal): DiffSync adapter owning this Site
            ids (dict): Initial values for this model's _identifiers
            attrs (dict): Initial values for this model's _attributes
        """
        site = Site(name=ids["name"], slug=attrs["slug"], description=attrs["description"])
        site.status = Status.objects.get(slug=attrs["status_slug"])
        if attrs["region_name"]:
            site.region = Region.objects.get(name=attrs["region_name"])
        site.validated_save()
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update an existing Site record in local Nautobot.

        Args:
            attrs (dict): Updated values for any of this model's _attributes
        """
        site = Site.objects.get(name=self.name)

        for attr_name in ("slug", "description"):
            if attr_name in attrs:
                setattr(site, attr_name, attrs[attr_name])

        if "status_slug" in attrs:
            site.status = Status.objects.get(slug=attrs["status_slug"])

        if "region_name" in attrs:
            site.region = Region.objects.get(name=attrs["region_name"])

        site.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete an existing Site record from local Nautobot."""
        site = Site.objects.get(name=self.name)
        site.delete()
        return super().delete()


class PrefixLocalModel(PrefixModel):
    """Implementation of Prefix create/update/delete methods for updating local Nautobot data."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create a new Prefix record in local Nautobot.

        Args:
            diffsync (NautobotLocal): DiffSync adapter owning this Prefix
            ids (dict): Initial values for this model's _identifiers
            attrs (dict): Initial values for this model's _attributes
        """
        prefix = Prefix(prefix=ids["prefix"], description=attrs["description"])
        if ids["tenant_slug"]:
            tenant_obj, _ = Tenant.objects.get_or_create(
                slug=ids["tenant_slug"],
                defaults={"name": ids["tenant_slug"]},
            )
            prefix.tenant = tenant_obj

        status_obj, _ = Status.objects.get_or_create(
            slug=attrs["status_slug"],
            defaults={"name": attrs["status_slug"]},
        )
        status_obj.content_types.add(ContentType.objects.get_for_model(Prefix))
        prefix.status = status_obj
        prefix.validated_save()
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update an existing Prefix record in local Nautobot.

        Args:
            attrs (dict): Updated values for any of this model's _attributes
        """
        prefix = Prefix.objects.get(prefix=self.prefix, tenant__slug=self.tenant_slug)
        for attr_name in ("description",):
            if attr_name in attrs:
                setattr(prefix, attr_name, attrs[attr_name])

        if "status_slug" in attrs:
            status_obj, _ = Status.objects.get_or_create(
                defaults={"name": attrs["status_slug"]},
            )
            status_obj.content_types.add(ContentType.objects.get_for_model(Prefix))
            prefix.status = status_obj
        prefix.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete an existing Prefix record from local Nautobot."""
        prefix = Prefix.objects.get(prefix=self.prefix, tenant__slug=self.tenant_slug)
        prefix.delete()
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
    prefix = PrefixRemoteModel

    # Top-level class labels, i.e. those classes that are handled directly rather than as children of other models
    top_level = ("region", "site", "prefix")

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
        data = requests.get(f"{self.url}/{url_path}", headers=self.headers, params={"limit": 0}).json()
        result_data = data["results"]
        while data["next"]:
            data = requests.get(data["next"], headers=self.headers, params={"limit": 0}).json()
            result_data.extend(data["results"])
        return result_data

    def load(self):
        """Load Region and Site data from the remote Nautobot instance."""
        for region_entry in self._get_api_data("api/dcim/regions/"):
            region = self.region(
                name=region_entry["name"],
                slug=region_entry["slug"],
                description=region_entry["description"],
                parent_name=region_entry["parent"]["name"] if region_entry["parent"] else None,
                pk=region_entry["id"],
            )
            self.add(region)
            self.job.log_debug(message=f"Loaded {region} from remote Nautobot instance")

        for site_entry in self._get_api_data("api/dcim/sites/"):
            site = self.site(
                name=site_entry["name"],
                slug=site_entry["slug"],
                status_slug=site_entry["status"]["value"],
                region_name=site_entry["region"]["name"] if site_entry["region"] else None,
                description=site_entry["description"],
                pk=site_entry["id"],
            )
            self.add(site)
            self.job.log_debug(message=f"Loaded {site} from remote Nautobot instance")

        for prefix_entry in self._get_api_data("api/ipam/prefixes/"):
            prefix = self.prefix(
                prefix=prefix_entry["prefix"],
                description=prefix_entry["description"],
                status_slug=prefix_entry["status"]["value"],
                tenant_slug=prefix_entry["tenant"]["slug"] if prefix_entry["tenant"] else "",
                pk=prefix_entry["id"],
            )
            self.add(prefix)
            self.job.log_debug(message=f"Loaded {prefix} from remote Nautobot instance")

    def post(self, path, data):
        """Send an appropriately constructed HTTP POST request."""
        response = requests.post(f"{self.url}{path}", headers=self.headers, json=data)
        response.raise_for_status()
        return response

    def patch(self, path, data):
        """Send an appropriately constructed HTTP PATCH request."""
        response = requests.patch(f"{self.url}{path}", headers=self.headers, json=data)
        response.raise_for_status()
        return response

    def delete(self, path):
        """Send an appropriately constructed HTTP DELETE request."""
        response = requests.delete(f"{self.url}{path}", headers=self.headers)
        response.raise_for_status()
        return response


class NautobotLocal(DiffSync):
    """DiffSync adapter class for loading data from the local Nautobot instance."""

    # Model classes used by this adapter class
    region = RegionLocalModel
    site = SiteLocalModel
    prefix = PrefixLocalModel

    # Top-level class labels, i.e. those classes that are handled directly rather than as children of other models
    top_level = ("region", "site", "prefix")

    def __init__(self, *args, job=None, **kwargs):
        """Instantiate this class, but do not load data immediately from the local system."""
        super().__init__(*args, **kwargs)
        self.job = job

    def load(self):
        """Load Region and Site data from the local Nautobot instance."""
        for region in Region.objects.all():
            region_model = self.region(
                name=region.name,
                slug=region.slug,
                description=region.description,
                parent_name=region.parent.name if region.parent else None,
                pk=region.pk,
            )
            self.add(region_model)
            self.job.log_debug(message=f"Loaded {region_model} from local Nautobot instance")

        for site in Site.objects.all():
            site_model = self.site(
                name=site.name,
                slug=site.slug,
                status_slug=site.status.slug,
                region_name=site.region.name if site.region else None,
                description=site.description,
                pk=site.pk,
            )
            self.add(site_model)
            self.job.log_debug(message=f"Loaded {site_model} from local Nautobot instance")

        for prefix in Prefix.objects.all():
            prefix_model = self.prefix(
                prefix=str(prefix.prefix),
                description=prefix.description,
                status_slug=prefix.status.slug,
                tenant_slug=prefix.tenant.slug if prefix.tenant else "",
                pk=prefix.pk,
            )
            self.add(prefix_model)
            self.job.log_debug(message=f"Loaded {prefix_model} from local Nautobot instance")


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
        self.diffsync_flags = self.diffsync_flags | DiffSyncFlags.SKIP_UNMATCHED_DST

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
        self.target_adapter = NautobotLocal(job=self)
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


class ExampleDataTarget(DataTarget, Job):
    """Sync Region and Site data from the local Nautobot instance to a remote Nautobot instance."""

    target_url = StringVar(description="Remote Nautobot instance to update", default="https://demo.nautobot.com")
    target_token = StringVar(description="REST API authentication token for remote Nautobot instance", default="a" * 40)

    def __init__(self):
        """Initialize ExampleDataTarget."""
        super().__init__()
        self.diffsync_flags = self.diffsync_flags | DiffSyncFlags.SKIP_UNMATCHED_DST

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
        self.source_adapter = NautobotLocal(job=self)
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
