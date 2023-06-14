"""Nautobot Models for Infoblox integration with SSoT plugin."""
import ipaddress
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from nautobot.extras.choices import CustomFieldTypeChoices, LogLevelChoices
from nautobot.extras.models import RelationshipAssociation as OrmRelationshipAssociation
from nautobot.extras.models import CustomField as OrmCF
from nautobot.ipam.choices import IPAddressRoleChoices
from nautobot.ipam.models import IPAddress as OrmIPAddress
from nautobot.ipam.models import Prefix as OrmPrefix
from nautobot.ipam.models import VLAN as OrmVlan
from nautobot.ipam.models import VLANGroup as OrmVlanGroup
from nautobot_ssot.integrations.infoblox.constant import PLUGIN_CFG
from nautobot_ssot.integrations.infoblox.diffsync.models.base import Network, IPAddress, Vlan, VlanView
from nautobot_ssot.integrations.infoblox.utils.diffsync import create_tag_sync_from_infoblox
from nautobot_ssot.integrations.infoblox.utils.nautobot import get_prefix_vlans


def process_ext_attrs(diffsync, obj: object, extattrs: dict):
    """Process Extensibility Attributes into Custom Fields or link to found objects.

    Args:
        diffsync (object): DiffSync Job
        obj (object): The object that's being created or updated and needs processing.
        extattrs (dict): The Extensibility Attributes to be analyzed and applied to passed `prefix`.
    """
    for attr, attr_value in extattrs.items():
        if attr_value:
            if attr.lower() in ["site", "facility", "location"]:
                try:
                    obj.location_id = diffsync.location_map[attr_value]
                except KeyError as err:
                    diffsync.job.job_result.log(
                        f"Unable to find Location {attr_value} for {obj} found in Extensibility Attributes '{attr}'. {err}",
                        level_choice=LogLevelChoices.LOG_WARNING,
                    )
            if attr.lower() == "vrf":
                try:
                    obj.vrf_id = diffsync.vrf_map[attr_value]
                except KeyError as err:
                    diffsync.job.job_result.log(
                        f"Unable to find VRF {attr_value} for {obj} found in Extensibility Attributes '{attr}'. {err}",
                        level_choice=LogLevelChoices.LOG_WARNING,
                    )
            if "role" in attr.lower():
                if isinstance(obj, OrmIPAddress) and attr_value.lower() in IPAddressRoleChoices.as_dict():
                    obj.role = attr_value.lower()
                else:
                    try:
                        obj.role_id = diffsync.role_map[attr_value]
                    except KeyError as err:
                        diffsync.job.job_result.log(
                            f"Unable to find Role {attr_value} for {obj} found in Extensibility Attributes '{attr}'. {err}",
                            level_choice=LogLevelChoices.LOG_WARNING,
                        )

            if attr.lower() in ["tenant", "dept", "department"]:
                try:
                    obj.tenant_id = diffsync.tenant_map[attr_value]
                except KeyError as err:
                    diffsync.job.job_result.log(
                        f"Unable to find Tenant {attr_value} for {obj} found in Extensibility Attributes '{attr}'. {err}",
                        level_choice=LogLevelChoices.LOG_WARNING,
                    )
            _cf_dict = {
                "key": slugify(attr),
                "type": CustomFieldTypeChoices.TYPE_TEXT,
                "label": attr,
            }
            field, _ = OrmCF.objects.get_or_create(key=_cf_dict["key"], defaults=_cf_dict)
            field.content_types.add(ContentType.objects.get_for_model(type(obj)).id)
            obj.custom_field_data.update({_cf_dict["key"]: str(attr_value)})


class NautobotNetwork(Network):
    """Nautobot implementation of the Network Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Prefix object in Nautobot."""
        try:
            status = diffsync.status_map[attrs["status"]]
        except KeyError:
            status = diffsync.status_map[PLUGIN_CFG.get("default_status", "Active")]

        _prefix = OrmPrefix(
            prefix=ids["network"],
            status_id=status,
            description=attrs.get("description", ""),
        )
        if attrs.get("vlans"):
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
                    diffsync.job.job_result.log(
                        f"Unable to find VLAN {_vlan['vid']} {_vlan['name']} in {_vlan['group']}. {err}",
                        level_choice=LogLevelChoices.LOG_WARNING,
                    )

        if attrs.get("ext_attrs"):
            process_ext_attrs(diffsync=diffsync, obj=_prefix, extattrs=attrs["ext_attrs"])
        _prefix.tags.add(create_tag_sync_from_infoblox())
        diffsync.objects_to_create["prefixes"].append(_prefix)
        diffsync.prefix_map[ids["network"]] = _prefix.id
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):  # pylint: disable=too-many-branches
        """Update Prefix object in Nautobot."""
        _pf = OrmPrefix.objects.get(id=self.pk)
        if self.diffsync.job.debug:
            self.diffsync.job.job_result.log(
                f"Attempting to update Prefix {_pf.prefix} with {attrs}.", level_choice=LogLevelChoices.LOG_DEBUG
            )
        if "description" in attrs:
            _pf.description = attrs["description"]
        if "status" in attrs:
            try:
                _pf.status_id = self.diffsync.status_map[attrs["status"]]
            except KeyError:
                self.diffsync.job.job_result.log(
                    f"Unable to find Status {attrs['status']} to update prefix {_pf.prefix}.",
                    level_choice=LogLevelChoices.LOG_WARNING,
                )
        if "ext_attrs" in attrs:
            process_ext_attrs(diffsync=self.diffsync, obj=_pf, extattrs=attrs["ext_attrs"])
        if "vlans" in attrs:  # pylint: disable=too-many-nested-blocks
            current_vlans = get_prefix_vlans(prefix=_pf)
            if len(current_vlans) < len(attrs["vlans"]):
                for _, item in attrs["vlans"].items():
                    try:
                        vlan = OrmVlan.objects.get(vid=item["vid"], name=item["name"], group__name=item["group"])
                        if vlan not in current_vlans:
                            if self.diffsync.job.get("debug"):
                                self.diffsync.job.job_result.log(
                                    f"Adding VLAN {vlan.vid} to {_pf.prefix}.", level_choice=LogLevelChoices.LOG_DEBUG
                                )
                            OrmRelationshipAssociation.objects.get_or_create(
                                relationship_id=self.diffsync.relationship_map["Prefix -> VLAN"],
                                source_type=ContentType.objects.get_for_model(OrmPrefix),
                                source_id=_pf.id,
                                destination_type=ContentType.objects.get_for_model(OrmVlan),
                                destination_id=vlan.id,
                            )
                    except OrmVlan.DoesNotExist:
                        if self.diffsync.job.debug:
                            self.diffsync.job.job_result.log(
                                f"Unable to find VLAN {item['vid']} {item['name']} in {item['group']} to assign to prefix {_pf.prefix}.",
                                level_choice=LogLevelChoices.LOG_DEBUG,
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
                            self.diffsync.job.job_result.log(
                                f"Removing VLAN {vlan.vid} from {_pf.prefix}.", level_choice=LogLevelChoices.LOG_DEBUG
                            )
                        del_vlan.delete()
        _pf.validated_save()
        return super().update(attrs)

    # def delete(self):
    #     """Delete Prefix object in Nautobot."""
    #     self.diffsync.job.job_result.log(f"Prefix {self.network} will be deleted.", level_choice=LogLevelChoices.LOG_WARNING)
    #     _prefix = OrmPrefix.objects.get(id=self.pk)
    #     _prefix.delete()
    #     return super().delete()


class NautobotIPAddress(IPAddress):
    """Nautobot implementation of the IPAddress Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create IPAddress object in Nautobot."""
        _pf = ipaddress.ip_network(ids["prefix"])
        try:
            status = diffsync.status_map[attrs["status"]]
        except KeyError:
            status = diffsync.status_map[PLUGIN_CFG.get("default_status", "Active")]
        _ip = OrmIPAddress(
            address=f"{ids['address']}/{_pf.prefixlen}",
            status_id=status,
            description=attrs.get("description", ""),
            dns_name=attrs.get("dns_name", ""),
        )
        _ip.tags.add(create_tag_sync_from_infoblox())
        if attrs.get("ext_attrs"):
            process_ext_attrs(diffsync=diffsync, obj=_ip, extattrs=attrs["ext_attrs"])
        try:
            diffsync.objects_to_create["ipaddrs"].append(_ip)
            diffsync.ipaddr_map[_ip.address] = _ip.id
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)
        except ValidationError as err:
            diffsync.job.job_result.log(
                f"Error with validating IP Address {ids['address']}/{_pf.prefixlen}. {err}",
                level_choice=LogLevelChoices.LOG_WARNING,
            )
            return None

    def update(self, attrs):
        """Update IPAddress object in Nautobot."""
        _ipaddr = OrmIPAddress.objects.get(id=self.pk)
        if attrs.get("status"):
            try:
                status = self.diffsync.status_map[attrs["status"]]
            except KeyError:
                status = self.diffsync.status_map[PLUGIN_CFG.get("default_status", "Active")]
            _ipaddr.status_id = status
        if attrs.get("description"):
            _ipaddr.description = attrs["description"]
        if attrs.get("dns_name"):
            _ipaddr.dns_name = attrs["dns_name"]
        if "ext_attrs" in attrs:
            process_ext_attrs(diffsync=self.diffsync, obj=_ipaddr, extattrs=attrs["ext_attrs"])
        try:
            _ipaddr.validated_save()
            return super().update(attrs)
        except ValidationError as err:
            self.diffsync.job.job_result.log(
                f"Error with updating IP Address {self.address}. {err}", level_choice=LogLevelChoices.LOG_WARNING
            )
            return None

    # def delete(self):
    #     """Delete IPAddress object in Nautobot."""
    #     self.diffsync.job.job_result.log(f"IP Address {self.address} will be deleted.", level_choice=LogLevelChoices.LOG_WARNING)
    #     _ipaddr = OrmIPAddress.objects.get(id=self.pk)
    #     _ipaddr.delete()
    #     return super().delete()


class NautobotVlanGroup(VlanView):
    """Nautobot implementation of the VLANView model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create VLANGroup object in Nautobot."""
        _vg = OrmVlanGroup(
            name=ids["name"],
            slug=slugify(ids["name"]),
            description=attrs["description"],
        )
        if attrs.get("ext_attrs"):
            process_ext_attrs(diffsync=diffsync, obj=_vg, extattrs=attrs["ext_attrs"])
        diffsync.objects_to_create["vlangroups"].append(_vg)
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
        self.diffsync.job.job_result.log(
            f"VLAN Group {self.name} will be deleted.", level_choice=LogLevelChoices.LOG_WARNING
        )
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
        _vlan.tags.add(create_tag_sync_from_infoblox())
        try:
            diffsync.objects_to_create["vlans"].append(_vlan)
            if ids["vlangroup"] not in diffsync.vlan_map:
                diffsync.vlan_map[ids["vlangroup"]] = {}
            diffsync.vlan_map[ids["vlangroup"]][_vlan.vid] = _vlan.id
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)
        except ValidationError as err:
            diffsync.job.job_result.log(
                f"Unable to create VLAN {ids['name']} {ids['vid']}. {err}", level_choice=LogLevelChoices.LOG_WARNING
            )
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
        if not _vlan.group.location and _vlan.location:
            _vlan.group.location = _vlan.location
            _vlan.group.validated_save()
        try:
            _vlan.validated_save()
        except ValidationError as err:
            self.diffsync.job.job_result.log(
                f"Unable to update VLAN {_vlan.name} {_vlan.vid}. {err}", level_choice=LogLevelChoices.LOG_WARNING
            )
            return None
        return super().update(attrs)

    def delete(self):
        """Delete VLAN object in Nautobot."""
        self.diffsync.job.job_result.log(f"VLAN {self.vid} will be deleted.", level_choice=LogLevelChoices.LOG_WARNING)
        _vlan = OrmVlan.objects.get(id=self.pk)
        _vlan.delete()
        return super().delete()
