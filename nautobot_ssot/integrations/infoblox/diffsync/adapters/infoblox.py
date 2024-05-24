"""Infoblox Adapter for Infoblox integration with SSoT app."""

import re
from typing import Optional

import requests

from diffsync import DiffSync
from diffsync.enum import DiffSyncFlags
from diffsync.exceptions import ObjectAlreadyExists
from nautobot.extras.plugins.exceptions import PluginImproperlyConfigured

from nautobot_ssot.integrations.infoblox.diffsync.models.infoblox import (
    InfobloxIPAddress,
    InfobloxNamespace,
    InfobloxNetwork,
    InfobloxVLAN,
    InfobloxVLANView,
)
from nautobot_ssot.integrations.infoblox.utils.client import get_default_ext_attrs, get_dns_name
from nautobot_ssot.integrations.infoblox.utils.diffsync import (
    build_vlan_map,
    get_ext_attr_dict,
    map_network_view_to_namespace,
    validate_dns_name,
)


class AdapterLoadException(Exception):
    """Raised when there's an error while loading data."""


class InfobloxAdapter(DiffSync):
    """DiffSync adapter using requests to communicate to Infoblox server."""

    namespace = InfobloxNamespace
    prefix = InfobloxNetwork
    ipaddress = InfobloxIPAddress
    vlangroup = InfobloxVLANView
    vlan = InfobloxVLAN

    top_level = ["namespace", "vlangroup", "vlan", "prefix", "ipaddress"]

    def __init__(self, *args, job=None, sync=None, conn, config, **kwargs):
        """Initialize Infoblox.

        Args:
            job (object, optional): Infoblox job. Defaults to None.
            sync (object, optional): Infoblox DiffSync. Defaults to None.
            conn (object): InfobloxAPI connection.
            config (object): Infoblox config object.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.conn = conn
        self.config = config
        self.excluded_attrs = config.cf_fields_ignore.get("extensible_attributes", [])
        self.subnets = []

        if self.conn in [None, False]:
            self.job.logger.error(
                "Improperly configured settings for communicating to Infoblox. Please validate accuracy."
            )
            raise PluginImproperlyConfigured

    def load_network_views(self, sync_filters: dict):
        """Load Namespace DiffSync model.

        Args:
            sync_filter (dict): Sync filter containing sync rules
        """
        if self.job.debug:
            self.job.logger.debug("Loading Network Views from Infoblox.")
        network_view_filters = {sf["network_view"] for sf in sync_filters if "network_view" in sf}
        try:
            networkviews = self.conn.get_network_views()
        except requests.exceptions.HTTPError as err:
            self.job.logger.error(f"Error while loading network views: {str(err)}")
            raise AdapterLoadException(str(err)) from err

        default_ext_attrs = get_default_ext_attrs(review_list=networkviews, excluded_attrs=self.excluded_attrs)
        for _nv in networkviews:
            # Do not load Network Views not present in the sync filters
            if _nv["name"] not in network_view_filters:
                continue
            namespace_name = map_network_view_to_namespace(value=_nv["name"], direction="nv_to_ns")
            networkview_ext_attrs = get_ext_attr_dict(
                extattrs=_nv.get("extattrs", {}), excluded_attrs=self.excluded_attrs
            )
            new_namespace = self.namespace(
                name=namespace_name,
                ext_attrs={**default_ext_attrs, **networkview_ext_attrs},
            )
            self.add(new_namespace)

    def _load_prefixes_filtered(self, sync_filter: dict, ip_version: str = "ipv4"):
        """Loads prefixes from Infoblox based on the provided sync filter.

        Args:
            sync_filter (dict): Sync filter containing sync rules
            ip_version (str): IP version of prefixes, either "ipv4" or "ipv6"

        Returns:
            (tuple): Tuple consisting of list of container prefixes and a list of subnet prefixes
        """
        containers = []
        subnets = []
        prefix_filter_attr = f"prefixes_{ip_version}"
        network_view = sync_filter["network_view"]

        for prefix in sync_filter[prefix_filter_attr]:
            tree = self.conn.get_tree_from_container(root_container=prefix, network_view=network_view)
            containers.extend(tree)
            # Need to check if the container has children. If it does, we need to get all subnets from the children
            # If it doesn't, we can just get all subnets from the container
            if tree:
                for subnet in tree:
                    subnets.extend(
                        self.conn.get_child_subnets_from_container(prefix=subnet["network"], network_view=network_view)
                    )
            else:
                subnets.extend(self.conn.get_all_subnets(prefix=prefix, network_view=network_view))

        return containers, subnets

    def _load_all_prefixes_filtered(self, sync_filters: list, include_ipv4: bool, include_ipv6: bool):
        """Loads all of the Infoblox prefixes based on the sync filter rules.

        Args:
            sync_filters (list): List of dicts, each dict is a single sync filter definition
            include_ipv4 (bool): Whether to include IPv4 prefixes
            include_ipv6 (bool): Whether to include IPv6 prefixes

        Returns:
            (tuple): Tuple consisting of list of container prefixes and a list of subnet prefixes
        """
        all_containers = []
        all_subnets = []
        for sync_filter in sync_filters:
            pfx_filter_ipv4 = "prefixes_ipv4" in sync_filter
            pfx_filter_ipv6 = "prefixes_ipv6" in sync_filter
            if pfx_filter_ipv4 and include_ipv4:
                containers, subnets = self._load_prefixes_filtered(sync_filter=sync_filter, ip_version="ipv4")
                all_containers.extend(containers)
                all_subnets.extend(subnets)
            if pfx_filter_ipv6 and include_ipv6:
                containers, subnets = self._load_prefixes_filtered(sync_filter=sync_filter, ip_version="ipv6")
                all_subnets.extend(subnets)
                all_containers.extend(containers)
            # Load all prefixes from a network view if there are no prefix filters
            if "network_view" in sync_filter and not (pfx_filter_ipv4 or pfx_filter_ipv6):
                network_view = sync_filter["network_view"]
                if include_ipv4:
                    all_containers.extend(self.conn.get_network_containers(network_view=network_view))
                    all_subnets.extend(self.conn.get_all_subnets(network_view=network_view))
                if include_ipv6:
                    all_containers.extend(self.conn.get_network_containers(network_view=network_view, ipv6=True))
                    all_subnets.extend(self.conn.get_all_subnets(network_view=network_view, ipv6=True))

        return all_containers, all_subnets

    def load_prefixes(self, include_ipv4: bool, include_ipv6: bool, sync_filters: Optional[list] = None):
        """Load InfobloxNetwork DiffSync model."""
        if self.job.debug:
            self.job.logger.debug("Loading Subnets from Infoblox.")
        try:
            containers, subnets = self._load_all_prefixes_filtered(
                sync_filters, include_ipv4=include_ipv4, include_ipv6=include_ipv6
            )
        except requests.exceptions.HTTPError as err:
            self.job.logger.error(f"Error while loading prefixes: {str(err)}")
            raise AdapterLoadException(str(err)) from err

        all_networks = containers + subnets
        self.subnets = [(x["network"], x["network_view"]) for x in subnets]
        default_ext_attrs = get_default_ext_attrs(review_list=all_networks, excluded_attrs=self.excluded_attrs)
        for _pf in all_networks:
            pf_ext_attrs = get_ext_attr_dict(extattrs=_pf.get("extattrs", {}), excluded_attrs=self.excluded_attrs)
            new_pf = self.prefix(
                network=_pf["network"],
                namespace=map_network_view_to_namespace(value=_pf["network_view"], direction="nv_to_ns"),
                description=_pf.get("comment", ""),
                network_type="network" if _pf in subnets else "container",
                ext_attrs={**default_ext_attrs, **pf_ext_attrs},
                vlans=build_vlan_map(vlans=_pf["vlans"]) if _pf.get("vlans") else {},
            )
            prefix_ranges = _pf.get("ranges")
            if prefix_ranges:
                new_pf.ranges = prefix_ranges
            try:
                self.add(new_pf)
            except ObjectAlreadyExists:
                self.job.logger.warning(f"Duplicate prefix found: {new_pf}.")

    def load_ipaddresses(self):
        """Load InfobloxIPAddress DiffSync model."""
        if self.job.debug:
            self.job.logger.debug("Loading IP addresses from Infoblox.")
        try:
            ipaddrs = self.conn.get_all_ipv4address_networks(prefixes=self.subnets)
        except requests.exceptions.HTTPError as err:
            self.job.logger.error(f"Error while loading IP addresses: {str(err)}")
            raise AdapterLoadException(str(err)) from err

        default_ext_attrs = get_default_ext_attrs(review_list=ipaddrs, excluded_attrs=self.excluded_attrs)
        for _ip in ipaddrs:
            _, prefix_length = _ip["network"].split("/")
            network_view = _ip["network_view"]
            dns_name = ""
            fallback_dns_name = ""
            # Record can have multiple names, if there is a DNS record attached we should use that name
            # Otherwise return non-DNS name
            for dns_name_candidate in _ip["names"]:
                if validate_dns_name(infoblox_client=self.conn, dns_name=dns_name_candidate, network_view=network_view):
                    dns_name = dns_name_candidate
                    break
                if not fallback_dns_name:
                    fallback_dns_name = get_dns_name(possible_fqdn=dns_name_candidate)

            dns_name = dns_name or fallback_dns_name
            namespace = map_network_view_to_namespace(value=network_view, direction="nv_to_ns")

            ip_ext_attrs = get_ext_attr_dict(extattrs=_ip.get("extattrs", {}), excluded_attrs=self.excluded_attrs)
            new_ip = self.ipaddress(
                address=_ip["ip_address"],
                prefix=_ip["network"],
                prefix_length=prefix_length,
                namespace=namespace,
                dns_name=dns_name,
                status=self.conn.get_ipaddr_status(_ip),
                ip_addr_type=self.conn.get_ipaddr_type(_ip),
                description=_ip["comment"],
                ext_attrs={**default_ext_attrs, **ip_ext_attrs},
                mac_address=None if not _ip["mac_address"] else _ip["mac_address"],
            )

            # Record references to DNS Records linked to this IP Address
            for ref in _ip["objects"]:
                obj_type = ref.split("/")[0]
                if obj_type == "record:host":
                    new_ip.has_host_record = True
                    new_ip.host_record_ref = ref
                elif obj_type == "record:a":
                    new_ip.has_a_record = True
                    new_ip.a_record_ref = ref
                elif obj_type == "record:ptr":
                    new_ip.has_ptr_record = True
                    new_ip.ptr_record_ref = ref
                elif obj_type == "fixedaddress":
                    new_ip.has_fixed_address = True
                    new_ip.fixed_address_ref = ref
                    if "RESERVATION" in _ip["types"]:
                        new_ip.fixed_address_type = "RESERVED"
                    elif "FA" in _ip["types"]:
                        new_ip.fixed_address_type = "MAC_ADDRESS"

            self.add(new_ip)

    def load_vlanviews(self):
        """Load InfobloxVLANView DiffSync model."""
        if self.job.debug:
            self.job.logger.debug("Loading VLAN Views from Infoblox.")
        try:
            vlanviews = self.conn.get_vlanviews()
        except requests.exceptions.HTTPError as err:
            self.job.logger.error(f"Error while loading VLAN views: {str(err)}")
            raise AdapterLoadException(str(err)) from err

        default_ext_attrs = get_default_ext_attrs(review_list=vlanviews, excluded_attrs=self.excluded_attrs)
        for _vv in vlanviews:
            vv_ext_attrs = get_ext_attr_dict(extattrs=_vv.get("extattrs", {}), excluded_attrs=self.excluded_attrs)
            new_vv = self.vlangroup(
                name=_vv["name"],
                description=_vv["comment"] if _vv.get("comment") else "",
                ext_attrs={**default_ext_attrs, **vv_ext_attrs},
            )
            self.add(new_vv)

    def load_vlans(self):
        """Load InfobloxVlan DiffSync model."""
        if self.job.debug:
            self.job.logger.debug("Loading VLANs from Infoblox.")
        try:
            vlans = self.conn.get_vlans()
        except requests.exceptions.HTTPError as err:
            self.job.logger.error(f"Error while loading VLANs: {str(err)}")
            raise AdapterLoadException(str(err)) from err

        default_ext_attrs = get_default_ext_attrs(review_list=vlans, excluded_attrs=self.excluded_attrs)
        for _vlan in vlans:
            vlan_ext_attrs = get_ext_attr_dict(extattrs=_vlan.get("extattrs", {}), excluded_attrs=self.excluded_attrs)
            vlan_group = re.search(r"(?:.+\:)(\S+)(?:\/\S+\/.+)", _vlan["_ref"])
            new_vlan = self.vlan(
                name=_vlan["name"],
                vid=_vlan["id"],
                status=_vlan["status"],
                vlangroup=vlan_group.group(1) if vlan_group else "",
                description=_vlan["comment"] if _vlan.get("comment") else "",
                ext_attrs={**default_ext_attrs, **vlan_ext_attrs},
            )
            self.add(new_vlan)

    def load(self):
        """Load all models by calling other methods."""
        include_ipv4 = self.config.import_ipv4
        include_ipv6 = self.config.import_ipv6
        sync_filters = self.config.infoblox_sync_filters

        self.load_network_views(sync_filters=sync_filters)
        if self.config.import_subnets:
            self.load_prefixes(include_ipv4=include_ipv4, include_ipv6=include_ipv6, sync_filters=sync_filters)
        if self.config.import_ip_addresses:
            self.load_ipaddresses()
        if self.config.import_vlan_views:
            self.load_vlanviews()
        if self.config.import_vlans:
            self.load_vlans()
        for obj in ["namespace", "prefix", "ipaddress", "vlangroup", "vlan"]:
            if obj in self.dict():
                self.job.logger.info(f"Loaded {len(self.dict()[obj])} {obj} from Infoblox.")

    def sync_complete(self, source, diff, flags=DiffSyncFlags.NONE, logger=None):
        """Add tags and custom fields to synced objects."""
        source.tag_involved_objects(target=self)
