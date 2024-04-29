"""Nautobot Adapter for Infoblox integration."""

# pylint: disable=duplicate-code
import datetime
from typing import Optional

from diffsync import DiffSync
from diffsync.exceptions import ObjectAlreadyExists, ObjectNotFound
from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import Location
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.models import CustomField, Relationship, Role, Status, Tag
from nautobot.ipam.models import VLAN, IPAddress, Namespace, Prefix, VLANGroup
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.infoblox.constant import PLUGIN_CFG, TAG_COLOR
from nautobot_ssot.integrations.infoblox.diffsync.models import (
    NautobotIPAddress,
    NautobotNamespace,
    NautobotNetwork,
    NautobotVlan,
    NautobotVlanGroup,
)
from nautobot_ssot.integrations.infoblox.utils.diffsync import (
    get_default_custom_fields,
    map_network_view_to_namespace,
    nautobot_vlan_status,
)
from nautobot_ssot.integrations.infoblox.utils.nautobot import build_vlan_map_from_relations, get_prefix_vlans


class NautobotMixin:
    """Add specific objects onto Nautobot objects to provide information on sync status with Infoblox."""

    def tag_involved_objects(self, target):
        """Tag all objects that were successfully synced to the target."""
        # The ssot_synced_to_infoblox tag *should* have been created automatically during app installation
        # (see nautobot_ssot/integrations/infoblox/signals.py) but maybe a user deleted it inadvertently, so be safe:
        tag, _ = Tag.objects.get_or_create(
            name="SSoT Synced to Infoblox",
            defaults={
                "name": "SSoT Synced to Infoblox",
                "description": "Object synced at some point to Infoblox",
                "color": TAG_COLOR,
            },
        )
        for model in [IPAddress, Prefix, VLAN]:
            tag.content_types.add(ContentType.objects.get_for_model(model))
        # Ensure that the "ssot_synced_to_infoblox" custom field is present; as above, it *should* already exist.
        custom_field, _ = CustomField.objects.get_or_create(
            type=CustomFieldTypeChoices.TYPE_DATE,
            key="ssot_synced_to_infoblox",
            defaults={
                "label": "Last synced to Infoblox on",
            },
        )
        for model in [IPAddress, Prefix, VLAN, VLANGroup]:
            custom_field.content_types.add(ContentType.objects.get_for_model(model))

        for modelname in ["ipaddress", "prefix", "vlan", "vlangroup"]:
            for local_instance in self.get_all(modelname):
                unique_id = local_instance.get_unique_id()
                # Verify that the object now has a counterpart in the target DiffSync
                try:
                    target.get(modelname, unique_id)
                except ObjectNotFound:
                    continue

                self.tag_object(modelname, unique_id, tag, custom_field)

    def tag_object(self, modelname, unique_id, tag, custom_field):
        """Apply the given tag and custom field to the identified object."""
        model_instance = self.get(modelname, unique_id)
        today = datetime.date.today().isoformat()

        def _tag_object(nautobot_object):
            """Apply custom field and tag to object, if applicable."""
            if hasattr(nautobot_object, "tags"):
                nautobot_object.tags.add(tag)
            if hasattr(nautobot_object, "cf"):
                nautobot_object.cf[custom_field.key] = today
            nautobot_object.validated_save()

        if modelname == "ipaddress":
            _tag_object(IPAddress.objects.get(pk=model_instance.pk))
        elif modelname == "prefix":
            _tag_object(Prefix.objects.get(pk=model_instance.pk))
        elif modelname == "vlan":
            _tag_object(VLAN.objects.get(pk=model_instance.pk))
        elif modelname == "vlangroup":
            _tag_object(VLANGroup.objects.get(pk=model_instance.pk))


class NautobotAdapter(NautobotMixin, DiffSync):  # pylint: disable=too-many-instance-attributes
    """DiffSync adapter using ORM to communicate to Nautobot."""

    namespace = NautobotNamespace
    prefix = NautobotNetwork
    ipaddress = NautobotIPAddress
    vlangroup = NautobotVlanGroup
    vlan = NautobotVlan

    top_level = ["namespace", "vlangroup", "vlan", "prefix", "ipaddress"]

    status_map = {}
    location_map = {}
    relationship_map = {}
    tenant_map = {}
    vrf_map = {}
    namespace_map = {}
    prefix_map = {}
    role_map = {}
    ipaddr_map = {}
    vlan_map = {}
    vlangroup_map = {}

    def __init__(self, *args, job=None, sync=None, **kwargs):
        """Initialize Nautobot.

        Args:
            job (object, optional): Nautobot job. Defaults to None.
            sync (object, optional): Nautobot DiffSync. Defaults to None.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync

    def sync_complete(self, source: DiffSync, *args, **kwargs):
        """Process object creations/updates using bulk operations.

        Args:
            source (DiffSync): Source DiffSync adapter data.
        """
        super().sync_complete(source, *args, **kwargs)

    def _get_namespaces_from_sync_filters(self, sync_filters: list) -> set:
        """Get namespaces defined in filters."""
        namespaces = set()
        for sync_filter in sync_filters:
            if "network_view" not in sync_filter:
                continue
            namespace_name = map_network_view_to_namespace(sync_filter["network_view"])
            namespaces.add(namespace_name)

        return namespaces

    def load_namespaces(self, sync_filters: Optional[list] = None):
        """Load Namespace DiffSync model."""
        namespace_names = None
        if sync_filters:
            namespace_names = self._get_namespaces_from_sync_filters(sync_filters)
        if namespace_names:
            all_namespaces = Namespace.objects.filter(name__in=namespace_names)
        else:
            all_namespaces = Namespace.objects.all()

        default_cfs = get_default_custom_fields(cf_contenttype=ContentType.objects.get_for_model(Namespace))
        for namespace in all_namespaces:
            self.namespace_map[namespace.name] = namespace.id
            _namespace = self.namespace(
                name=namespace.name,
                ext_attrs={**default_cfs, **namespace.custom_field_data},
                pk=namespace.id,
            )
            try:
                self.add(_namespace)
            except ObjectAlreadyExists:
                self.job.logger.warning(f"Found duplicate namespace: {namespace.name}.")

    def _load_all_prefixes_filtered(self, sync_filters: list, include_ipv4: bool, include_ipv6: bool):
        """Loads prefixes from Nautobot based on the provided sync filter.

        Args:
            sync_filter (dict): Sync filter containing sync rules
            include_ipv4 (bool): Whether to include IPv4 prefixes
            include_ipv6 (bool): Whether to include IPv6 prefixes

        Returns:
            (PrefixQuerySet): PrefixQuerySet with prefixes
        """
        all_prefixes = Prefix.objects.none()
        for sync_filter in sync_filters:
            query_filters = {}
            if "network_view" in sync_filter:
                query_filters["namespace__name"] = sync_filter["network_view"]
            if "prefixes_ipv4" in sync_filter and include_ipv4:
                for pfx_ipv4 in sync_filter["prefixes_ipv4"]:
                    query_filters["network__net_contained_or_equal"] = pfx_ipv4
                    all_prefixes.union(Prefix.objects.filter(**query_filters))
            if "prefixes_ipv6" in sync_filter and include_ipv6:
                for pfx_ipv6 in sync_filter["prefixes_ipv6"]:
                    query_filters["network__net_contained_or_equal"] = pfx_ipv6
                    all_prefixes.union(Prefix.objects.filter(**query_filters))
            # Filter on namespace name only
            if "prefixes_ipv4" not in sync_filter and "prefixes_ipv6" not in sync_filter:
                all_prefixes.union(Prefix.objects.filter(**query_filters))

        return all_prefixes

    def load_prefixes(self, include_ipv4: bool, include_ipv6: bool, sync_filters: Optional[list]):
        """Load Prefixes from Nautobot."""
        if not sync_filters:
            all_prefixes = Prefix.objects.all()
        else:
            all_prefixes = self._load_all_prefixes_filtered(
                sync_filters=sync_filters, include_ipv4=include_ipv4, include_ipv6=include_ipv6
            )

        default_cfs = get_default_custom_fields(cf_contenttype=ContentType.objects.get_for_model(Prefix))
        for prefix in all_prefixes:
            self.prefix_map[(prefix.namespace.name), str(prefix.prefix)] = prefix.id
            if "ssot_synced_to_infoblox" in prefix.custom_field_data:
                prefix.custom_field_data.pop("ssot_synced_to_infoblox")
            current_vlans = get_prefix_vlans(prefix=prefix)
            _prefix = self.prefix(
                network=str(prefix.prefix),
                namespace=prefix.namespace.name,
                description=prefix.description,
                network_type=prefix.type,
                ext_attrs={**default_cfs, **prefix.custom_field_data},
                vlans=build_vlan_map_from_relations(vlans=current_vlans),
                pk=prefix.id,
            )
            dhcp_ranges = prefix.cf.get("dhcp_ranges")
            if dhcp_ranges:
                _prefix.ranges = dhcp_ranges.split(",")
            try:
                self.add(_prefix)
            except ObjectAlreadyExists:
                self.job.logger.warning(f"Found duplicate prefix: {prefix.prefix}.")

    def _load_all_ipaddresses_filtered(self, sync_filters: list, include_ipv4: bool, include_ipv6: bool):
        """Loads ip addresses from Nautobot based on the provided sync filter.

        Args:
            sync_filter (dict): Sync filter containing sync rules
            include_ipv4 (bool): Whether to include IPv4 addresses
            include_ipv6 (bool): Whether to include IPv6 addresses

        Returns:
            (IPAddressQuerySet): IPAddressQuerySet with ip addresses
        """
        all_ipaddresses = IPAddress.objects.none()
        for sync_filter in sync_filters:
            query_filters = {}
            if "network_view" in sync_filter:
                query_filters["parent__namespace__name"] = sync_filter["network_view"]
            if "prefixes_ipv4" in sync_filter and include_ipv4:
                query_filters["host__net_in"] = sync_filter["prefixes_ipv4"]
                all_ipaddresses.union(IPAddress.objects.filter(**query_filters))
            if "prefixes_ipv6" in sync_filter and include_ipv6:
                query_filters["host__net_in"] = sync_filter["prefixes_ipv6"]
                all_ipaddresses.union(IPAddress.objects.filter(**query_filters))
            # Filter on namespace name only
            if "prefixes_ipv4" not in sync_filter and "prefixes_ipv6" not in sync_filter:
                all_ipaddresses.union(IPAddress.objects.filter(**query_filters))

        return all_ipaddresses

    def load_ipaddresses(self, include_ipv4: bool, include_ipv6: bool, sync_filters: list):
        """Load IP Addresses from Nautobot."""
        default_cfs = get_default_custom_fields(cf_contenttype=ContentType.objects.get_for_model(IPAddress))
        if not sync_filters:
            all_ipaddresses = IPAddress.objects.all()
        else:
            all_ipaddresses = self._load_all_ipaddresses_filtered(
                sync_filters=sync_filters, include_ipv4=include_ipv4, include_ipv6=include_ipv6
            )
        for ipaddr in all_ipaddresses:
            self.ipaddr_map[str(ipaddr.address)] = ipaddr.id
            addr = ipaddr.host
            prefix = ipaddr.parent

            # The IP address must have a parent prefix
            # Note: In Nautobot 2.0 IP Address *must* have a parent prefix so this should not happen
            if not prefix:
                self.job.logger.warning(f"IP Address {addr} does not have a parent prefix and will not be synced.")
                self.ipaddr_map[str(ipaddr.address), "Global"] = ipaddr.id
                continue
            self.ipaddr_map[str(ipaddr.address), prefix.namespace.name] = ipaddr.id
            # IP address must be part of a prefix that is not a container
            # This means the IP cannot be associated with an IPv4 Network within Infoblox
            if prefix.type == "container":
                self.job.logger.warning(
                    f"IP Address {addr}'s parent prefix is a container. The parent prefix type must not be 'container'."
                )
                continue

            if "ssot_synced_to_infoblox" in ipaddr.custom_field_data:
                ipaddr.custom_field_data.pop("ssot_synced_to_infoblox")
            _ip = self.ipaddress(
                address=addr,
                prefix=str(prefix),
                namespace=prefix.namespace.name,
                status=ipaddr.status.name if ipaddr.status else None,
                ip_addr_type=ipaddr.type,
                prefix_length=prefix.prefix_length if prefix else ipaddr.prefix_length,
                dns_name=ipaddr.dns_name,
                description=ipaddr.description,
                ext_attrs={**default_cfs, **ipaddr.custom_field_data},
                pk=ipaddr.id,
            )
            try:
                self.add(_ip)
            except ObjectAlreadyExists:
                self.job.logger.warning(f"Duplicate IP Address detected: {addr}.")

    def load_vlangroups(self):
        """Load VLAN Groups from Nautobot."""
        default_cfs = get_default_custom_fields(cf_contenttype=ContentType.objects.get_for_model(VLANGroup))
        for grp in VLANGroup.objects.all():
            self.vlangroup_map[grp.name] = grp.id
            if "ssot_synced_to_infoblox" in grp.custom_field_data:
                grp.custom_field_data.pop("ssot_synced_to_infoblox")
            _vg = self.vlangroup(
                name=grp.name,
                description=grp.description,
                ext_attrs={**default_cfs, **grp.custom_field_data},
                pk=grp.id,
            )
            self.add(_vg)

    def load_vlans(self):
        """Load VLANs from Nautobot."""
        default_cfs = get_default_custom_fields(cf_contenttype=ContentType.objects.get_for_model(VLAN))
        # To ensure we are only dealing with VLANs imported from Infoblox we need to filter to those with a
        # VLAN Group assigned to match how Infoblox requires a VLAN View to be associated to VLANs.
        for vlan in VLAN.objects.filter(vlan_group__isnull=False):
            if vlan.vlan_group.name not in self.vlan_map:
                self.vlan_map[vlan.vlan_group.name] = {}
            self.vlan_map[vlan.vlan_group.name][vlan.vid] = vlan.id
            if "ssot_synced_to_infoblox" in vlan.custom_field_data:
                vlan.custom_field_data.pop("ssot_synced_to_infoblox")
            _vlan = self.vlan(
                vid=vlan.vid,
                name=vlan.name,
                description=vlan.description,
                vlangroup=vlan.vlan_group.name if vlan.vlan_group else "",
                status=nautobot_vlan_status(vlan.status.name),
                ext_attrs={**default_cfs, **vlan.custom_field_data},
                pk=vlan.id,
            )
            self.add(_vlan)

    def load(self):
        """Load models with data from Nautobot."""
        include_ipv4 = True
        include_ipv6 = PLUGIN_CFG.get("infoblox_import_objects", {}).get("subnets_ipv6", False)
        sync_filters = PLUGIN_CFG["infoblox_sync_filters"]
        self.relationship_map = {r.label: r.id for r in Relationship.objects.only("id", "label")}
        self.status_map = {s.name: s.id for s in Status.objects.only("id", "name")}
        self.location_map = {loc.name: loc.id for loc in Location.objects.only("id", "name")}
        self.tenant_map = {t.name: t.id for t in Tenant.objects.only("id", "name")}
        self.role_map = {r.name: r.id for r in Role.objects.only("id", "name")}
        self.load_namespaces(sync_filters=sync_filters)
        if "namespace" in self.dict():
            self.job.logger.info(f"Loaded {len(self.dict()['namespace'])} Namespaces from Nautobot.")
        self.load_prefixes(sync_filters=sync_filters, include_ipv4=include_ipv4, include_ipv6=include_ipv6)
        if "prefix" in self.dict():
            self.job.logger.info(f"Loaded {len(self.dict()['prefix'])} prefixes from Nautobot.")
        self.load_ipaddresses(sync_filters=sync_filters, include_ipv4=include_ipv4, include_ipv6=include_ipv6)
        if "ipaddress" in self.dict():
            self.job.logger.info(f"Loaded {len(self.dict()['ipaddress'])} IP addresses from Nautobot.")
        self.load_vlangroups()
        if "vlangroup" in self.dict():
            self.job.logger.info(f"Loaded {len(self.dict()['vlangroup'])} VLAN Groups from Nautobot.")
        self.load_vlans()
        if "vlan" in self.dict():
            self.job.logger.info(f"Loaded {len(self.dict()['vlan'])} VLANs from Nautobot.")
