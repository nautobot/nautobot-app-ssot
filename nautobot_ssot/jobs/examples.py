"""Sample data-source and data-target Jobs."""
# Skip colon check for multiple statements on one line.
# flake8: noqa: E701

from typing import Optional, Mapping
from uuid import UUID
from django.contrib.contenttypes.models import ContentType
from django.templatetags.static import static
from django.urls import reverse

from nautobot.circuits.models import CircuitTermination
from nautobot.dcim.models import Device, DeviceRedundancyGroup, Location, LocationType, PowerPanel, Rack, RackGroup
from nautobot.extras.jobs import StringVar
from nautobot.extras.models import Status
from nautobot.ipam.models import Namespace, Prefix, VLAN, VLANGroup
from nautobot.tenancy.models import Tenant
from nautobot.virtualization.models import Cluster

from diffsync import DiffSync, DiffSyncModel
from diffsync.enum import DiffSyncFlags
from diffsync.exceptions import ObjectNotFound

import requests

from nautobot_ssot.jobs.base import DataMapping, DataSource, DataTarget


# In a more complex Job, you would probably want to move the DiffSyncModel subclasses into a separate Python module(s).

name = "SSoT Examples"  # pylint: disable=invalid-name


class RegionModel(DiffSyncModel):
    """Shared data model representing a Region in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _modelname = "region"
    _identifiers = ("name",)
    _attributes = ("description", "parent_name")

    # Data type declarations for all identifiers and attributes
    name: str
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
    _attributes = ("status", "region_name", "description")

    # Data type declarations for all identifiers and attributes
    name: str
    status: str
    region_name: str
    description: str

    # Not in _attributes or _identifiers, hence not included in diff calculations
    pk: Optional[UUID]


class PrefixModel(DiffSyncModel):
    """Shared data model representing a Prefix in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _modelname = "prefix"
    _identifiers = ("prefix", "tenant")
    # To keep this example simple, we don't include **all** attributes of a Prefix here. But you could!
    _attributes = ("description", "status")

    # Data type declarations for all identifiers and attributes
    prefix: str
    tenant: str
    status: str
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
                "description": attrs["description"],
                "status": attrs["status"],
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
        if "description" in attrs:
            data["description"] = attrs["description"]
        if "status" in attrs:
            data["status"] = attrs["status"]
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
                "tenant": {"name": ids["tenant"]} if ids["tenant"] else None,
                "description": attrs["description"],
                "status": attrs["status"],
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
            data["status"] = attrs["status"]
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
        reg_type, _ = LocationType.objects.update_or_create(name="Region", nestable=True)
        region = Location(
            name=ids["name"],
            description=attrs["description"],
            location_type=LocationType.objects.get(name="Region"),
            status=Status.objects.get(name="Active"),
        )
        if attrs["parent_name"]:
            region.parent = Location.objects.get(name=attrs["parent_name"], location_type=reg_type)
        region.validated_save()
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update an existing Region record in local Nautobot.

        Args:
            attrs (dict): Updated values for any of this model's _attributes
        """
        region = Location.objects.get(name=self.name, location_type=LocationType.objects.get(name="Region"))

        if "description" in attrs:
            region.description = attrs["description"]

        if "parent_name" in attrs:
            region.parent = Location.objects.get(
                name=attrs["parent_name"], location_type=LocationType.objects.get(name="Region")
            )

        region.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete an existing Region record from local Nautobot."""
        region = Location.objects.get(name=self.name, location_type=LocationType.objects.get(name="Region"))
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
        diffsync.job.logger.info(f"Creating Site {ids['name']} with ids: {ids} attrs: {attrs}")
        reg_type = LocationType.objects.get(name="Region")
        try:
            site_type = LocationType.objects.get(name="Site")
            if not site_type.parent:
                site_type.parent = reg_type
                site_type.validated_save()
        except LocationType.DoesNotExist:
            site_type, _ = LocationType.objects.update_or_create(name="Site", nestable=False, parent=reg_type)
        for obj_type in [
            Rack,
            RackGroup,
            Device,
            DeviceRedundancyGroup,
            CircuitTermination,
            PowerPanel,
            VLAN,
            VLANGroup,
            Cluster,
        ]:
            if ContentType.objects.get_for_model(obj_type) not in site_type.content_types.all():
                site_type.content_types.add(ContentType.objects.get_for_model(obj_type))
        site = Location(name=ids["name"], description=attrs["description"], location_type=site_type, parent=None)
        site.status = Status.objects.get(name=attrs["status"])
        if attrs["region_name"]:
            site.parent = Location.objects.get(
                name=attrs["region_name"], location_type=LocationType.objects.get(name="Region")
            )
        site.validated_save()
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update an existing Site record in local Nautobot.

        Args:
            attrs (dict): Updated values for any of this model's _attributes
        """
        site = Location.objects.get(name=self.name, location_type=LocationType.objects.get(name="Site"))

        if "description" in attrs:
            site.description = attrs["description"]

        if "status" in attrs:
            site.status = Status.objects.get(name=attrs["status"])

        if "region_name" in attrs:
            site.parent = Location.objects.get(
                name=attrs["region_name"], location_type=LocationType.objects.get(name="Region")
            )

        site.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete an existing Site record from local Nautobot."""
        site = Location.objects.get(name=self.name, location_type=LocationType.objects.get_or_create(name="Site")[0])
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
        diffsync.job.logger.info(f"Creating Prefix {ids['prefix']} with ids: {ids} attrs: {attrs}")
        prefix = Prefix(prefix=ids["prefix"], description=attrs["description"])
        if ids["tenant"]:
            tenant_obj, _ = Tenant.objects.get_or_create(
                name=ids["tenant"],
                defaults={"name": ids["tenant"]},
            )
            prefix.tenant = tenant_obj
            namespace_obj, _ = Namespace.objects.get_or_create(
                name=ids["tenant"],
                defaults={"name": ids["tenant"]},
            )
            prefix.namespace = namespace_obj

        status_obj, _ = Status.objects.get_or_create(
            name=attrs["status"],
            defaults={"name": attrs["status"]},
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
        prefix = Prefix.objects.get(prefix=self.prefix, tenant__name=self.tenant)
        if "description" in attrs:
            prefix.description = attrs["description"]

        if "status" in attrs:
            status_obj, _ = Status.objects.get_or_create(
                defaults={"name": attrs["status"]},
            )
            status_obj.content_types.add(ContentType.objects.get_for_model(Prefix))
            prefix.status = status_obj
        prefix.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete an existing Prefix record from local Nautobot."""
        prefix = Prefix.objects.get(prefix=self.prefix, tenant__name=self.tenant)
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
    top_level = ["region", "site", "prefix"]

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
        for region_entry in self._get_api_data("api/dcim/regions/"):
            region = self.region(
                name=region_entry["name"],
                description=region_entry["description"],
                parent_name=region_entry["parent"]["name"] if region_entry["parent"] else None,
                pk=region_entry["id"],
            )
            self.add(region)
            self.job.logger.debug(f"Loaded {region} from remote Nautobot instance")

        for site_entry in self._get_api_data("api/dcim/sites/"):
            site = self.site(
                name=site_entry["name"],
                status=site_entry["status"]["label"] if site_entry.get("status") else "Active",
                region_name=site_entry["region"]["name"] if site_entry["region"] else "Global",
                description=site_entry["description"],
                pk=site_entry["id"],
            )
            self.add(site)
            self.job.logger.debug(f"Loaded {site} from remote Nautobot instance")
            if site.region_name == "Global":
                try:
                    self.get(self.region, "Global")
                except ObjectNotFound:
                    global_region = self.region(
                        name="Global",
                        description="Region created for Sites without assigned Region from SSoT import.",
                        parent_name=None,
                        pk=None,
                    )
                    self.add(global_region)

        for prefix_entry in self._get_api_data("api/ipam/prefixes/"):
            prefix = self.prefix(
                prefix=prefix_entry["prefix"],
                description=prefix_entry["description"],
                status=prefix_entry["status"]["label"] if prefix_entry.get("status") else "Active",
                tenant=prefix_entry["tenant"]["name"] if prefix_entry["tenant"] else "",
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


class NautobotLocal(DiffSync):
    """DiffSync adapter class for loading data from the local Nautobot instance."""

    # Model classes used by this adapter class
    region = RegionLocalModel
    site = SiteLocalModel
    prefix = PrefixLocalModel

    # Top-level class labels, i.e. those classes that are handled directly rather than as children of other models
    top_level = ["region", "site", "prefix"]

    def __init__(self, *args, job=None, **kwargs):
        """Instantiate this class, but do not load data immediately from the local system."""
        super().__init__(*args, **kwargs)
        self.job = job

    def load(self):
        """Load Region and Site data from the local Nautobot instance."""
        for location in Location.objects.all():
            if location.location_type.name == "Region":
                region_model = self.region(
                    name=location.name,
                    description=location.description,
                    parent_name=location.parent.name if location.parent else None,
                    pk=location.pk,
                )
                self.add(region_model)
                self.job.logger.debug(f"Loaded {region_model} from local Nautobot instance")

            if location.location_type.name == "Site":
                site_model = self.site(
                    name=location.name,
                    status=location.status.name,
                    region_name=location.parent.name if location.parent else "",
                    description=location.description,
                    pk=location.pk,
                )
                self.add(site_model)
                self.job.logger.debug(f"Loaded {site_model} from local Nautobot instance")

        for prefix in Prefix.objects.all():
            prefix_model = self.prefix(
                prefix=str(prefix.prefix),
                description=prefix.description,
                status=prefix.status.name,
                tenant=prefix.tenant.name if prefix.tenant else "",
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
        self.target_adapter = NautobotLocal(job=self)
        self.target_adapter.load()

    def lookup_object(self, model_name, unique_id):
        """Look up a Nautobot object based on the DiffSync model name and unique ID."""
        if model_name == "region":
            try:
                return Location.objects.get(name=unique_id, location_type=LocationType.objects.get(name="Region"))
            except Location.DoesNotExist:
                pass
        elif model_name == "site":
            try:
                return Location.objects.get(name=unique_id, location_type=LocationType.objects.get(name="Site"))
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
        self.source_adapter = NautobotLocal(job=self)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Method to instantiate and load the TARGET adapter into `self.target_adapter`."""
        self.target_adapter = NautobotRemote(url=self.target_url, token=self.target_token, job=self)
        self.target_adapter.load()

    def lookup_object(self, model_name, unique_id):
        """Look up a Nautobot object based on the DiffSync model name and unique ID."""
        if model_name == "region":
            try:
                return Location.objects.get(name=unique_id, location_type=LocationType.objects.get(name="Region"))
            except Location.DoesNotExist:
                pass
        elif model_name == "site":
            try:
                return Location.objects.get(name=unique_id, location_type=LocationType.objects.get(name="Site"))
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
