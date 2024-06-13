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
from nautobot.ipam.choices import IPAddressTypeChoices
from nautobot.ipam.models import VLAN, IPAddress, Namespace, Prefix, VLANGroup
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.infoblox.choices import DNSRecordTypeChoices, FixedAddressTypeChoices
from nautobot_ssot.integrations.infoblox.constant import TAG_COLOR
from nautobot_ssot.integrations.infoblox.diffsync.models import (
    NautobotDnsARecord,
    NautobotDnsHostRecord,
    NautobotDnsPTRRecord,
    NautobotIPAddress,
    NautobotNamespace,
    NautobotNetwork,
    NautobotVlan,
    NautobotVlanGroup,
)
from nautobot_ssot.integrations.infoblox.utils.diffsync import (
    get_default_custom_fields,
    get_valid_custom_fields,
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
    dnshostrecord = NautobotDnsHostRecord
    dnsarecord = NautobotDnsARecord
    dnsptrrecord = NautobotDnsPTRRecord

    top_level = ["namespace", "vlangroup", "vlan", "prefix", "ipaddress", "dnshostrecord", "dnsarecord", "dnsptrrecord"]

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

    def __init__(self, *args, job=None, sync=None, config, **kwargs):
        """Initialize Nautobot.

        Args:
            job (object, optional): Nautobot job. Defaults to None.
            sync (object, optional): Nautobot DiffSync. Defaults to None.
            config (object): Infoblox config object.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.config = config
        self.excluded_cfs = config.cf_fields_ignore.get("custom_fields", [])

    def sync_complete(self, source: DiffSync, *args, **kwargs):
        """Process object creations/updates using bulk operations.

        Args:
            source (DiffSync): Source DiffSync adapter data.
        """
        super().sync_complete(source, *args, **kwargs)

    def _get_namespaces_from_sync_filters(self, sync_filters: list) -> set:
        """Get namespaces defined in filters.

        Args:
            sync_filters (list): Sync filters containing sync rules
        """
        namespaces = set()
        for sync_filter in sync_filters:
            namespace_name = map_network_view_to_namespace(value=sync_filter["network_view"], direction="nv_to_ns")
            namespaces.add(namespace_name)

        return namespaces

    def load_namespaces(self, sync_filters: Optional[list] = None):
        """Load Namespace DiffSync model.

        Args:
            sync_filters (list): Sync filters containing sync rules
        """
        if self.job.debug:
            self.job.logger.debug("Loading Namespaces from Nautobot.")
        namespace_names = None
        if sync_filters:
            namespace_names = self._get_namespaces_from_sync_filters(sync_filters)
        if namespace_names:
            all_namespaces = Namespace.objects.filter(name__in=namespace_names)
        else:
            all_namespaces = Namespace.objects.all()

        default_cfs = get_default_custom_fields(
            cf_contenttype=ContentType.objects.get_for_model(Namespace), excluded_cfs=self.excluded_cfs
        )
        for namespace in all_namespaces:
            self.namespace_map[namespace.name] = namespace.id
            custom_fields = get_valid_custom_fields(namespace.custom_field_data, excluded_cfs=self.excluded_cfs)
            _namespace = self.namespace(
                name=namespace.name,
                ext_attrs={**default_cfs, **custom_fields},
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
                namespace = map_network_view_to_namespace(sync_filter["network_view"], direction="nv_to_ns")
                query_filters["namespace__name"] = namespace
            if "prefixes_ipv4" in sync_filter and include_ipv4:
                for pfx_ipv4 in sync_filter["prefixes_ipv4"]:
                    query_filters["network__net_contained_or_equal"] = pfx_ipv4
                    all_prefixes = all_prefixes.union(Prefix.objects.filter(**query_filters))
            if "prefixes_ipv6" in sync_filter and include_ipv6:
                for pfx_ipv6 in sync_filter["prefixes_ipv6"]:
                    query_filters["network__net_contained_or_equal"] = pfx_ipv6
                    all_prefixes = all_prefixes.union(Prefix.objects.filter(**query_filters))
            # Filter on namespace name only
            if "prefixes_ipv4" not in sync_filter and "prefixes_ipv6" not in sync_filter:
                if include_ipv4 and not include_ipv6:
                    query_filters["ip_version"] = 4
                elif include_ipv6 and not include_ipv4:
                    query_filters["ip_version"] = 6
                all_prefixes = all_prefixes.union(Prefix.objects.filter(**query_filters))

        return all_prefixes

    def load_prefixes(self, include_ipv4: bool, include_ipv6: bool, sync_filters: list):
        """Load Prefixes from Nautobot.

        Args:
            sync_filters (list): List of dicts, each dict is a single sync filter definition
            include_ipv4 (bool): Whether to include IPv4 prefixes
            include_ipv6 (bool): Whether to include IPv6 prefixes
        """
        if self.job.debug:
            self.job.logger.debug("Loading Prefixes from Nautobot.")
        all_prefixes = self._load_all_prefixes_filtered(
            sync_filters=sync_filters, include_ipv4=include_ipv4, include_ipv6=include_ipv6
        )

        default_cfs = get_default_custom_fields(
            cf_contenttype=ContentType.objects.get_for_model(Prefix), excluded_cfs=self.excluded_cfs
        )
        for prefix in all_prefixes:
            self.prefix_map[(prefix.namespace.name), str(prefix.prefix)] = prefix.id
            dhcp_ranges = prefix.cf.get("dhcp_ranges")
            current_vlans = get_prefix_vlans(prefix=prefix)
            custom_fields = get_valid_custom_fields(prefix.custom_field_data, excluded_cfs=self.excluded_cfs)
            _prefix = self.prefix(
                network=str(prefix.prefix),
                namespace=prefix.namespace.name,
                description=prefix.description,
                network_type=prefix.type,
                ext_attrs={**default_cfs, **custom_fields},
                vlans=build_vlan_map_from_relations(vlans=current_vlans),
                pk=prefix.id,
            )
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
                namespace = map_network_view_to_namespace(sync_filter["network_view"], direction="nv_to_ns")
                query_filters["parent__namespace__name"] = namespace
            if "prefixes_ipv4" in sync_filter and include_ipv4:
                query_filters["host__net_in"] = sync_filter["prefixes_ipv4"]
                all_ipaddresses = all_ipaddresses.union(IPAddress.objects.filter(**query_filters))
            if "prefixes_ipv6" in sync_filter and include_ipv6:
                query_filters["host__net_in"] = sync_filter["prefixes_ipv6"]
                all_ipaddresses = all_ipaddresses.union(IPAddress.objects.filter(**query_filters))
            # Filter on namespace name only
            if "prefixes_ipv4" not in sync_filter and "prefixes_ipv6" not in sync_filter:
                if include_ipv4 and not include_ipv6:
                    query_filters["ip_version"] = 4
                elif include_ipv6 and not include_ipv4:
                    query_filters["ip_version"] = 6
                all_ipaddresses = all_ipaddresses.union(IPAddress.objects.filter(**query_filters))

        return all_ipaddresses

    def load_ipaddresses(
        self, include_ipv4: bool, include_ipv6: bool, sync_filters: list
    ):  # pylint: disable=too-many-branches
        """Load IP Addresses from Nautobot.

        Args:
            sync_filters (list): List of dicts, each dict is a single sync filter definition
            include_ipv4 (bool): Whether to include IPv4 IP addresses
            include_ipv6 (bool): Whether to include IPv6 addresses
        """
        if self.job.debug:
            self.job.logger.debug("Loading IP Addresses from Nautobot.")
        default_cfs = get_default_custom_fields(
            cf_contenttype=ContentType.objects.get_for_model(IPAddress), excluded_cfs=self.excluded_cfs
        )
        all_ipaddresses = self._load_all_ipaddresses_filtered(
            sync_filters=sync_filters, include_ipv4=include_ipv4, include_ipv6=include_ipv6
        )
        for ipaddr in all_ipaddresses:
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

            # Infoblox fixed address records are of type DHCP. Only Nautobot IP addresses of type DHCP will trigger fixed address creation logic.
            has_fixed_address = False
            mac_address = ipaddr.custom_field_data.get("mac_address") or ""
            if ipaddr.type == IPAddressTypeChoices.TYPE_DHCP:
                if self.config.fixed_address_type == FixedAddressTypeChoices.MAC_ADDRESS and mac_address:
                    has_fixed_address = True
                elif self.config.fixed_address_type == FixedAddressTypeChoices.RESERVED:
                    has_fixed_address = True

            # Description is used to derive name of the fixed record
            if self.config.fixed_address_type != FixedAddressTypeChoices.DONT_CREATE_RECORD:
                description = ipaddr.description
            else:
                description = ""

            custom_fields = get_valid_custom_fields(ipaddr.custom_field_data, excluded_cfs=self.excluded_cfs)
            _ip = self.ipaddress(
                address=addr,
                prefix=str(prefix),
                namespace=prefix.namespace.name,
                status=ipaddr.status.name if ipaddr.status else None,
                ip_addr_type=ipaddr.type,
                prefix_length=prefix.prefix_length if prefix else ipaddr.prefix_length,
                description=description,
                ext_attrs={**default_cfs, **custom_fields},
                mac_address=mac_address,
                pk=ipaddr.id,
                has_fixed_address=has_fixed_address,
                # Only set fixed address comment if we create fixed addresses.
                fixed_address_comment=(
                    ipaddr.custom_field_data.get("fixed_address_comment") or "" if has_fixed_address else ""
                ),
            )

            # Pretend IP Address has matching DNS records if `dns_name` is defined.
            # This will be compared against values set on Infoblox side.
            if ipaddr.dns_name:
                if self.config.dns_record_type == DNSRecordTypeChoices.HOST_RECORD:
                    _ip.has_host_record = True
                    self._load_dns_host_record_for_ip(
                        ip_record=_ip, dns_name=ipaddr.dns_name, cfs=ipaddr.custom_field_data
                    )
                elif self.config.dns_record_type == DNSRecordTypeChoices.A_RECORD:
                    _ip.has_a_record = True
                    self._load_dns_a_record_for_ip(
                        ip_record=_ip, dns_name=ipaddr.dns_name, cfs=ipaddr.custom_field_data
                    )
                elif self.config.dns_record_type == DNSRecordTypeChoices.A_AND_PTR_RECORD:
                    _ip.has_a_record = True
                    _ip.has_ptr_record = True
                    self._load_dns_ptr_record_for_ip(
                        ip_record=_ip, dns_name=ipaddr.dns_name, cfs=ipaddr.custom_field_data
                    )
                    self._load_dns_a_record_for_ip(
                        ip_record=_ip, dns_name=ipaddr.dns_name, cfs=ipaddr.custom_field_data
                    )

            try:
                self.add(_ip)
            except ObjectAlreadyExists:
                self.job.logger.warning(f"Duplicate IP Address detected: {addr}.")

    def _load_dns_host_record_for_ip(self, ip_record: NautobotIPAddress, dns_name: str, cfs: dict):
        """Load the DNS Host record.

        Args:
            ip_record (NautobotIPAddress): Parent IP Address record
            dns_name (str): DNS Name
            cfs (dict): Custom fields
        """
        new_host_record = self.dnshostrecord(
            address=ip_record.address,
            prefix=ip_record.prefix,
            prefix_length=ip_record.prefix_length,
            namespace=ip_record.namespace,
            dns_name=dns_name,
            ip_addr_type=ip_record.ip_addr_type,
            description=cfs.get("dns_host_record_comment") or "",
            status=ip_record.status,
            ext_attrs=ip_record.ext_attrs,
            pk=ip_record.pk,
        )

        self.add(new_host_record)

    def _load_dns_a_record_for_ip(self, ip_record: NautobotIPAddress, dns_name: str, cfs: dict):
        """Load the DNS A record.

        Args:
            ip_record (NautobotIPAddress): Parent IP Address record
            dns_name (str): DNS Name
            cfs (dict): Custom fields
        """
        new_a_record = self.dnsarecord(
            address=ip_record.address,
            prefix=ip_record.prefix,
            prefix_length=ip_record.prefix_length,
            namespace=ip_record.namespace,
            dns_name=dns_name,
            ip_addr_type=ip_record.ip_addr_type,
            description=cfs.get("dns_a_record_comment") or "",
            status=ip_record.status,
            ext_attrs=ip_record.ext_attrs,
            pk=ip_record.pk,
        )

        self.add(new_a_record)

    def _load_dns_ptr_record_for_ip(self, ip_record: NautobotIPAddress, dns_name: str, cfs: dict):
        """Load the DNS PTR record.

        Args:
            ip_record (NautobotIPAddress): Parent IP Address record
            dns_name (str): DNS Name
            cfs (dict): Custom fields
        """
        new_ptr_record = self.dnsptrrecord(
            address=ip_record.address,
            prefix=ip_record.prefix,
            prefix_length=ip_record.prefix_length,
            namespace=ip_record.namespace,
            dns_name=dns_name,
            ip_addr_type=ip_record.ip_addr_type,
            description=cfs.get("dns_ptr_record_comment") or "",
            status=ip_record.status,
            ext_attrs=ip_record.ext_attrs,
            pk=ip_record.pk,
        )

        self.add(new_ptr_record)

    def load_vlangroups(self):
        """Load VLAN Groups from Nautobot."""
        if self.job.debug:
            self.job.logger.debug("Loading VLAN Groups from Nautobot.")
        default_cfs = get_default_custom_fields(
            cf_contenttype=ContentType.objects.get_for_model(VLANGroup), excluded_cfs=self.excluded_cfs
        )
        for grp in VLANGroup.objects.all():
            self.vlangroup_map[grp.name] = grp.id
            custom_fields = get_valid_custom_fields(grp.custom_field_data, excluded_cfs=self.excluded_cfs)
            _vg = self.vlangroup(
                name=grp.name,
                description=grp.description,
                ext_attrs={**default_cfs, **custom_fields},
                pk=grp.id,
            )
            self.add(_vg)

    def load_vlans(self):
        """Load VLANs from Nautobot."""
        if self.job.debug:
            self.job.logger.debug("Loading VLANs from Nautobot.")
        default_cfs = get_default_custom_fields(
            cf_contenttype=ContentType.objects.get_for_model(VLAN), excluded_cfs=self.excluded_cfs
        )
        # To ensure we are only dealing with VLANs imported from Infoblox we need to filter to those with a
        # VLAN Group assigned to match how Infoblox requires a VLAN View to be associated to VLANs.
        for vlan in VLAN.objects.filter(vlan_group__isnull=False):
            if vlan.vlan_group.name not in self.vlan_map:
                self.vlan_map[vlan.vlan_group.name] = {}
            self.vlan_map[vlan.vlan_group.name][vlan.vid] = vlan.id
            custom_fields = get_valid_custom_fields(vlan.custom_field_data, excluded_cfs=self.excluded_cfs)
            _vlan = self.vlan(
                vid=vlan.vid,
                name=vlan.name,
                description=vlan.description,
                vlangroup=vlan.vlan_group.name if vlan.vlan_group else "",
                status=nautobot_vlan_status(vlan.status.name),
                ext_attrs={**default_cfs, **custom_fields},
                pk=vlan.id,
            )
            self.add(_vlan)

    def load(self):
        """Load models with data from Nautobot."""
        include_ipv4 = self.config.import_ipv4
        include_ipv6 = self.config.import_ipv6
        sync_filters = self.config.infoblox_sync_filters

        self.relationship_map = {r.label: r.id for r in Relationship.objects.only("id", "label")}
        self.status_map = {s.name: s.id for s in Status.objects.only("id", "name")}
        self.location_map = {loc.name: loc.id for loc in Location.objects.only("id", "name")}
        self.tenant_map = {t.name: t.id for t in Tenant.objects.only("id", "name")}
        self.role_map = {r.name: r.id for r in Role.objects.only("id", "name")}
        self.load_namespaces(sync_filters=sync_filters)
        if "namespace" in self.dict():
            self.job.logger.info(f"Loaded {len(self.dict()['namespace'])} Namespaces from Nautobot.")
        if self.config.import_subnets:
            self.load_prefixes(sync_filters=sync_filters, include_ipv4=include_ipv4, include_ipv6=include_ipv6)
        if "prefix" in self.dict():
            self.job.logger.info(f"Loaded {len(self.dict()['prefix'])} prefixes from Nautobot.")
        if self.config.import_ip_addresses:
            self.load_ipaddresses(sync_filters=sync_filters, include_ipv4=include_ipv4, include_ipv6=include_ipv6)
        if "ipaddress" in self.dict():
            self.job.logger.info(f"Loaded {len(self.dict()['ipaddress'])} IP addresses from Nautobot.")
        if self.config.import_vlan_views:
            self.load_vlangroups()
        if "vlangroup" in self.dict():
            self.job.logger.info(f"Loaded {len(self.dict()['vlangroup'])} VLAN Groups from Nautobot.")
        if self.config.import_vlans:
            self.load_vlans()
        if "vlan" in self.dict():
            self.job.logger.info(f"Loaded {len(self.dict()['vlan'])} VLANs from Nautobot.")
