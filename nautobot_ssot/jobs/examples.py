"""Sample data-source and data-target Jobs."""

# pylint: disable=too-many-lines

import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Generator, List, Optional, TypedDict

import requests
from diffsync import Adapter
from diffsync.enum import DiffSyncFlags
from diffsync.exceptions import ObjectNotFound
from django.contrib.contenttypes.models import ContentType
from django.templatetags.static import static
from django.urls import reverse
from nautobot.dcim.models import Device, DeviceType, Interface, Location, LocationType, Manufacturer, Platform
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.jobs import ObjectVar, StringVar
from nautobot.extras.models import ExternalIntegration, Role, Status
from nautobot.extras.secrets.exceptions import SecretError
from nautobot.ipam.models import IPAddress, Namespace, Prefix
from nautobot.tenancy.models import Tenant

from nautobot_ssot.contrib import NautobotAdapter, NautobotModel
from nautobot_ssot.contrib.typeddicts import TagDict
from nautobot_ssot.exceptions import MissingSecretsGroupException
from nautobot_ssot.jobs.base import DataMapping, DataSource, DataTarget
from nautobot_ssot.tests.contrib_base_classes import ContentTypeDict

# In a more complex Job, you would probably want to move the DiffSyncModel subclasses into a separate Python module(s).

name = "SSoT Examples"  # pylint: disable=invalid-name


class LocationTypeModel(NautobotModel):
    """Shared data model representing a LocationType in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _model = LocationType
    _modelname = "locationtype"
    _identifiers = ("name",)
    # To keep this example simple, we don't include **all** attributes of a Location here. But you could!
    _attributes = ("content_types", "description", "nestable", "parent__name")

    # Data type declarations for all identifiers and attributes
    name: str
    description: str
    nestable: bool
    parent__name: Optional[str] = None
    content_types: List[ContentTypeDict] = []


class LocationDict(TypedDict):
    """This typed dict is for M2M Locations."""

    name: str
    location_type__name: str


class LocationModel(NautobotModel):
    """Shared data model representing a Location in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _model = Location
    _modelname = "location"
    _identifiers = ("name",)
    # To keep this example simple, we don't include **all** attributes of a Location here. But you could!
    _attributes = (
        "location_type__name",
        "status__name",
        "parent__name",
        "parent__location_type__name",
        "tenant__name",
        "description",
        "tags",
    )

    # Data type declarations for all identifiers and attributes
    name: str
    location_type__name: str
    status__name: str
    parent__name: Optional[str] = None
    parent__location_type__name: Optional[str] = None
    tenant__name: Optional[str] = None
    description: str
    tags: List[TagDict] = []


class RoleModel(NautobotModel):
    """Shared data model representing a Role in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _model = Role
    _modelname = "role"
    _identifiers = ("name",)
    _attributes = ("content_types",)

    name: str
    content_types: List[ContentTypeDict] = []


class StatusModel(NautobotModel):
    """Shared data model representing a Status in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _model = Status
    _modelname = "status"
    _identifiers = ("name",)
    _attributes = ("content_types", "color")

    name: str
    color: str
    content_types: List[ContentTypeDict] = []


class NamespaceModel(NautobotModel):
    """Shared data model representing a Namespace in either of the local or remote Nautobot instance."""

    # Metadata about this model
    _model = Namespace
    _modelname = "namespace"
    _identifiers = ("name",)
    _attributes = ("description", "tags")

    name: str
    description: Optional[str] = ""
    tags: List[TagDict] = []


class PrefixModel(NautobotModel):
    """Shared data model representing a Prefix in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _model = Prefix
    _modelname = "prefix"
    _identifiers = ("network", "prefix_length", "namespace__name")
    # To keep this example simple, we don't include **all** attributes of a Prefix here. But you could!
    _attributes = ("description", "tenant__name", "status__name", "locations", "tags")

    # Data type declarations for all identifiers and attributes
    network: str
    namespace__name: str
    prefix_length: int
    tenant__name: Optional[str] = None
    status__name: str
    description: str
    tags: List[TagDict] = []

    locations: List[LocationDict] = []


class IPAddressModel(NautobotModel):
    """Shared data model representing an IPAddress in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _model = IPAddress
    _modelname = "ipaddress"
    _identifiers = ("host", "mask_length", "parent__network", "parent__prefix_length", "parent__namespace__name")
    _attributes = ("status__name", "ip_version", "tenant__name", "tags")

    # Data type declarations for all identifiers and attributes
    host: str
    mask_length: int
    parent__network: str
    parent__prefix_length: int
    parent__namespace__name: str
    status__name: str
    ip_version: int
    tenant__name: Optional[str]
    tags: List[TagDict] = []


class TenantModel(NautobotModel):
    """Shared data model representing a Tenant in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _model = Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("tags",)
    _children = {}

    name: str
    prefixes: List[PrefixModel] = []
    tags: List[TagDict] = []


class DeviceTypeModel(NautobotModel):
    """Shared data model representing a DeviceType in either of the local or remote Nautobot instances."""

    _model = DeviceType
    _modelname = "device_type"
    _identifiers = ("model", "manufacturer__name")
    _attributes = ("part_number", "u_height", "is_full_depth", "tags")

    model: str
    manufacturer__name: str
    part_number: str
    u_height: int
    is_full_depth: bool
    tags: List[TagDict] = []


class ManufacturerModel(NautobotModel):
    """Shared data model representing a Manufacturer in either of the local or remote Nautobot instances."""

    _model = Manufacturer
    _modelname = "manufacturer"
    _identifiers = ("name",)
    _attributes = ("description",)
    _children = {"device_type": "device_types"}

    name: str
    description: str
    device_types: List[DeviceTypeModel] = []


class PlatformModel(NautobotModel):
    """Shared data model representing a Platform in either of the local or remote Nautobot instances."""

    _model = Platform
    _modelname = "platform"
    _identifiers = ("name", "manufacturer__name")
    _attributes = ("description", "network_driver", "napalm_driver")

    name: str
    manufacturer__name: Optional[str] = None
    description: str
    network_driver: str
    napalm_driver: str


class DeviceModel(NautobotModel):
    """Shared data model representing a Device in either of the local or remote Nautobot instances."""

    # Metadata about this model
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
        "tenant__name",
        "asset_tag",
        "tags",
    )
    _children = {"interface": "interfaces"}

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
    tenant__name: Optional[str]
    asset_tag: Optional[str]
    interfaces: List["InterfaceModel"] = []
    tags: List[TagDict] = []


class InterfaceModel(NautobotModel):
    """Shared data model representing an Interface in either of the local or remote Nautobot instances."""

    # Metadata about this model
    _model = Interface
    _modelname = "interface"
    _identifiers = ("name", "device__name")
    _attributes = (
        "device__location__name",
        "device__location__parent__name",
        "description",
        "enabled",
        "mac_address",
        "mgmt_only",
        "mtu",
        "type",
        "status__name",
        "tags",
    )
    _children = {}

    # Data type declarations for all identifiers and attributes
    device__name: str
    device__location__name: str
    device__location__parent__name: str
    description: Optional[str]
    enabled: bool
    mac_address: Optional[str]
    mgmt_only: bool
    mtu: Optional[int]
    name: str
    type: str
    status__name: str
    tags: List[TagDict] = []


class LocationRemoteModel(LocationModel):
    """Implementation of Location create/update/delete methods for updating remote Nautobot data."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create a new Location in remote Nautobot.

        Args:
            adapter (NautobotRemote): DiffSync adapter owning this Site
            ids (dict): Initial values for this model's _identifiers
            attrs (dict): Initial values for this model's _attributes
        """
        adapter.post(
            "/api/dcim/locations/",
            {
                "name": ids["name"],
                "description": attrs["description"],
                "status": attrs["status__name"],
                "location_type": attrs["location_type__name"],
                "parent": {"name": attrs["parent__name"]} if attrs.get("parent__name") else None,
                "tags": attrs["tags"] if attrs.get("tags") else [],
            },
        )
        return super().create(adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update an existing Site record in remote Nautobot.

        Args:
            attrs (dict): Updated values for this record's _attributes
        """
        data = {}
        if "description" in attrs:
            data["description"] = attrs["description"]
        if "status__name" in attrs:
            data["status"] = attrs["status__name"]
        if "parent__name" in attrs:
            if attrs["parent__name"]:
                data["parent"] = {"name": attrs["parent__name"]}
            else:
                data["parent"] = None
        if "tags" in attrs:
            data["tags"] = attrs["tags"] if attrs.get("tags") else []
        self.adapter.patch(f"/api/dcim/locations/{self.pk}/", data)
        return super().update(attrs)

    def delete(self):
        """Delete an existing Site record from remote Nautobot."""
        self.adapter.delete(f"/api/dcim/locations/{self.pk}/")
        return super().delete()


class TenantRemoteModel(TenantModel):
    """Implementation of Tenant create/update/delete methods for updating remote Nautobot data."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create a new Tenant in remote Nautobot."""
        adapter.post(
            "/api/tenancy/tenants/",
            {
                "name": ids["name"],
                "tags": attrs["tags"] if attrs.get("tags") else [],
            },
        )
        return super().create(adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Updating tenants is not supported because we don't have any attributes."""
        data = {}
        if "tags" in attrs:
            data["tags"] = attrs["tags"] if attrs.get("tags") else []
        self.adapter.patch(f"/api/tenancy/tenants/{self.pk}/", data)
        return super().update(attrs)

    def delete(self):
        """Delete a Tenant in remote Nautobot."""
        self.adapter.delete(f"/api/tenancy/tenants/{self.pk}/")
        return super().delete()


class PrefixRemoteModel(PrefixModel):
    """Implementation of Prefix create/update/delete methods for updating remote Nautobot data."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create a new Prefix in remote Nautobot.

        Args:
            adapter (NautobotRemote): DiffSync adapter owning this Prefix
            ids (dict): Initial values for this model's _identifiers
            attrs (dict): Initial values for this model's _attributes
        """
        adapter.post(
            "/api/ipam/prefixes/",
            {
                "network": ids["network"],
                "prefix_length": ids["prefix_length"],
                "tenant": {"name": attrs["tenant__name"]} if attrs.get("tenant__name") else None,
                "namespace": {"name": ids["namespace__name"]} if ids.get("namespace__name") else None,
                "description": attrs["description"],
                "status": attrs["status__name"],
                "tags": attrs["tags"] if attrs.get("tags") else [],
            },
        )
        return super().create(adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update an existing Prefix record in remote Nautobot.

        Args:
            attrs (dict): Updated values for this record's _attributes
        """
        data = {}
        if "description" in attrs:
            data["description"] = attrs["description"]
        if "status__name" in attrs:
            data["status"] = attrs["status__name"]
        if "tags" in attrs:
            data["tags"] = attrs["tags"] if attrs.get("tags") else []
        self.adapter.patch(f"/api/ipam/prefixes/{self.pk}/", data)
        return super().update(attrs)

    def delete(self):
        """Delete an existing Prefix record from remote Nautobot."""
        self.adapter.delete(f"/api/ipam/prefixes/{self.pk}/")
        return super().delete()


# In a more complex Job, you would probably want to move each DiffSync subclass into a separate Python module.


class NautobotRemote(Adapter):
    """DiffSync adapter class for loading data from a remote Nautobot instance using Python requests.

    In a more realistic example, you'd probably use PyNautobot here instead of raw requests,
    but we didn't want to add PyNautobot as a dependency of this app just to make an example more realistic.
    """

    # Model classes used by this adapter class
    locationtype = LocationTypeModel
    location = LocationRemoteModel
    tenant = TenantRemoteModel
    namespace = NamespaceModel
    prefix = PrefixRemoteModel
    ipaddress = IPAddressModel
    manufacturer = ManufacturerModel
    device_type = DeviceTypeModel
    platform = PlatformModel
    role = RoleModel
    status = StatusModel
    device = DeviceModel
    interface = InterfaceModel

    # Top-level class labels, i.e. those classes that are handled directly rather than as children of other models
    top_level = [
        "tenant",
        "status",
        "locationtype",
        "location",
        "manufacturer",
        "platform",
        "role",
        "device",
        "namespace",
        "prefix",
        "ipaddress",
    ]

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
        self._content_type_cache = {}
        self._thread_local = threading.local()

    def __deepcopy__(self, memo):
        """Custom deepcopy to handle threading.local which cannot be copied.

        DiffSync may deepcopy the job (and thus adapters) during adapter creation.
        threading.local objects are not deepcopy-able, so we produce a copy with
        a fresh thread-local storage for the duplicate instance.
        """
        if id(self) in memo:
            return memo[id(self)]
        result = copy.copy(self)
        memo[id(self)] = result
        result._thread_local = threading.local()
        return result

    def _get_session(self) -> requests.Session:
        """Get a thread-local requests.Session for connection reuse and persistence.

        Each thread gets its own session to ensure thread-safety while benefiting
        from TCP connection reuse (keep-alive) within that thread's API calls.
        """
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update(self.headers)
            self._thread_local.session = session
        return self._thread_local.session

    def _topological_sort_entries(self, entries, name_key="name", parent_key="parent"):
        """Order entries so parents appear before their children.

        Args:
            entries: List of dict-like entries with name and optional parent.
            name_key: Key for entry name.
            parent_key: Key for parent (expected to be dict with 'name' key).

        Returns:
            List of entries in topological order (parents before children).
        """
        entries_by_name = {entry[name_key]: entry for entry in entries}
        children_by_parent = {}
        root_entries = []

        for entry in entries:
            parent_obj = entry.get(parent_key)
            parent_name = parent_obj.get("name") if parent_obj else None
            if parent_name:
                if parent_name not in children_by_parent:
                    children_by_parent[parent_name] = []
                children_by_parent[parent_name].append(entry)
            else:
                root_entries.append(entry)

        processed = set()
        ordered_entries = []

        def process_entry(entry):
            entry_name = entry[name_key]
            if entry_name in processed:
                return
            parent_obj = entry.get(parent_key)
            parent_name = parent_obj.get("name") if parent_obj else None
            if parent_name and parent_name in entries_by_name:
                parent_entry = entries_by_name[parent_name]
                if parent_entry[name_key] not in processed:
                    process_entry(parent_entry)
            ordered_entries.append(entry)
            processed.add(entry_name)
            if entry_name in children_by_parent:
                for child_entry in children_by_parent[entry_name]:
                    process_entry(child_entry)

        for root_entry in root_entries:
            process_entry(root_entry)
        for entry in entries:
            if entry[name_key] not in processed:
                process_entry(entry)
        return ordered_entries

    def _get_api_data(self, url_path: str, **query_params) -> Generator:
        """Returns data from a url_path using pagination.

        Uses the thread-local session for connection reuse and keep-alive.
        """
        session = self._get_session()
        response = session.get(
            f"{self.url}/{url_path}",
            params={"limit": 200, "exclude_m2m": "false", **query_params},
            timeout=600,
        )
        response.raise_for_status()
        try:
            data = response.json()
        except json.JSONDecodeError as err:
            self.job.logger.error("Failed to decode JSON response from %s: %s", url_path, err)
            raise
        results = data.get("results", [])
        yield from results
        while data.get("next"):
            response = session.get(
                data["next"],
                timeout=600,
            )
            response.raise_for_status()
            try:
                data = response.json()
            except json.JSONDecodeError as err:
                self.job.logger.error("Failed to decode JSON response from pagination: %s", err)
                raise
            results = data.get("results", [])
            yield from results

    def load(self):
        """Load data from the remote Nautobot instance using multithreading.

        Independent API endpoints are fetched in parallel using ThreadPoolExecutor,
        while respecting dependencies between data types (e.g., locations need
        location_types and statuses; prefixes need locations, etc.).
        """
        # Phase 1: Load independent base data types in parallel
        phase1_loaders = [
            self.load_statuses,
            self.load_location_types,
            self.load_roles,
            self.load_tenants,
            self.load_namespaces,
            self.load_manufacturers,
            self.load_platforms,
        ]
        self._run_loaders_parallel(phase1_loaders)

        # Phase 2: Load locations, prefixes, and device_types in parallel (depend on phase 1)
        phase2_loaders = [self.load_locations, self.load_prefixes, self.load_device_types]
        self._run_loaders_parallel(phase2_loaders)

        # Phase 3: Load ipaddresses and devices in parallel (depend on phase 2)
        phase3_loaders = [self.load_ipaddresses, self.load_devices]
        self._run_loaders_parallel(phase3_loaders)
        # self.load_interfaces()

    def _run_loaders_parallel(self, loaders):
        """Execute multiple load methods in parallel using ThreadPoolExecutor.

        Args:
            loaders: List of callables (load methods) to execute in parallel.
        """
        with ThreadPoolExecutor(max_workers=len(loaders)) as executor:
            futures = {executor.submit(loader): loader for loader in loaders}
            for future in as_completed(futures):
                loader = futures[future]
                try:
                    future.result()
                except Exception as err:
                    self.job.logger.error(
                        "Error loading data from %s: %s",
                        loader.__name__,
                        err,
                        exc_info=True,
                    )
                    raise

    def load_location_types(self):
        """Load LocationType data from the remote Nautobot instance.

        Ensures parent LocationTypes are loaded before their children by using
        topological sorting based on parent-child relationships.
        """
        location_type_entries = list(self._get_api_data("api/dcim/location-types/", depth=1))
        ordered_entries = self._topological_sort_entries(location_type_entries, name_key="name", parent_key="parent")
        for lt_entry in ordered_entries:
            content_types = self.get_content_types(lt_entry)
            location_type = self.locationtype(
                name=lt_entry["name"],
                description=lt_entry["description"],
                nestable=lt_entry["nestable"],
                parent__name=lt_entry["parent"]["name"] if lt_entry.get("parent") else None,
                content_types=content_types,
                pk=lt_entry["id"],
            )
            self.add(location_type)
            self.job.logger.debug(f"Loaded {location_type} LocationType from remote Nautobot instance")

    def load_locations(self):
        """Load Locations data from the remote Nautobot instance.

        Ensures parent Locations are loaded before their children by using
        topological sorting based on parent-child relationships.
        """
        location_entries = list(self._get_api_data("api/dcim/locations/", depth=3))
        ordered_entries = self._topological_sort_entries(location_entries, name_key="name", parent_key="parent")
        for loc_entry in ordered_entries:
            location_args = {
                "name": loc_entry["name"],
                "status__name": loc_entry["status"]["name"] if loc_entry["status"].get("name") else "Active",
                "location_type__name": loc_entry["location_type"]["name"],
                "tenant__name": loc_entry["tenant"]["name"] if loc_entry.get("tenant") else None,
                "description": loc_entry["description"],
                "tags": loc_entry["tags"] if loc_entry.get("tags") else [],
                "pk": loc_entry["id"],
            }
            if loc_entry["parent"]:
                location_args["parent__name"] = loc_entry["parent"]["name"]
                location_args["parent__location_type__name"] = loc_entry["parent"]["location_type"]["name"]
            new_location = self.location(**location_args)
            self.add(new_location)
            self.job.logger.debug(f"Loaded {new_location} Location from remote Nautobot instance")

    def load_roles(self):
        """Load Roles data from the remote Nautobot instance."""
        for role_entry in self._get_api_data("api/extras/roles/", depth=1):
            content_types = self.get_content_types(role_entry)
            role = self.role(
                name=role_entry["name"],
                content_types=content_types,
                pk=role_entry["id"],
            )
            self.add(role)

    def load_statuses(self):
        """Load Statuses data from the remote Nautobot instance."""
        for status_entry in self._get_api_data("api/extras/statuses/", depth=1):
            content_types = self.get_content_types(status_entry)
            status = self.status(
                name=status_entry["name"],
                color=status_entry["color"],
                content_types=content_types,
                pk=status_entry["id"],
            )
            self.add(status)

    def load_tenants(self):
        """Load Tenants data from the remote Nautobot instance."""
        for tenant_entry in self._get_api_data("api/tenancy/tenants/", depth=1):
            tenant = self.tenant(
                name=tenant_entry["name"],
                tags=tenant_entry["tags"] if tenant_entry.get("tags") else [],
                pk=tenant_entry["id"],
            )
            self.add(tenant)

    def load_namespaces(self):
        """Load Namespaces data from remote Nautobot instance."""
        for namespace_entry in self._get_api_data("api/ipam/namespaces/", depth=1):
            namespace = self.namespace(
                name=namespace_entry["name"],
                description=namespace_entry["description"],
                tags=namespace_entry["tags"] if namespace_entry.get("tags") else [],
                pk=namespace_entry["id"],
            )
            self.add(namespace)

    def load_prefixes(self):
        """Load Prefixes data from the remote Nautobot instance."""
        for prefix_entry in self._get_api_data("api/ipam/prefixes/", depth=2):
            prefix = self.prefix(
                network=prefix_entry["network"],
                prefix_length=prefix_entry["prefix_length"],
                namespace__name=prefix_entry["namespace"]["name"],
                description=prefix_entry["description"],
                locations=[
                    {"name": x["name"], "location_type__name": x["location_type"]["name"]}
                    for x in prefix_entry["locations"]
                ],
                status__name=prefix_entry["status"]["name"] if prefix_entry["status"].get("name") else "Active",
                tenant__name=prefix_entry["tenant"]["name"] if prefix_entry["tenant"] else None,
                tags=prefix_entry["tags"] if prefix_entry.get("tags") else [],
                pk=prefix_entry["id"],
            )
            self.add(prefix)
            self.job.logger.debug(f"Loaded {prefix} from remote Nautobot instance")

    def load_ipaddresses(self):
        """Load IPAddresses data from the remote Nautobot instance."""
        for ipaddr_entry in self._get_api_data("api/ipam/ip-addresses/", depth=2):
            ipaddr = self.ipaddress(
                host=ipaddr_entry["host"],
                mask_length=ipaddr_entry["mask_length"],
                parent__network=ipaddr_entry["parent"]["network"],
                parent__prefix_length=ipaddr_entry["parent"]["prefix_length"],
                parent__namespace__name=ipaddr_entry["parent"]["namespace"]["name"],
                status__name=ipaddr_entry["status"]["name"],
                ip_version=ipaddr_entry["ip_version"],
                tenant__name=ipaddr_entry["tenant"]["name"] if ipaddr_entry.get("tenant") else None,
                tags=ipaddr_entry["tags"] if ipaddr_entry.get("tags") else [],
                pk=ipaddr_entry["id"],
            )
            self.add(ipaddr)
            self.job.logger.debug(f"Loaded {ipaddr} from remote Nautobot instance")

    def load_manufacturers(self):
        """Load Manufacturers data from the remote Nautobot instance."""
        for manufacturer in self._get_api_data("api/dcim/manufacturers/", depth=1):
            manufacturer_model = self.manufacturer(
                name=manufacturer["name"],
                description=manufacturer["description"],
                pk=manufacturer["id"],
            )
            self.add(manufacturer_model)
            self.job.logger.debug(f"Loaded {manufacturer_model} from remote Nautobot instance")

    def load_device_types(self):
        """Load DeviceTypes data from the remote Nautobot instance."""
        for device_type in self._get_api_data("api/dcim/device-types/", depth=1):
            try:
                manufacturer = self.get(self.manufacturer, device_type["manufacturer"]["name"])
                devicetype = self.device_type(
                    model=device_type["model"],
                    manufacturer__name=device_type["manufacturer"]["name"] if device_type.get("manufacturer") else "",
                    part_number=device_type["part_number"],
                    u_height=device_type["u_height"],
                    is_full_depth=device_type["is_full_depth"],
                    tags=device_type["tags"] if device_type.get("tags") else [],
                    pk=device_type["id"],
                )
                self.add(devicetype)
                self.job.logger.debug(f"Loaded {devicetype} from remote Nautobot instance")
                manufacturer.add_child(devicetype)
            except ObjectNotFound:
                self.job.logger.debug(f"Unable to find Manufacturer {device_type['manufacturer']['name']}")

    def load_platforms(self):
        """Load Platforms data from the remote Nautobot instance."""
        for platform in self._get_api_data("api/dcim/platforms/", depth=1):
            platform_model = self.platform(
                name=platform["name"],
                manufacturer__name=platform["manufacturer"]["name"] if platform.get("manufacturer") else "",
                description=platform["description"],
                network_driver=platform["network_driver"],
                napalm_driver=platform["napalm_driver"],
                pk=platform["id"],
            )
            self.add(platform_model)
            self.job.logger.debug(f"Loaded {platform_model} from remote Nautobot instance")

    def load_devices(self):
        """Load Devices data from the remote Nautobot instance."""
        for device in self._get_api_data("api/dcim/devices/", depth=3):
            device_model = self.device(
                name=device["name"],
                location__name=device["location"]["name"],
                location__parent__name=(
                    device["location"]["parent"]["name"] if device["location"].get("parent") else None
                ),
                location__parent__location_type__name=(
                    device["location"]["parent"]["location_type"]["name"] if device["location"].get("parent") else None
                ),
                location__location_type__name=device["location"]["location_type"]["name"],
                device_type__manufacturer__name=device["device_type"]["manufacturer"]["name"],
                device_type__model=device["device_type"]["model"],
                platform__name=device["platform"]["name"] if device.get("platform") else None,
                role__name=device["role"]["name"],
                asset_tag=device["asset_tag"] if device.get("asset_tag") else None,
                serial=device["serial"] if device.get("serial") else "",
                status__name=device["status"]["name"],
                tenant__name=device["tenant"]["name"] if device.get("tenant") else None,
                tags=device["tags"] if device.get("tags") else [],
                pk=device["id"],
            )
            self.add(device_model)
            self.job.logger.debug(f"Loaded {device_model} from remote Nautobot instance")

    def load_interfaces(self):
        """Load Interfaces data from the remote Nautobot instance."""
        self.job.logger.info("Pulling data from remote Nautobot instance for Interfaces.")
        for device in self.get_all(self.device):
            for interface in self._get_api_data("api/dcim/interfaces/", depth=3, device=device.pk):
                if not interface.get("device"):
                    self.job.logger.warning(
                        f"Skipping Interface {interface['name']} because it has no Device associated with it."
                    )
                    continue
                new_interface = self.interface(
                    name=interface["name"],
                    device__name=interface["device"]["name"],
                    device__location__name=interface["device"]["location"]["name"],
                    device__location__parent__name=interface["device"]["location"]["parent"]["name"],
                    description=interface["description"],
                    enabled=interface["enabled"],
                    mac_address=interface["mac_address"],
                    mgmt_only=interface["mgmt_only"],
                    mtu=interface["mtu"],
                    type=interface["type"]["value"],
                    status__name=interface["status"]["name"],
                    tags=interface["tags"] if interface.get("tags") else [],
                    pk=interface["id"],
                )
                self.add(new_interface)
                self.job.logger.debug(
                    f"Loaded {new_interface} for {interface['device']['name']} from remote Nautobot instance"
                )
                device.add_child(new_interface)

    def get_content_types(self, entry):
        """Create list of dicts of ContentTypes.

        Uses a cache to avoid repeated database lookups for the same ContentType.

        Args:
            entry (dict): Record from Nautobot.

        Returns:
            List[dict]: List of dictionaries of ContentTypes split into app_label and model.
        """
        content_types = []
        for contenttype in entry.get("content_types", []):
            cache_key = contenttype
            if cache_key not in self._content_type_cache:
                try:
                    app_label, model = tuple(contenttype.split("."))
                    ContentType.objects.get(app_label=app_label, model=model)
                    self._content_type_cache[cache_key] = {"app_label": app_label, "model": model}
                except (ContentType.DoesNotExist, ValueError):
                    self._content_type_cache[cache_key] = None
            if self._content_type_cache[cache_key] is not None:
                content_types.append(self._content_type_cache[cache_key])
        return content_types

    def post(self, path, data):
        """Send an appropriately constructed HTTP POST request."""
        session = self._get_session()
        response = session.post(f"{self.url}{path}", json=data, timeout=600)
        response.raise_for_status()
        return response

    def patch(self, path, data):
        """Send an appropriately constructed HTTP PATCH request."""
        session = self._get_session()
        response = session.patch(f"{self.url}{path}", json=data, timeout=600)
        response.raise_for_status()
        return response

    def delete(self, path):
        """Send an appropriately constructed HTTP DELETE request."""
        session = self._get_session()
        response = session.delete(f"{self.url}{path}", timeout=600)
        response.raise_for_status()
        return response


class NautobotLocal(NautobotAdapter):
    """DiffSync adapter class for loading data from the local Nautobot instance."""

    # Model classes used by this adapter class
    locationtype = LocationTypeModel
    location = LocationModel
    tenant = TenantModel
    namespace = NamespaceModel
    prefix = PrefixModel
    ipaddress = IPAddressModel
    manufacturer = ManufacturerModel
    device_type = DeviceTypeModel
    platform = PlatformModel
    role = RoleModel
    status = StatusModel
    device = DeviceModel
    interface = InterfaceModel

    # Top-level class labels, i.e. those classes that are handled directly rather than as children of other models
    top_level = [
        "tenant",
        "status",
        "locationtype",
        "location",
        "manufacturer",
        "platform",
        "role",
        "device",
        "namespace",
        "prefix",
        "ipaddress",
    ]


# The actual Data Source and Data Target Jobs are relatively simple to implement
# once you have the above DiffSync scaffolding in place.


class ExampleDataSource(DataSource):  # pylint: disable=too-many-instance-attributes
    """Sync Region and Site data from a remote Nautobot instance into the local Nautobot instance."""

    source = ObjectVar(
        model=ExternalIntegration,
        queryset=ExternalIntegration.objects.all(),
        display_field="display",
        label="Nautobot Demo Instance",
        required=False,
    )
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
            DataMapping("LocationType (remote)", None, "LocationType (local)", reverse("dcim:locationtype_list")),
            DataMapping("Location (remote)", None, "Location (local)", reverse("dcim:location_list")),
            DataMapping("Role (remote)", None, "Role (local)", reverse("extras:role_list")),
            DataMapping("Namespace (remote)", None, "Namespace (local)", reverse("ipam:namespace_list")),
            DataMapping("Prefix (remote)", None, "Prefix (local)", reverse("ipam:prefix_list")),
            DataMapping("IPAddress (remote)", None, "IPAddress (local)", reverse("ipam:ipaddress_list")),
            DataMapping("Tenant (remote)", None, "Tenant (local)", reverse("tenancy:tenant_list")),
            DataMapping("DeviceType (remote)", None, "DeviceType (local)", reverse("dcim:devicetype_list")),
            DataMapping("Manufacturer (remote)", None, "Manufacturer (local)", reverse("dcim:manufacturer_list")),
            DataMapping("Platform (remote)", None, "Platform (local)", reverse("dcim:platform_list")),
            DataMapping("Device (remote)", None, "Device (local)", reverse("dcim:device_list")),
            DataMapping("Interface (remote)", None, "Interface (local)", reverse("dcim:interface_list")),
        )

    def run(
        self,
        *args,
        **kwargs,
    ):
        """Run sync."""
        self.dryrun = kwargs.get("dryrun", True)
        self.memory_profiling = kwargs.get("memory_profiling", False)
        self.source = kwargs.get("source")
        self.source_url = kwargs.get("source_url")
        self.source_token = kwargs.get("source_token")
        try:
            if self.source:
                self.logger.info(f"Using external integration '{self.source}'")
                self.source_url = self.source.remote_url
                if not self.source.secrets_group:
                    self.logger.error(
                        "%s is missing a SecretsGroup. You must specify a SecretsGroup to synchronize with this Nautobot instance.",
                        self.source,
                    )
                    raise MissingSecretsGroupException(message="Missing SecretsGroup on specified ExternalIntegration.")
                secrets_group = self.source.secrets_group
                self.source_token = secrets_group.get_secret_value(
                    access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
                    secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
                )
            else:
                self.source_url = self.source_url
                self.source_token = self.source_token
        except SecretError as error:
            self.logger.error("Error setting up job: %s", error)
            raise

        super().run(*args, **kwargs)

    def load_source_adapter(self):
        """Method to instantiate and load the SOURCE adapter into `self.source_adapter`."""
        self.logger.info("Loading source adapter: NautobotRemote")
        self.source_adapter = NautobotRemote(url=self.source_url, token=self.source_token, job=self)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Method to instantiate and load the TARGET adapter into `self.target_adapter`."""
        self.logger.info("Loading target adapter: NautobotLocal")
        self.target_adapter = NautobotLocal(job=self, sync=self.sync)
        self.target_adapter.load()

    def lookup_object(self, model_name, unique_id):  # pylint: disable=too-many-return-statements, too-many-branches, too-many-locals
        """Look up a Nautobot object based on the DiffSync model name and unique ID."""
        if model_name == "prefix":
            try:
                return Prefix.objects.get(
                    prefix=unique_id.split("__")[0], tenant__name=unique_id.split("__")[1] or None
                )
            except Prefix.DoesNotExist:
                pass
        elif model_name == "tenant":
            try:
                return Tenant.objects.get(name=unique_id)
            except Tenant.DoesNotExist:
                pass
        return None


class ExampleDataTarget(DataTarget):
    """Sync Region and Site data from the local Nautobot instance to a remote Nautobot instance."""

    target = ObjectVar(
        model=ExternalIntegration,
        queryset=ExternalIntegration.objects.all(),
        display_field="display",
        label="Nautobot Target Instance",
        required=False,
    )
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
            DataMapping("LocationType (local)", reverse("dcim:locationtype_list"), "LocationType (remote)", None),
            DataMapping("Location (local)", reverse("dcim:location_list"), "Location (remote)", None),
            DataMapping("Role (local)", reverse("extras:role_list"), "Role (remote)", None),
            DataMapping("Namespace (local)", reverse("ipam:namespace_list"), "Namespace (remote)", None),
            DataMapping("Prefix (local)", reverse("ipam:prefix_list"), "Prefix (remote)", None),
            DataMapping("IPAddress (local)", reverse("ipam:ipaddress_list"), "IPAddress (remote)", None),
            DataMapping("Tenant (local)", reverse("tenancy:tenant_list"), "Tenant (remote)", None),
            DataMapping("DeviceType (local)", reverse("dcim:devicetype_list"), "DeviceType (remote)", None),
            DataMapping("Manufacturer (local)", reverse("dcim:manufacturer_list"), "Manufacturer (remote)", None),
            DataMapping("Platform (local)", reverse("dcim:platform_list"), "Platform (remote)", None),
            DataMapping("Device (local)", reverse("dcim:device_list"), "Device (remote)", None),
            DataMapping("Interface (local)", reverse("dcim:interface_list"), "Interface (remote)", None),
        )

    def run(  # pylint: disable=too-many-arguments, arguments-differ
        self,
        *args,
        **kwargs,
    ):
        """Run sync."""
        self.target = kwargs.get("target")
        self.target_url = kwargs.get("target_url")
        self.target_token = kwargs.get("target_token")
        try:
            if self.target:
                self.logger.info(f"Using external integration '{self.target}'")
                self.target_url = self.target.remote_url
                if not self.target.secrets_group:
                    self.logger.error(
                        "%s is missing a SecretsGroup. You must specify a SecretsGroup to synchronize with this Nautobot instance.",
                        self.target,
                    )
                    raise MissingSecretsGroupException("Missing SecretsGroup on specified ExternalIntegration.")
                secrets_group = self.target.secrets_group
                self.target_token = secrets_group.get_secret_value(
                    access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
                    secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
                )
            else:
                self.target_url = self.target_url
                self.target_token = self.target_token
        except SecretError as error:
            self.logger.error("Error setting up job: %s", error)
            raise

        super().run(*args, **kwargs)

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
        if model_name == "prefix":
            try:
                return Prefix.objects.get(
                    prefix=unique_id.split("__")[0], tenant__name=unique_id.split("__")[1] or None
                )
            except Prefix.DoesNotExist:
                pass
        elif model_name == "tenant":
            try:
                return Tenant.objects.get(name=unique_id)
            except Tenant.DoesNotExist:
                pass
        return None
