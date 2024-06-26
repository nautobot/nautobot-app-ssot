"""Nautobot Models for Infoblox integration with SSoT app."""

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.models import CustomField as OrmCF
from nautobot.extras.models import RelationshipAssociation as OrmRelationshipAssociation
from nautobot.ipam.choices import IPAddressRoleChoices, IPAddressTypeChoices
from nautobot.ipam.models import VLAN as OrmVlan
from nautobot.ipam.models import IPAddress as OrmIPAddress
from nautobot.ipam.models import Namespace as OrmNamespace
from nautobot.ipam.models import Prefix as OrmPrefix
from nautobot.ipam.models import VLANGroup as OrmVlanGroup

from nautobot_ssot.integrations.infoblox.choices import (
    DNSRecordTypeChoices,
    FixedAddressTypeChoices,
    NautobotDeletableModelChoices,
)
from nautobot_ssot.integrations.infoblox.diffsync.models.base import (
    DnsARecord,
    DnsHostRecord,
    DnsPTRRecord,
    IPAddress,
    Namespace,
    Network,
    Vlan,
    VlanView,
)
from nautobot_ssot.integrations.infoblox.utils.diffsync import (
    create_tag_sync_from_infoblox,
    map_network_view_to_namespace,
)
from nautobot_ssot.integrations.infoblox.utils.nautobot import get_prefix_vlans


def process_ext_attrs(diffsync, obj: object, extattrs: dict):  # pylint: disable=too-many-branches
    """Process Extensibility Attributes into Custom Fields or link to found objects.

    Args:
        diffsync (object): DiffSync Job
        obj (object): The object that's being created or updated and needs processing.
        extattrs (dict): The Extensibility Attributes to be analyzed and applied to passed `prefix`.
    """
    for attr, attr_value in extattrs.items():  # pylint: disable=too-many-nested-blocks
        if attr_value:
            if attr.lower() in ["site", "facility", "location"]:
                try:
                    obj.location_id = diffsync.location_map[attr_value]
                except KeyError as err:
                    diffsync.job.logger.warning(
                        f"Unable to find Location {attr_value} for {obj} found in Extensibility Attributes '{attr}'. {err}"
                    )
                except TypeError as err:
                    diffsync.job.logger.warning(
                        f"Cannot set location values {attr_value} for {obj}. Multiple locations are assigned "
                        f"in Extensibility Attributes '{attr}', but multiple location assignments are not "
                        f"supported by Nautobot. {err}"
                    )
            if attr.lower() == "vrf":
                if isinstance(attr_value, list):
                    for vrf in attr_value:
                        try:
                            obj.vrfs.add(diffsync.vrf_map[vrf])
                        except KeyError as err:
                            diffsync.job.logger.warning(
                                f"Unable to find VRF {vrf} for {obj} found in Extensibility Attributes '{attr}'. {err}"
                            )
                else:
                    try:
                        obj.vrfs.add(diffsync.vrf_map[attr_value])
                    except KeyError as err:
                        diffsync.job.logger.warning(
                            f"Unable to find VRF {attr_value} for {obj} found in Extensibility Attributes '{attr}'. {err}"
                        )
            if "role" in attr.lower():
                if isinstance(obj, OrmIPAddress) and attr_value.lower() in IPAddressRoleChoices.as_dict():
                    obj.role = attr_value.lower()
                else:
                    try:
                        obj.role_id = diffsync.role_map[attr_value]
                    except KeyError as err:
                        diffsync.job.logger.warning(
                            f"Unable to find Role {attr_value} for {obj} found in Extensibility Attributes '{attr}'. {err}"
                        )
                    except TypeError as err:
                        diffsync.job.logger.warning(
                            f"Cannot set role values {attr_value} for {obj}. Multiple roles are assigned "
                            f"in Extensibility Attributes '{attr}', but multiple role assignments are not "
                            f"supported by Nautobot. {err}"
                        )
            if attr.lower() in ["tenant", "dept", "department"]:
                try:
                    obj.tenant_id = diffsync.tenant_map[attr_value]
                except KeyError as err:
                    diffsync.job.logger.warning(
                        f"Unable to find Tenant {attr_value} for {obj} found in Extensibility Attributes '{attr}'. {err}"
                    )
                except TypeError as err:
                    diffsync.job.logger.warning(
                        f"Cannot set tenant values {attr_value} for {obj}. Multiple tenants are assigned "
                        f"in Extensibility Attributes '{attr}', but multiple tenant assignments are not "
                        f"supported by Nautobot. {err}"
                    )
            _cf_dict = {
                "key": slugify(attr).replace("-", "_"),
                "type": CustomFieldTypeChoices.TYPE_TEXT,
                "label": attr,
            }
            field, _ = OrmCF.objects.get_or_create(key=_cf_dict["key"], defaults=_cf_dict)
            field.content_types.add(ContentType.objects.get_for_model(type(obj)).id)
            obj.custom_field_data.update({_cf_dict["key"]: str(attr_value)})


def _create_ip_address_common(diffsync: object, ids: dict, attrs: dict) -> IPAddress:
    """Creates common IP Address atrributes.

    Args:
        diffsync (object): diffsync adapter instance
        ids (dict): IP Address identifiers
        attrs (dict): IP Address attributes

    Returns:
        Partially instantiated IPAddress object
    """
    try:
        status = diffsync.status_map[attrs["status"]]
    except KeyError:
        status = diffsync.config.default_status.pk
    addr = f"{ids['address']}/{ids['prefix_length']}"
    if attrs.get("ip_addr_type"):
        if attrs["ip_addr_type"].lower() in IPAddressTypeChoices.as_dict():
            ip_addr_type = attrs["ip_addr_type"].lower()
        else:
            diffsync.logger.warning(
                f"unable to determine IPAddress Type for {addr}, defaulting to 'Host'",
                extra={"grouping": "create"},
            )
            ip_addr_type = "host"
    else:
        ip_addr_type = "host"
    _ip = OrmIPAddress(
        address=addr,
        status_id=status,
        type=ip_addr_type,
        parent_id=diffsync.prefix_map[(ids["namespace"], ids["prefix"])],
    )
    if attrs.get("ext_attrs"):
        process_ext_attrs(diffsync=diffsync, obj=_ip, extattrs=attrs["ext_attrs"])
    _ip.tags.add(create_tag_sync_from_infoblox())

    return _ip


def _get_ip_address_ds_key(address: object) -> tuple:
    """Get IP Address key used to find out PK of the IP Address objects.

    Args:
        address (object): Diffsync IPAddress object

    Returns:
        tuple containing key to the dict
    """
    ip_address_key = (f"{address.address}/{address.prefix_length}", address.namespace)

    return ip_address_key


class NautobotNetwork(Network):
    """Nautobot implementation of the Network Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Prefix object in Nautobot."""
        namespace_name = map_network_view_to_namespace(value=ids["namespace"], direction="nv_to_ns")
        _prefix = OrmPrefix(
            prefix=ids["network"],
            status_id=diffsync.status_map["Active"],
            type=attrs["network_type"],
            description=attrs.get("description", ""),
            namespace_id=diffsync.namespace_map[namespace_name],
        )
        prefix_ranges = attrs.get("ranges")
        if prefix_ranges:
            _prefix.cf["dhcp_ranges"] = ",".join(prefix_ranges)
        # Only attempt associating to VLANs if they were actually loaded
        if attrs.get("vlans") and diffsync.vlan_map:
            relation = diffsync.relationship_map["Prefix -> VLAN"]
            for _, _vlan in attrs["vlans"].items():
                index = 0
                try:
                    found_vlan = diffsync.vlan_map[_vlan["group"]][_vlan["vid"]]
                    if found_vlan:
                        if index == 0:
                            _prefix.vlan_id = found_vlan
                        OrmRelationshipAssociation.objects.get_or_create(
                            relationship_id=relation,
                            source_type=ContentType.objects.get_for_model(OrmPrefix),
                            source_id=_prefix.id,
                            destination_type=ContentType.objects.get_for_model(OrmVlan),
                            destination_id=found_vlan,
                        )
                    index += 1
                except KeyError as err:
                    diffsync.job.logger.warning(
                        f"Unable to find VLAN {_vlan['vid']} {_vlan['name']} in {_vlan['group']}. {err}"
                    )

        if attrs.get("ext_attrs"):
            process_ext_attrs(diffsync=diffsync, obj=_prefix, extattrs=attrs["ext_attrs"])
        _prefix.tags.add(create_tag_sync_from_infoblox())
        _prefix.validated_save()
        diffsync.prefix_map[(ids["namespace"], ids["network"])] = _prefix.id
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):  # pylint: disable=too-many-branches
        """Update Prefix object in Nautobot."""
        _pf = OrmPrefix.objects.get(id=self.pk)
        if self.diffsync.job.debug:
            self.diffsync.job.logger.debug(f"Attempting to update Prefix {_pf.prefix} with {attrs}.")
        if "description" in attrs:
            _pf.description = attrs["description"]
        if "network_type" in attrs:
            _pf.type = attrs["network_type"]
        if "ext_attrs" in attrs:
            process_ext_attrs(diffsync=self.diffsync, obj=_pf, extattrs=attrs["ext_attrs"])
        prefix_ranges = attrs.get("ranges")
        if prefix_ranges:
            _pf.cf["dhcp_ranges"] = ",".join(prefix_ranges)
        # Only attempt associating to VLANs if they were actually loaded
        if "vlans" in attrs and self.diffsync.vlan_map:  # pylint: disable=too-many-nested-blocks
            current_vlans = get_prefix_vlans(prefix=_pf)
            if len(current_vlans) < len(attrs["vlans"]):
                for _, item in attrs["vlans"].items():
                    try:
                        vlan = OrmVlan.objects.get(vid=item["vid"], name=item["name"], vlan_group__name=item["group"])
                        if vlan not in current_vlans:
                            if self.diffsync.job.get("debug"):
                                self.diffsync.job.logger.debug(f"Adding VLAN {vlan.vid} to {_pf.prefix}.")
                            OrmRelationshipAssociation.objects.get_or_create(
                                relationship_id=self.diffsync.relationship_map["Prefix -> VLAN"],
                                source_type=ContentType.objects.get_for_model(OrmPrefix),
                                source_id=_pf.id,
                                destination_type=ContentType.objects.get_for_model(OrmVlan),
                                destination_id=vlan.id,
                            )
                    except OrmVlan.DoesNotExist:
                        if self.diffsync.job.debug:
                            self.diffsync.job.logger.debug(
                                f"Unable to find VLAN {item['vid']} {item['name']} in {item['group']} to assign to prefix {_pf.prefix}."
                            )
                            continue
            else:
                for vlan in current_vlans:
                    if vlan.vid not in attrs["vlans"]:
                        del_vlan = OrmRelationshipAssociation.objects.get(
                            relationship_id=self.diffsync.relationship_map["Prefix -> VLAN"],
                            source_type=ContentType.objects.get_for_model(OrmPrefix),
                            source_id=_pf.id,
                            destination_type=ContentType.objects.get_for_model(OrmVlan),
                            destination_id=vlan.id,
                        )
                        if self.diffsync.job.debug:
                            self.diffsync.job.logger.debug(f"Removing VLAN {vlan.vid} from {_pf.prefix}.")
                        del_vlan.delete()
        _pf.validated_save()
        return super().update(attrs)


class NautobotIPAddress(IPAddress):
    """Nautobot implementation of the IPAddress Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create IPAddress object in Nautobot. Used for fixed address data only."""
        # Infoblox side doesn't have a fixed address record
        if not attrs.get("has_fixed_address", False):
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        addr_w_pfxl = f"{ids['address']}/{ids['prefix_length']}"
        if diffsync.config.fixed_address_type == FixedAddressTypeChoices.DONT_CREATE_RECORD:
            diffsync.job.logger.warning(
                f"Did not create Fixed Address {addr_w_pfxl}-{ids['namespace']}. It exists in Infoblox but Nautobot config has `fixed_address_type` set to `DONT_CREATE_RECORD`."
            )
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        if diffsync.job.debug:
            diffsync.job.logger.debug(f"Creating IP Address {addr_w_pfxl}")
        _ip = _create_ip_address_common(diffsync, ids, attrs)
        _ip.description = attrs.get("description") or ""
        if "mac_address" in attrs:
            _ip.custom_field_data.update({"mac_address": attrs.get("mac_address", "")})
        if "fixed_address_comment" in attrs:
            _ip.custom_field_data.update({"fixed_address_comment": attrs.get("fixed_address_comment") or ""})

        try:
            _ip.validated_save()
            diffsync.ipaddr_map[(f"{addr_w_pfxl}", ids["namespace"])] = _ip.id
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)
        except ValidationError as err:
            diffsync.job.logger.warning(f"Error with validating IP Address {addr_w_pfxl}-{ids['namespace']}. {err}")
            return None

    def update(self, attrs):  # pylint: disable=too-many-branches
        """Update IPAddress object in Nautobot."""
        # Description field should only be used by Fixed Address.
        # If description is cleared in Infoblox diffsync record it either means fixed address is gone or name was removed.
        # Either way we clear the field in Nautobot even if DONT_CREATE_RECORD is set.
        if attrs.get("description") == "" and FixedAddressTypeChoices.DONT_CREATE_RECORD:
            _ipaddr = OrmIPAddress.objects.get(id=self.pk)
            _ipaddr.description = attrs["description"]
            _ipaddr.custom_field_data.update({"fixed_address_comment": attrs.get("fixed_address_comment") or ""})
            try:
                _ipaddr.validated_save()
                return super().update(attrs)
            except ValidationError as err:
                self.diffsync.job.logger.warning(f"Error with updating IP Address {self.address}. {err}")
                return None

        if self.diffsync.config.fixed_address_type == FixedAddressTypeChoices.DONT_CREATE_RECORD:
            self.diffsync.job.logger.warning(
                f"Did not update Fixed Address {self.address}/{self.prefix_length}-{self.namespace}. "  # nosec: B608
                "It exists in Infoblox but Nautobot config has `fixed_address_type` set to `DONT_CREATE_RECORD`."
            )
            return super().update(attrs)

        _ipaddr = OrmIPAddress.objects.get(id=self.pk)
        if attrs.get("status"):
            try:
                status = self.diffsync.status_map[attrs["status"]]
            except KeyError:
                status = self.diffsync.config.default_status.pk
            _ipaddr.status_id = status
        if attrs.get("ip_addr_type"):
            if attrs["ip_addr_type"].lower() in IPAddressTypeChoices.as_dict():
                _ipaddr.type = attrs["ip_addr_type"].lower()
            else:
                _ipaddr.type = "host"
        if attrs.get("description"):
            _ipaddr.description = attrs["description"]
        if "ext_attrs" in attrs:
            process_ext_attrs(diffsync=self.diffsync, obj=_ipaddr, extattrs=attrs["ext_attrs"])
        if "mac_address" in attrs:
            _ipaddr.custom_field_data.update({"mac_address": attrs.get("mac_address", "")})
        if "fixed_address_comment" in attrs:
            _ipaddr.custom_field_data.update({"fixed_address_comment": attrs.get("fixed_address_comment") or ""})
        try:
            _ipaddr.validated_save()
            return super().update(attrs)
        except ValidationError as err:
            self.diffsync.job.logger.warning(f"Error with updating IP Address {self.address}. {err}")
            return None

    def delete(self):
        """Delete IPAddress object in Nautobot."""
        if NautobotDeletableModelChoices.IP_ADDRESS not in self.diffsync.config.nautobot_deletable_models:
            return super().delete()

        _ipaddr = OrmIPAddress.objects.get(id=self.pk)
        del self.diffsync.ipaddr_map[_get_ip_address_ds_key(self)]
        _ipaddr.delete()
        return super().delete()


class NautobotVlanGroup(VlanView):
    """Nautobot implementation of the VLANView model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create VLANGroup object in Nautobot."""
        _vg = OrmVlanGroup(
            name=ids["name"],
            description=attrs["description"],
        )
        if attrs.get("ext_attrs"):
            process_ext_attrs(diffsync=diffsync, obj=_vg, extattrs=attrs["ext_attrs"])
        _vg.validated_save()
        diffsync.vlangroup_map[ids["name"]] = _vg.id
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update VLANGroup object in Nautobot."""
        _vg = OrmVlanGroup.objects.get(id=self.pk)
        if "ext_attrs" in attrs:
            process_ext_attrs(diffsync=self.diffsync, obj=_vg, extattrs=attrs["ext_attrs"])
        return super().update(attrs)

    def delete(self):
        """Delete VLANGroup object in Nautobot."""
        if NautobotDeletableModelChoices.VLAN_GROUP not in self.diffsync.config.nautobot_deletable_models:
            return super().delete()

        self.diffsync.job.logger.warning(f"VLAN Group {self.name} will be deleted.")
        _vg = OrmVlanGroup.objects.get(id=self.pk)
        _vg.delete()
        return super().delete()


class NautobotVlan(Vlan):
    """Nautobot implementation of the Vlan model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create VLAN object in Nautobot."""
        _vlan = OrmVlan(
            vid=ids["vid"],
            name=ids["name"],
            status_id=diffsync.status_map[cls.get_vlan_status(attrs["status"])],
            vlan_group_id=diffsync.vlangroup_map[ids["vlangroup"]],
            description=attrs["description"],
        )
        if "ext_attrs" in attrs:
            process_ext_attrs(diffsync=diffsync, obj=_vlan, extattrs=attrs["ext_attrs"])
        try:
            _vlan.tags.add(create_tag_sync_from_infoblox())
            _vlan.validated_save()
            if ids["vlangroup"] not in diffsync.vlan_map:
                diffsync.vlan_map[ids["vlangroup"]] = {}
            diffsync.vlan_map[ids["vlangroup"]][_vlan.vid] = _vlan.id
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)
        except ValidationError as err:
            diffsync.job.logger.warning(f"Unable to create VLAN {ids['name']} {ids['vid']}. {err}")
            return None

    @staticmethod
    def get_vlan_status(status: str) -> str:
        """Return VLAN Status from mapping."""
        statuses = {
            "ASSIGNED": "Active",
            "UNASSIGNED": "Deprecated",
            "RESERVED": "Reserved",
        }
        return statuses[status]

    def update(self, attrs):
        """Update VLAN object in Nautobot."""
        _vlan = OrmVlan.objects.get(id=self.pk)
        if attrs.get("status"):
            _vlan.status_id = self.diffsync.status_map[self.get_vlan_status(attrs["status"])]
        if attrs.get("description"):
            _vlan.description = attrs["description"]
        if "ext_attrs" in attrs:
            process_ext_attrs(diffsync=self.diffsync, obj=_vlan, extattrs=attrs["ext_attrs"])
        if not _vlan.vlan_group.location and _vlan.location:
            _vlan.vlan_group.location = _vlan.location
            _vlan.vlan_group.validated_save()
        try:
            _vlan.validated_save()
        except ValidationError as err:
            self.diffsync.job.logger.warning(f"Unable to update VLAN {_vlan.name} {_vlan.vid}. {err}")
            return None
        return super().update(attrs)

    def delete(self):
        """Delete VLAN object in Nautobot."""
        if NautobotDeletableModelChoices.VLAN not in self.diffsync.config.nautobot_deletable_models:
            return super().delete()

        self.diffsync.job.logger.warning(f"VLAN {self.vid} will be deleted.")
        _vlan = OrmVlan.objects.get(id=self.pk)
        _vlan.delete()
        return super().delete()


class NautobotNamespace(Namespace):
    """Nautobot implementation of the Namespace model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Namespace object in Nautobot."""
        _ns = OrmNamespace(
            name=ids["name"],
        )
        if attrs.get("ext_attrs"):
            process_ext_attrs(diffsync=diffsync, obj=_ns, extattrs=attrs["ext_attrs"])
        try:
            _ns.tags.add(create_tag_sync_from_infoblox())
            _ns.validated_save()
            diffsync.namespace_map[ids["name"]] = _ns.id
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)
        except ValidationError as err:
            diffsync.job.logger.warning(f"Unable to create Namespace {_ns.name}. {err}")
            return None

    def update(self, attrs):
        """Update Namespace object in Nautobot."""
        _ns = OrmNamespace.objects.get(id=self.pk)
        if "ext_attrs" in attrs:
            process_ext_attrs(diffsync=self.diffsync, obj=_ns, extattrs=attrs["ext_attrs"])
        try:
            _ns.validated_save()
            return super().update(attrs)
        except ValidationError as err:
            self.diffsync.job.logger.warning(f"Unable to update Namespace {_ns.name}. {err}")
            return None

    def delete(self):
        """Don't allow deleting Namespaces in Nautobot."""
        self.diffsync.job.logger.error(
            f"Deleting Namespaces in Nautobot is not allowed. Infoblox Network View: {self.get_identifiers()['name']}"
        )
        raise NotImplementedError


class NautobotDnsARecord(DnsARecord):
    """Nautobot implementation of the DnsARecord Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create A Record data on IPAddress object in Nautobot."""
        addr_w_pfxl = f"{ids['address']}/{ids['prefix_length']}"

        if diffsync.config.dns_record_type not in (
            DNSRecordTypeChoices.A_RECORD,
            DNSRecordTypeChoices.A_AND_PTR_RECORD,
        ):
            diffsync.job.logger.warning(
                f"Can't create/update A record data for IP Address: {addr_w_pfxl}-{ids['namespace']}. Nautobot config is not set for A record operations."  # nosec: B608
            )
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        ip_pk = diffsync.ipaddr_map.get((addr_w_pfxl, ids["namespace"]))
        if ip_pk:
            if diffsync.job.debug:
                diffsync.job.logger.debug(
                    f"Adding A record data to an existing IP Address: {addr_w_pfxl}-{ids['namespace']}."
                )
            _ipaddr = OrmIPAddress.objects.get(id=ip_pk)
            _ipaddr.dns_name = attrs.get("dns_name") or ""
            _ipaddr.custom_field_data.update({"dns_a_record_comment": attrs.get("description") or ""})
            try:
                _ipaddr.validated_save()
            except ValidationError as err:
                diffsync.job.logger.warning(
                    f"Error with updating A record data for IP Address: {addr_w_pfxl}-{ids['namespace']}. {err}"
                )
                return None
        else:
            if diffsync.job.debug:
                diffsync.job.logger.debug(f"Creating IP Address from A record data: {addr_w_pfxl}-{ids['namespace']}.")
            try:
                _ipaddr = _create_ip_address_common(diffsync, ids, attrs)
                _ipaddr.dns_name = attrs.get("dns_name") or ""
                _ipaddr.custom_field_data.update({"dns_a_record_comment": attrs.get("description") or ""})
                _ipaddr.validated_save()
                diffsync.ipaddr_map[(addr_w_pfxl, ids["namespace"])] = _ipaddr.id
            except ValidationError as err:
                diffsync.job.logger.warning(
                    f"Error with creating IP Address from A record data: {addr_w_pfxl}-{ids['namespace']}. {err}"
                )
                return None

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update A Record data on IPAddress object in Nautobot."""
        if self.diffsync.config.dns_record_type not in (
            DNSRecordTypeChoices.A_RECORD,
            DNSRecordTypeChoices.A_AND_PTR_RECORD,
        ):
            self.diffsync.job.logger.warning(
                f"Can't update A record data for IP Address: {self.address}/{self.prefix_length}-{self.namespace}. Nautobot config is not set for A record operations."  # nosec: B608
            )
            return super().update(attrs)

        _ipaddr = OrmIPAddress.objects.get(id=self.pk)
        if attrs.get("dns_name"):
            _ipaddr.dns_name = attrs["dns_name"]
        if "description" in attrs:
            _ipaddr.custom_field_data.update({"dns_a_record_comment": attrs.get("description") or ""})
        try:
            _ipaddr.validated_save()
            return super().update(attrs)
        except ValidationError as err:
            self.diffsync.job.logger.warning(
                f"Error with updating A record data for IP Address: {self.address}/{self.prefix_length}-{self.namespace}. {err}"
            )
            return None

    def delete(self):
        """Delete A Record data on IPAddress object in Nautobot."""
        if NautobotDeletableModelChoices.DNS_A_RECORD not in self.diffsync.config.nautobot_deletable_models:
            return super().delete()

        if self.diffsync.config.dns_record_type not in (
            DNSRecordTypeChoices.A_RECORD,
            DNSRecordTypeChoices.A_AND_PTR_RECORD,
        ):
            self.diffsync.job.logger.warning(
                f"Can't delete A record data for IP Address: {self.address}/{self.prefix_length}-{self.namespace}. Nautobot config is not set for A record operations."
            )
            return super().delete()

        # Parent record has been already deleted
        if _get_ip_address_ds_key(self) not in self.diffsync.ipaddr_map:
            return super().delete()

        _ipaddr = OrmIPAddress.objects.get(id=self.pk)
        _ipaddr.dns_name = ""
        _ipaddr.custom_field_data.update({"dns_a_record_comment": ""})
        try:
            _ipaddr.validated_save()
            return super().delete()
        except ValidationError as err:
            self.diffsync.job.logger.warning(
                f"Error with deleting A record data for IP Address: {self.address}/{self.prefix_length}-{self.namespace}. {err}"
            )
            return None


class NautobotDnsHostRecord(DnsHostRecord):
    """Nautobot implementation of the DnsHostRecord Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Host Record data on IPAddress object in Nautobot."""
        addr_w_pfxl = f"{ids['address']}/{ids['prefix_length']}"

        if diffsync.config.dns_record_type != DNSRecordTypeChoices.HOST_RECORD:
            diffsync.job.logger.warning(
                f"Can't create/update Host record data for IP Address: {addr_w_pfxl}-{ids['namespace']}. Nautobot config is not set for Host record operations."  # nosec: B608
            )
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        ip_pk = diffsync.ipaddr_map.get((addr_w_pfxl, ids["namespace"]))
        if ip_pk:
            if diffsync.job.debug:
                diffsync.job.logger.debug(
                    f"Adding Host record data to an existing IP Address: {addr_w_pfxl}-{ids['namespace']}."
                )
            _ipaddr = OrmIPAddress.objects.get(id=ip_pk)
            _ipaddr.dns_name = attrs.get("dns_name") or ""
            _ipaddr.custom_field_data.update({"dns_host_record_comment": attrs.get("description") or ""})
            try:
                _ipaddr.validated_save()
            except ValidationError as err:
                diffsync.job.logger.warning(
                    f"Error with updating Host record data for IP Address: {addr_w_pfxl}-{ids['namespace']}. {err}"
                )
                return None
        else:
            if diffsync.job.debug:
                diffsync.job.logger.debug(
                    f"Creating IP Address from Host record data: {addr_w_pfxl}-{ids['namespace']}."
                )
            try:
                _ipaddr = _create_ip_address_common(diffsync, ids, attrs)
                _ipaddr.dns_name = attrs.get("dns_name") or ""
                _ipaddr.custom_field_data.update({"dns_host_record_comment": attrs.get("description") or ""})
                _ipaddr.validated_save()
                diffsync.ipaddr_map[(addr_w_pfxl, ids["namespace"])] = _ipaddr.id
            except ValidationError as err:
                diffsync.job.logger.warning(
                    f"Error with creating IP Address from Host record data: {addr_w_pfxl}-{ids['namespace']}. {err}"
                )
                return None

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Host Record data on IPAddress object in Nautobot."""
        if self.diffsync.config.dns_record_type != DNSRecordTypeChoices.HOST_RECORD:
            self.diffsync.job.logger.warning(
                f"Can't update Host record data for IP Address: {self.address}/{self.prefix_length}-{self.namespace}. Nautobot config is not set for Host record operations."  # nosec: B608
            )
            return super().update(attrs)

        _ipaddr = OrmIPAddress.objects.get(id=self.pk)
        if "dns_name" in attrs:
            _ipaddr.dns_name = attrs["dns_name"]
        if "description" in attrs:
            _ipaddr.custom_field_data.update({"dns_host_record_comment": attrs.get("description") or ""})
        try:
            _ipaddr.validated_save()
            return super().update(attrs)
        except ValidationError as err:
            self.diffsync.job.logger.warning(
                f"Error with updating Host record data for IP Address: {self.address}/{self.prefix_length}-{self.namespace}. {err}"
            )
            return None

    def delete(self):
        """Delete Host Record data on IPAddress object in Nautobot."""
        if NautobotDeletableModelChoices.DNS_HOST_RECORD not in self.diffsync.config.nautobot_deletable_models:
            return super().delete()

        if self.diffsync.config.dns_record_type != DNSRecordTypeChoices.HOST_RECORD:
            self.diffsync.job.logger.warning(
                f"Can't delete Host record data for IP Address: {self.address}/{self.prefix_length}-{self.namespace}. Nautobot config is not set for Host record operations."
            )
            return super().delete()

        # Parent record has been already deleted
        if _get_ip_address_ds_key(self) not in self.diffsync.ipaddr_map:
            return super().delete()

        _ipaddr = OrmIPAddress.objects.get(id=self.pk)
        _ipaddr.dns_name = ""
        _ipaddr.custom_field_data.update({"dns_host_record_comment": ""})
        try:
            _ipaddr.validated_save()
            return super().delete()
        except ValidationError as err:
            self.diffsync.job.logger.warning(
                f"Error with deleting Host record data for IP Address: {self.address}/{self.prefix_length}-{self.namespace}. {err}"
            )
            return None


class NautobotDnsPTRRecord(DnsPTRRecord):
    """Nautobot implementation of the DnsPTRRecord Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create PTR Record data on IPAddress object in Nautobot."""
        addr_w_pfxl = f"{ids['address']}/{ids['prefix_length']}"

        if diffsync.config.dns_record_type != DNSRecordTypeChoices.A_AND_PTR_RECORD:
            diffsync.job.logger.warning(
                f"Can't create/update PTR record data for IP Address: {addr_w_pfxl}-{ids['namespace']}. Nautobot config is not set for PTR record operations."  # nosec: B608
            )
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        ip_pk = diffsync.ipaddr_map.get((addr_w_pfxl, ids["namespace"]))
        if ip_pk:
            if diffsync.job.debug:
                diffsync.job.logger.debug(
                    f"Adding PTR record data to an existing IP Address: {addr_w_pfxl}-{ids['namespace']}."
                )
            _ipaddr = OrmIPAddress.objects.get(id=ip_pk)
            _ipaddr.dns_name = attrs.get("dns_name") or ""
            _ipaddr.custom_field_data.update({"dns_ptr_record_comment": attrs.get("description") or ""})
            try:
                _ipaddr.validated_save()
            except ValidationError as err:
                diffsync.job.logger.warning(
                    f"Error with updating PTR record data for IP Address: {addr_w_pfxl}-{ids['namespace']}. {err}"
                )
                return None
        else:
            # We don't allow creating IPs from PTR record only
            diffsync.job.logger.warning(
                f"Can't create PTR record on its own. Associated A record must be created for IP Address: {addr_w_pfxl}-{ids['namespace']}."
            )
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update PTR Record data on IPAddress object in Nautobot."""
        if self.diffsync.config.dns_record_type != DNSRecordTypeChoices.A_AND_PTR_RECORD:
            self.diffsync.job.logger.warning(
                f"Can't update PTR record data for IP Address: {self.address}/{self.prefix_length}-{self.namespace}. Nautobot config is not set for PTR record operations."  # nosec: B608
            )
            return super().update(attrs)

        _ipaddr = OrmIPAddress.objects.get(id=self.pk)
        if "description" in attrs:
            _ipaddr.custom_field_data.update({"dns_ptr_record_comment": attrs.get("description") or ""})
        try:
            _ipaddr.validated_save()
            return super().update(attrs)
        except ValidationError as err:
            self.diffsync.job.logger.warning(
                f"Error with updating PTR record data for IP Address: {self.address}/{self.prefix_length}-{self.namespace}. {err}"
            )
            return None

    def delete(self):
        """Delete PTR Record data on IPAddress object in Nautobot."""
        if NautobotDeletableModelChoices.DNS_PTR_RECORD not in self.diffsync.config.nautobot_deletable_models:
            return super().delete()

        if self.diffsync.config.dns_record_type != DNSRecordTypeChoices.A_AND_PTR_RECORD:
            self.diffsync.job.logger.warning(
                f"Can't delete PTR record data for IP Address: {self.address}/{self.prefix_length}-{self.namespace}. Nautobot config is not set for PTR record operations."
            )
            return super().delete()

        # Parent record has been already deleted
        if _get_ip_address_ds_key(self) not in self.diffsync.ipaddr_map:
            return super().delete()

        _ipaddr = OrmIPAddress.objects.get(id=self.pk)
        _ipaddr.custom_field_data.update({"dns_ptr_record_comment": ""})
        try:
            _ipaddr.validated_save()
            return super().delete()
        except ValidationError as err:
            self.diffsync.job.logger.warning(
                f"Error with deleting PTR record data for IP Address: {self.address}/{self.prefix_length}-{self.namespace}. {err}"
            )
            return None
