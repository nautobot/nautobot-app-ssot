"""DiffSyncModel subclasses for Nautobot-to-ServiceNow data sync."""

from typing import List, Optional, Union
import uuid

from diffsync import DiffSyncModel
from diffsync.enum import DiffSyncStatus

# import pysnow
from nautobot_ssot.integrations.servicenow.third_party import pysnow


class ServiceNowCRUDMixin:
    """Mixin class for all ServiceNow models, to support CRUD operations based on mappings.yaml."""

    _sys_id_cache = {}
    """Dict of table -> column_name -> value -> sys_id."""

    def map_data_to_sn_record(self, data, mapping_entry, existing_record=None, clear_cache=False):
        """Map create/update data from DiffSync to a corresponding ServiceNow data record."""
        record = existing_record or {}
        for mapping in mapping_entry.get("mappings", []):
            if mapping["field"] not in data:
                continue
            value = data[mapping["field"]]
            if "column" in mapping:
                record[mapping["column"]] = value
            elif "reference" in mapping:
                tablename = mapping["reference"]["table"]
                sys_id = None
                if "column" not in mapping["reference"]:
                    raise NotImplementedError
                column_name = mapping["reference"]["column"]
                if value is not None:
                    # if clear_cache is set to True then clear the cache for the object
                    if clear_cache:
                        self._sys_id_cache.setdefault(tablename, {}).setdefault(column_name, {})[value] = {}
                    # Look in the cache first
                    sys_id = self._sys_id_cache.get(tablename, {}).get(column_name, {}).get(value, None)
                    if not sys_id:
                        target = self.diffsync.client.get_by_query(tablename, {mapping["reference"]["column"]: value})
                        if target is None:
                            self.diffsync.job.logger.warning(f"Unable to find reference target in {tablename}")
                        else:
                            sys_id = target["sys_id"]
                            self._sys_id_cache.setdefault(tablename, {}).setdefault(column_name, {})[value] = sys_id
                record[mapping["reference"]["key"]] = sys_id
            else:
                raise NotImplementedError

        self.diffsync.job.logger.debug(f"Mapped data {data} to record {record}")
        return record

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create a new instance, data-driven by mappings."""
        entry = diffsync.mapping_data[cls.get_type()]

        model = super().create(diffsync, ids=ids, attrs=attrs)

        sn_resource = diffsync.client.resource(api_path=f"/table/{entry['table']}")
        sn_record = model.map_data_to_sn_record(data={**ids, **attrs}, mapping_entry=entry)
        sn_resource.create(payload=sn_record)

        return model

    def update(self, attrs):
        """Update an existing instance, data-driven by mappings."""
        entry = self.diffsync.mapping_data[self.get_type()]

        sn_resource = self.diffsync.client.resource(api_path=f"/table/{entry['table']}")
        query = self.map_data_to_sn_record(data=self.get_identifiers(), mapping_entry=entry)
        try:
            record = sn_resource.get(query=query).one()
        except pysnow.exceptions.MultipleResults:
            self.diffsync.job.logger.error(
                f"Unsure which record to update, as query {query} matched more than one item "
                f"in table {entry['table']}"
            )
            return None

        sn_record = self.map_data_to_sn_record(data=attrs, mapping_entry=entry, existing_record=record)
        sn_resource.update(query=query, payload=sn_record)

        super().update(attrs)
        return self

    def delete(self):
        """Delete an existing instance in ServiceNow if it does not exist in Nautobot. This code adds the ServiceNow object to the objects_to_delete dict of lists. The actual delete occurs in the post-run method of adapter_servicenow.py."""
        entry = self.diffsync.mapping_data[self.get_type()]
        sn_resource = self.diffsync.client.resource(api_path=f"/table/{entry['table']}")
        query = self.map_data_to_sn_record(data=self.get_identifiers(), mapping_entry=entry)
        try:
            sn_resource.get(query=query).one()
        except pysnow.exceptions.MultipleResults:
            self.diffsync.job.logger.error(
                f"Unsure which record to update, as query {query} matched more than one item "
                f"in table {entry['table']}"
            )
            return None
        self.diffsync.job.logger.warning(f"{self._modelname} {self.get_identifiers()} will be deleted.")
        _object = sn_resource.get(query=query)
        self.diffsync.objects_to_delete[self._modelname].append(_object)
        self.map_data_to_sn_record(
            data=self.get_identifiers(), mapping_entry=entry, clear_cache=True
        )  # remove device cache
        super().delete()
        return self


class Company(ServiceNowCRUDMixin, DiffSyncModel):
    """ServiceNow Company model."""

    _modelname = "company"
    _identifiers = ("name",)
    _attributes = ("manufacturer",)
    _children = {
        "product_model": "product_models",
    }

    name: str
    manufacturer: bool = True

    product_models: List["ProductModel"] = []

    sys_id: Optional[str] = None
    pk: Optional[uuid.UUID] = None


class ProductModel(ServiceNowCRUDMixin, DiffSyncModel):
    """ServiceNow Hardware Product Model model."""

    _modelname = "product_model"
    _identifiers = ("manufacturer_name", "model_name", "model_number")

    manufacturer_name: str
    # Nautobot has only one combined "model" field, but ServiceNow has both name and number
    model_name: str
    model_number: str

    sys_id: Optional[str] = None
    pk: Optional[uuid.UUID] = None


class Location(ServiceNowCRUDMixin, DiffSyncModel):
    """ServiceNow Location model."""

    _modelname = "location"
    _identifiers = ("name",)
    _attributes = (
        "parent_location_name",
        "latitude",
        "longitude",
    )
    _children = {
        "device": "devices",
    }

    name: str

    parent_location_name: Optional[str]
    # contained_locations: List["Location"] = []
    latitude: Union[float, str] = ""  # can't use Optional[float] because an empty string doesn't map to None
    longitude: Union[float, str] = ""

    devices: List["Device"] = []

    sys_id: Optional[str] = None
    pk: Optional[uuid.UUID] = None

    full_name: Optional[str] = None


class Device(ServiceNowCRUDMixin, DiffSyncModel):
    """ServiceNow Device model."""

    _modelname = "device"
    _identifiers = ("name",)
    # For now we do not store more of the device fields in ServiceNow:
    # platform, model, role, vendor
    # ...as we would need to sync these data models to ServiceNow as well, and we don't do that yet.
    _attributes = (
        "location_name",
        "asset_tag",
        "manufacturer_name",
        "model_name",
        "serial",
    )
    _children = {
        "interface": "interfaces",
    }

    name: str

    location_name: Optional[str]
    asset_tag: Optional[str]
    manufacturer_name: Optional[str]
    model_name: Optional[str]
    serial: Optional[str]

    # platform: Optional[str]
    # role: Optional[str]
    # vendor: Optional[str]

    interfaces: List["Interface"] = []

    sys_id: Optional[str] = None
    pk: Optional[uuid.UUID] = None

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create a new Device instance, and set things up for eventual bulk-creation of its child Interfaces."""
        model = super().create(diffsync, ids=ids, attrs=attrs)

        diffsync.job.logger.debug(
            f'New Device "{ids["name"]}" is being created, will bulk-create its interfaces later.'
        )
        diffsync.interfaces_to_create_per_device[ids["name"]] = []

        return model


class Interface(ServiceNowCRUDMixin, DiffSyncModel):
    """ServiceNow Interface model."""

    _modelname = "interface"
    _identifiers = (
        "device_name",
        "name",
    )
    _shortname = ("name",)
    # ServiceNow currently stores very little data about interfaces that we are interested in
    _attributes = ()

    _children = {"ip_address": "ip_addresses"}

    name: str
    device_name: str

    # access_vlan: Optional[int]
    # active: Optional[bool]
    allowed_vlans: List[str] = []
    description: Optional[str]
    # is_virtual: Optional[bool]
    # is_lag: Optional[bool]
    # is_lag_member: Optional[bool]
    lag_members: List[str] = []
    # mode: Optional[str]  # TRUNK, ACCESS, L3, NONE
    # mtu: Optional[int]
    # parent: Optional[str]
    # speed: Optional[int]
    # switchport_mode: Optional[str]
    # port_type: Optional[str]

    ip_addresses: List["IPAddress"] = []

    sys_id: Optional[str] = None
    pk: Optional[uuid.UUID] = None

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create an interface in isolation, or if the parent Device is new as well, defer for later bulk-creation."""
        if ids["device_name"] in diffsync.interfaces_to_create_per_device:
            diffsync.job.logger.debug(
                f'Device "{ids["device_name"]}" was just created; deferring creation of interface "{ids["name"]}"'
            )
            # copy-paste of DiffSyncModel's create() classmethod;
            # we don't want to call super().create() here as that would be ServiceNowCRUDMixin.create(),
            # which is what we're trying to avoid here!
            model = cls(**ids, diffsync=diffsync, **attrs)
            model.set_status(DiffSyncStatus.SUCCESS, "Deferred creation in ServiceNow")
            diffsync.interfaces_to_create_per_device[ids["device_name"]].append(model)
        else:
            model = super().create(diffsync, ids=ids, attrs=attrs)
        return model


class IPAddress(ServiceNowCRUDMixin, DiffSyncModel):
    """An IPv4 or IPv6 address."""

    _modelname = "ip_address"
    _identifiers = ("address",)
    _attributes = (
        "device_name",
        "interface_name",
    )

    address: str  # TODO: change to netaddr.IPAddress?

    device_name: Optional[str]
    interface_name: Optional[str]

    sys_id: Optional[str] = None
    pk: Optional[uuid.UUID] = None


Company.update_forward_refs()
Device.update_forward_refs()
Interface.update_forward_refs()
Location.update_forward_refs()
ProductModel.update_forward_refs()
