"""DiffSyncModel subclasses for Nautobot-to-ServiceNow data sync."""

import uuid
from typing import List, Optional, Union

from diffsync import DiffSyncModel
from diffsync.enum import DiffSyncStatus
from diffsync.exceptions import ObjectNotCreated, ObjectNotDeleted, ObjectNotUpdated

from nautobot_ssot.integrations.servicenow.exceptions import (
    AmbiguousReferenceError,
    MissingReferenceError,
    ServiceNowReferenceError,
)

# import pysnow
from nautobot_ssot.integrations.servicenow.third_party import pysnow


def normalize_sn_value(value):
    """Render a value the way ServiceNow reports it, for comparison against a fetched record.

    ServiceNow returns every column as a string, using an empty string for an unset reference.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def record_matches(record, criteria):
    """Whether a fetched ServiceNow record satisfies every column/value pair in `criteria`."""
    return all(
        normalize_sn_value(record.get(column)) == normalize_sn_value(expected) for column, expected in criteria.items()
    )


class ServiceNowCRUDMixin:
    """Mixin class for all ServiceNow models, to support CRUD operations based on mappings.yaml."""

    def map_data_to_sn_record(self, data, mapping_entry, existing_record=None, context=None):
        """Map create/update data from DiffSync to a corresponding ServiceNow data record.

        Args:
            data (dict): Field values to write. Also decides *which* columns appear in the returned record,
                so an update payload stays limited to the changed fields.
            mapping_entry (dict): The mappings.yaml entry for this model.
            existing_record (dict): Record to populate in place, if any.
            context (dict): Additional field values used only to resolve and disambiguate references.
                Never written to ServiceNow. Needed on the update path, where `data` holds only the
                changed attributes and so may be missing the sibling fields a lookup needs.

        Raises:
            ServiceNowReferenceError: If a non-null reference value did not resolve to exactly one
                ServiceNow record. Returning a null column instead would silently drop the field while
                the sync went on to report success.
        """
        record = existing_record or {}
        context = {**(context or {}), **data}
        for mapping in mapping_entry.get("mappings", []):
            if mapping["field"] not in data:
                continue
            if "column" in mapping:
                record[mapping["column"]] = data[mapping["field"]]
            elif "reference" in mapping:
                if "column" not in mapping["reference"]:
                    raise NotImplementedError
                record[mapping["reference"]["key"]] = self._resolve_reference(mapping, context, record)
            else:
                raise NotImplementedError

        if self.adapter.job.debug:
            self.adapter.job.logger.debug(f"Mapped data {data} to record {record}")
        return record

    def _find_sn_records(self, table, criteria):
        """Records in `table` matching every column/value pair in `criteria`.

        The records pulled during load are consulted first: they already contain every candidate, so the
        happy path costs no API call. Only when the loaded set has nothing (because a `table_query` or
        `site_filter` narrowed the load) is ServiceNow queried, and a single hit joins the loaded set so
        an identical lookup later does not query again.
        """
        loaded = [record for record in self.adapter.sys_ids.get(table, {}).values() if record_matches(record, criteria)]
        if loaded:
            return loaded
        fetched = self.adapter.client.get_all_by_query(table, criteria)
        if len(fetched) == 1:
            self.adapter.register_sn_record(table, fetched[0])
        return fetched

    def _match_criteria(self, reference, context, record):
        """Build the extra column/value pairs that narrow an otherwise ambiguous reference lookup.

        Returns:
            tuple: (criteria, unapplied), where `unapplied` names the match fields whose value was not
            available, so that an ambiguity error can report why it could not be narrowed.
        """
        criteria = {}
        unapplied = []
        for entry in reference.get("match", []):
            # Prefer a sys_id already resolved for an earlier mapping in this same record: it is free.
            if entry.get("key") in record:
                criteria[entry["column"]] = record[entry["key"]]
                continue
            # Otherwise fall back to the DiffSync value, which on the update path is all we have.
            value = context.get(entry.get("field"))
            if value is not None and "reference" in entry:
                nested = entry["reference"]
                found = self._find_sn_records(nested["table"], {nested["column"]: value})
                value = found[0]["sys_id"] if len(found) == 1 else None
            if value is None:
                unapplied.append(entry.get("field") or entry["column"])
            else:
                criteria[entry["column"]] = value
        return criteria, unapplied

    def _resolve_reference(self, mapping, context, record):
        """Resolve a `reference` mapping to exactly one ServiceNow sys_id.

        Returns None only when the source value is itself None, i.e. the reference is being cleared.

        Raises:
            AmbiguousReferenceError: If more than one record matched.
            MissingReferenceError: If no record matched.
        """
        reference = mapping["reference"]
        table = reference["table"]
        column = reference["column"]
        value = context.get(mapping["field"])
        if value is None:
            return None

        criteria = {column: value}
        match_criteria, unapplied = self._match_criteria(reference, context, record)
        criteria.update(match_criteria)

        candidates = self._find_sn_records(table, criteria)
        if len(candidates) == 1:
            return candidates[0]["sys_id"]

        error_class = AmbiguousReferenceError if candidates else MissingReferenceError
        raise error_class(
            table=table,
            column=column,
            value=value,
            modelname=self.get_type(),
            unique_id=self.get_unique_id(),
            field=mapping["field"],
            candidates=[candidate["sys_id"] for candidate in candidates],
            unapplied=unapplied,
        )

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create a new instance, data-driven by mappings."""
        if adapter.job.debug:
            adapter.job.logger.debug(f"Creating {cls.get_type()} with identifiers {ids} and attributes {attrs}")
        entry = adapter.mapping_data[cls.get_type()]

        model = super().create(adapter, ids=ids, attrs=attrs)

        sn_resource = adapter.client.resource(api_path=f"/table/{entry['table']}")
        try:
            sn_record = model.map_data_to_sn_record(data={**ids, **attrs}, mapping_entry=entry)
        except ServiceNowReferenceError as error:
            adapter.record_unresolved_reference(error)
            raise ObjectNotCreated(str(error)) from error
        result = sn_resource.create(payload=sn_record)
        object_id = result.one().get("sys_id")
        if not object_id:
            adapter.job.logger.warning(
                f"Failed to create {cls.get_type()} with identifiers {ids} and attributes {attrs}"
            )
            raise ObjectNotCreated(f"Failed to create {cls.get_type()} with identifiers {ids} and attributes {attrs}")

        # Remember the new record so that objects created later in this same run can reference it
        # without querying ServiceNow for something we just wrote.
        model.sys_id = object_id
        adapter.register_sn_record(entry["table"], result.one())

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
        # `attrs` holds only the changed attributes, so reference lookups that need a sibling field
        # (such as resolving a model name within its manufacturer) have to read it from the current state.
        context = {**self.get_identifiers(), **self.get_attrs(), **attrs}
        try:
            if self.sys_id:
                query = {"sys_id": self.sys_id}
            else:
                query = self.map_data_to_sn_record(data=self.get_identifiers(), mapping_entry=entry, context=context)
            sn_record = self.map_data_to_sn_record(data=attrs, mapping_entry=entry, context=context)
        except ServiceNowReferenceError as error:
            self.adapter.record_unresolved_reference(error)
            raise ObjectNotUpdated(str(error)) from error

        try:
            result = sn_resource.update(query=query, payload=sn_record)
        except pysnow.exceptions.MultipleResults as error:
            message = (
                f"Unsure which record to update, as query {query} matched more than one item "
                f"in table {entry['table']}"
            )
            self.adapter.job.logger.error(message)
            raise ObjectNotUpdated(message) from error
        if self.adapter.job.debug:
            self.adapter.job.logger.debug(f"Result of update: {result.one()}")
        for key, value in sn_record.items():
            if key not in result.one():
                self.adapter.job.logger.warning(
                    f"Key {key} from SN record {sn_record} not found in result {result.one()}"
                )
            # Convert True/False to true/false before comparing
            if isinstance(value, bool):
                value = "true" if value else "false"
                sn_record[key] = value
            if value and value != result.one()[key]:
                self.adapter.job.logger.warning(
                    f"Value {value} from SN record {sn_record} does not match result {result.one()[key]}"
                )
                raise ObjectNotUpdated(
                    f"Value {value} from SN record {sn_record} does not match result {result.one()[key]}"
                )

        super().update(attrs)
        return self

    def delete(self):
        """Delete an existing instance in ServiceNow if it does not exist in Nautobot. This code adds the ServiceNow object to the objects_to_delete dict of lists. The actual delete occurs in the post-run method of adapter_servicenow.py."""
        entry = self.adapter.mapping_data[self.get_type()]
        sn_resource = self.adapter.client.resource(api_path=f"/table/{entry['table']}")
        try:
            query = self.map_data_to_sn_record(
                data=self.get_identifiers(),
                mapping_entry=entry,
                context={**self.get_identifiers(), **self.get_attrs()},
            )
        except ServiceNowReferenceError as error:
            # An unresolved reference would leave the query matching the wrong records, or none at all.
            self.adapter.record_unresolved_reference(error)
            raise ObjectNotDeleted(str(error)) from error

        _object = sn_resource.get(query=query)
        try:
            _object.one()
        except pysnow.exceptions.MultipleResults as error:
            message = (
                f"Unsure which record to delete, as query {query} matched more than one item "
                f"in table {entry['table']}"
            )
            self.adapter.job.logger.error(message)
            raise ObjectNotDeleted(message) from error
        self.adapter.job.logger.warning(f"{self._modelname} {self.get_identifiers()} will be deleted.")
        self.adapter.objects_to_delete[self._modelname].append(_object)
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

        if adapter.job.debug:
            adapter.job.logger.debug(
                f'New Device "{ids["name"]}" is being created, will bulk-create its interfaces later.'
            )
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
            if adapter.job.debug:
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
