"""DiffSyncModel subclasses for Nautobot-to-ServiceNow data sync."""

import uuid
from typing import List, Optional, Union

from diffsync import DiffSyncModel
from diffsync.enum import DiffSyncStatus
from diffsync.exceptions import ObjectNotCreated, ObjectNotUpdated

# import pysnow
from nautobot_ssot.integrations.servicenow.third_party import pysnow


class ServiceNowCRUDMixin:
    """Mixin class for all ServiceNow models, to support CRUD operations based on mappings.yaml."""

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
                        self.adapter.sys_ids_cache.setdefault(tablename, {}).setdefault(column_name, {})[value] = {}
                    # Look in the cache first
                    sys_id = self.adapter.sys_ids_cache.get(tablename, {}).get(column_name, {}).get(value, None)
                    if not sys_id:
                        target = self.adapter.client.get_by_query(tablename, {mapping["reference"]["column"]: value})
                        if target is None:
                            self.adapter.job.logger.warning(f"Unable to find reference target in {tablename}")
                        else:
                            sys_id = target["sys_id"]
                            self.adapter.sys_ids_cache.setdefault(tablename, {}).setdefault(column_name, {})[value] = (
                                sys_id
                            )

                record[mapping["reference"]["key"]] = sys_id
            else:
                raise NotImplementedError

        self.adapter.job.logger.debug(f"Mapped data {data} to record {record}")
        return record

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create a new instance, data-driven by mappings."""
        if adapter.job.debug:
            adapter.job.logger.debug(f"Creating {cls.get_type()} with identifiers {ids} and attributes {attrs}")
        entry = adapter.mapping_data[cls.get_type()]

        model = super().create(adapter, ids=ids, attrs=attrs)

        sn_resource = adapter.client.resource(api_path=f"/table/{entry['table']}")
        sn_record = model.map_data_to_sn_record(data={**ids, **attrs}, mapping_entry=entry)
        result = sn_resource.create(payload=sn_record)
        object_id = result.one().get("sys_id")
        if not object_id:
            adapter.job.logger.warning(
                f"Failed to create {cls.get_type()} with identifiers {ids} and attributes {attrs}"
            )
            raise ObjectNotCreated(f"Failed to create {cls.get_type()} with identifiers {ids} and attributes {attrs}")
        for key in sn_record:
            if key not in result.one():
                adapter.job.logger.warning(f"Key {key} from SN record {sn_record} not found in result {result.one()}")
            # Convert True/False to true/false before comparing
            if isinstance(sn_record[key], bool):
                sn_record[key] = "true" if sn_record[key] else "false"
            if sn_record[key] and sn_record[key] != result.one()[key]:
                adapter.job.logger.warning(
                    f"Value {sn_record[key]} from SN record {sn_record} does not match result {result.one()[key]}"
                )
                raise ObjectNotCreated(
                    f"Value {sn_record[key]} from SN record {sn_record} does not match result {result.one()[key]}"
                )

        # adapter.job.logger.debug(f"Created {cls.get_type()} with sys_id {result['sys_id']}")

        return model

    def update(self, attrs):
        """Update an existing instance, data-driven by mappings."""
        if self.adapter.job.debug:
            self.adapter.job.logger.debug(
                f"Updating {self.get_type()} with identifiers {self.get_identifiers()} and attributes {attrs}"
            )
        entry = self.adapter.mapping_data[self.get_type()]

        sn_resource = self.adapter.client.resource(api_path=f"/table/{entry['table']}")
        query = self.map_data_to_sn_record(data=self.get_identifiers(), mapping_entry=entry)
        try:
            record = sn_resource.get(query=query).one()
        except pysnow.exceptions.MultipleResults:
            self.adapter.job.logger.error(
                f"Unsure which record to update, as query {query} matched more than one item "
                f"in table {entry['table']}"
            )
            return None

        sn_record = self.map_data_to_sn_record(data=attrs, mapping_entry=entry, existing_record=record)
        result = sn_resource.update(query=query, payload=sn_record)
        if self.adapter.job.debug:
            self.adapter.job.logger.debug(f"Result of update: {result.one()}")
        for key in sn_record:
            if key not in result.one():
                self.adapter.job.logger.warning(
                    f"Key {key} from SN record {sn_record} not found in result {result.one()}"
                )
            # Convert True/False to true/false before comparing
            if isinstance(sn_record[key], bool):
                sn_record[key] = "true" if sn_record[key] else "false"
            if sn_record[key] and sn_record[key] != result.one()[key]:
                self.adapter.job.logger.warning(
                    f"Value {sn_record[key]} from SN record {sn_record} does not match result {result.one()[key]}"
                )
                raise ObjectNotUpdated(
                    f"Value {sn_record[key]} from SN record {sn_record} does not match result {result.one()[key]}"
                )

        super().update(attrs)
        return self

    def delete(self):
        """Delete an existing instance in ServiceNow if it does not exist in Nautobot. This code adds the ServiceNow object to the objects_to_delete dict of lists. The actual delete occurs in the post-run method of adapter_servicenow.py."""
        entry = self.adapter.mapping_data[self.get_type()]
        sn_resource = self.adapter.client.resource(api_path=f"/table/{entry['table']}")
        query = self.map_data_to_sn_record(data=self.get_identifiers(), mapping_entry=entry)
        try:
            sn_resource.get(query=query).one()
        except pysnow.exceptions.MultipleResults:
            self.adapter.job.logger.error(
                f"Unsure which record to update, as query {query} matched more than one item "
                f"in table {entry['table']}"
            )
            return None
        self.adapter.job.logger.warning(f"{self._modelname} {self.get_identifiers()} will be deleted.")
        _object = sn_resource.get(query=query)
        self.adapter.objects_to_delete[self._modelname].append(_object)
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

    location_name: Optional[str] = None
    asset_tag: Optional[str] = None
    manufacturer_name: Optional[str] = None
    model_name: Optional[str] = None
    serial: Optional[str] = None

    # platform: Optional[str] = None
    # role: Optional[str] = None
    # vendor: Optional[str] = None

    interfaces: List["Interface"] = []

    sys_id: Optional[str] = None
    pk: Optional[uuid.UUID] = None

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create a new Device instance, and set things up for eventual bulk-creation of its child Interfaces."""
        model = super().create(adapter, ids=ids, attrs=attrs)

        adapter.job.logger.debug(f'New Device "{ids["name"]}" is being created, will bulk-create its interfaces later.')
        adapter.interfaces_to_create_per_device[ids["name"]] = []

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

    # access_vlan: Optional[int] = None
    # active: Optional[bool] = None
    allowed_vlans: List[str] = []
    description: Optional[str] = None
    # is_virtual: Optional[bool] = None
    # is_lag: Optional[bool] = None
    # is_lag_member: Optional[bool] = None
    lag_members: List[str] = []
    # mode: Optional[str] = None  # TRUNK, ACCESS, L3, NONE
    # mtu: Optional[int] = None
    # parent: Optional[str] = None
    # speed: Optional[int] = None
    # switchport_mode: Optional[str] = None
    # port_type: Optional[str] = None

    ip_addresses: List["IPAddress"] = []

    sys_id: Optional[str] = None
    pk: Optional[uuid.UUID] = None

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create an interface in isolation, or if the parent Device is new as well, defer for later bulk-creation."""
        if ids["device_name"] in adapter.interfaces_to_create_per_device:
            adapter.job.logger.debug(
                f'Device "{ids["device_name"]}" was just created; deferring creation of interface "{ids["name"]}"'
            )
            # copy-paste of DiffSyncModel's create() classmethod;
            # we don't want to call super().create() here as that would be ServiceNowCRUDMixin.create(),
            # which is what we're trying to avoid here!
            model = cls(**ids, adapter=adapter, **attrs)
            model.set_status(DiffSyncStatus.SUCCESS, "Deferred creation in ServiceNow")
            adapter.interfaces_to_create_per_device[ids["device_name"]].append(model)
        else:
            model = super().create(adapter, ids=ids, attrs=attrs)
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

    device_name: Optional[str] = None
    interface_name: Optional[str] = None

    sys_id: Optional[str] = None
    pk: Optional[uuid.UUID] = None


Company.model_rebuild()
Device.model_rebuild()
Interface.model_rebuild()
Location.model_rebuild()
ProductModel.model_rebuild()
