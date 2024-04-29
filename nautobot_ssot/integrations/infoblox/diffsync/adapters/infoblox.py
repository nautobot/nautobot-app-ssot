"""Infoblox Adapter for Infoblox integration with SSoT app."""

import re
from typing import Optional

from diffsync import DiffSync
from diffsync.enum import DiffSyncFlags
from diffsync.exceptions import ObjectAlreadyExists
from nautobot.extras.plugins.exceptions import PluginImproperlyConfigured

from nautobot_ssot.integrations.infoblox.constant import PLUGIN_CFG
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
)


class InfobloxAdapter(DiffSync):
    """DiffSync adapter using requests to communicate to Infoblox server."""

    namespace = InfobloxNamespace
    prefix = InfobloxNetwork
    ipaddress = InfobloxIPAddress
    vlangroup = InfobloxVLANView
    vlan = InfobloxVLAN

    top_level = ["namespace", "vlangroup", "vlan", "prefix", "ipaddress"]

    def __init__(self, *args, job=None, sync=None, conn, **kwargs):
        """Initialize Infoblox.

        Args:
            job (object, optional): Infoblox job. Defaults to None.
            sync (object, optional): Infoblox DiffSync. Defaults to None.
            conn (object): InfobloxAPI connection.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.conn = conn
        self.subnets = []

        if self.conn in [None, False]:
            self.job.logger.error(
                "Improperly configured settings for communicating to Infoblox. Please validate accuracy."
            )
            raise PluginImproperlyConfigured

    def load_network_views(self, sync_filters):
        """Load Namespace DiffSync model."""
        network_view_filters = {sf["network_view"] for sf in sync_filters if "network_view" in sf}
        networkviews = self.conn.get_network_views()
        default_ext_attrs = get_default_ext_attrs(review_list=networkviews)
        # TODO: Remove after development is done @progala
        self.job.logger.info(f"NVFilters: {network_view_filters}, NetworkViews: {networkviews}")
        for _nv in networkviews:
            # Do not load Network Views not present in the sync filters
            if _nv["name"] not in network_view_filters:
                continue
            namespace_name = map_network_view_to_namespace(_nv["name"])
            networkview_ext_attrs = get_ext_attr_dict(extattrs=_nv.get("extattrs", {}))
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
        network_view = None
        if "network_view" in sync_filter:
            network_view = sync_filter["network_view"]

        prefix_filter_attr = f"prefixes_{ip_version}"

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

        # We need to remove duplicate prefixes if Network View support is not enabled
        if not network_view:
            containers = self.conn.remove_duplicates(containers)
            subnets = self.conn.remove_duplicates(subnets)

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
            # Mimic default behavior of `infoblox_network_view` setting
            if "network_view" in sync_filter and not (pfx_filter_ipv4 or pfx_filter_ipv6):
                network_view = sync_filter["network_view"]
                if include_ipv4:
                    all_containers.extend(self.conn.get_network_containers(network_view=network_view))
                    all_subnets.extend(self.conn.get_all_subnets(network_view=network_view))
                if include_ipv6:
                    all_containers.extend(self.conn.get_network_containers(network_view=network_view, ipv6=True))
                    all_subnets.extend(self.conn.get_all_subnets(network_view=network_view, ipv6=True))

        return all_containers, all_subnets

    def _load_all_prefixes_unfiltered(self, include_ipv4: bool, include_ipv6: bool):
        """Loads all prefixes from Infoblox. Removes duplicates, if same prefix is found in different network views.

        Args:
            include_ipv4: Whether to include IPv4 prefixes
            include_ipv6: Whether to include IPv6 prefixes

        Returns:
            (tuple): Tuple consisting of list of container prefixes and a list of subnet prefixes
        """
        containers = []
        subnets = []
        if include_ipv4:
            containers.extend(self.conn.get_network_containers())
            subnets.extend(self.conn.get_all_subnets())
        if include_ipv6:
            containers.extend(self.conn.get_network_containers(ipv6=True))
            subnets.extend(self.conn.get_all_subnets(ipv6=True))

        containers = self.conn.remove_duplicates(containers)
        subnets = self.conn.remove_duplicates(subnets)

        return containers, subnets

    def load_prefixes(self, include_ipv4: bool, include_ipv6: bool, sync_filters: Optional[list] = None):
        """Load InfobloxNetwork DiffSync model."""
        # TODO: Need to align it with the new filter configuration, @progala
        legacy_sync_filter = {}
        if PLUGIN_CFG["NAUTOBOT_INFOBLOX_NETWORK_VIEW"]:
            legacy_sync_filter["network_view"] = PLUGIN_CFG["NAUTOBOT_INFOBLOX_NETWORK_VIEW"]
        if PLUGIN_CFG["infoblox_import_subnets"]:
            legacy_sync_filter["prefixes_ipv4"] = PLUGIN_CFG["infoblox_import_subnets"]
        # TODO: Validate there's no overlap between legacy_sync_filters and sync_filter
        # Alternatively, refuse to accept sync_filters if old flags are in place @progala
        sync_filters = PLUGIN_CFG["infoblox_sync_filters"]
        # TODO: Remove after development is done @progala
        self.job.logger.info(f"sync_filters: {sync_filters}")

        if not sync_filters:
            containers, subnets = self._load_all_prefixes_unfiltered(
                include_ipv4=include_ipv4, include_ipv6=include_ipv6
            )
        elif sync_filters:
            containers, subnets = self._load_all_prefixes_filtered(
                sync_filters, include_ipv4=include_ipv4, include_ipv6=include_ipv6
            )

        all_networks = containers + subnets
        self.subnets = [(x["network"], x["network_view"]) for x in subnets]
        default_ext_attrs = get_default_ext_attrs(review_list=all_networks)
        for _pf in all_networks:
            pf_ext_attrs = get_ext_attr_dict(extattrs=_pf.get("extattrs", {}))
            new_pf = self.prefix(
                network=_pf["network"],
                namespace=map_network_view_to_namespace(_pf["network_view"]),
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
                self.job.logger.warning(
                    f"Duplicate prefix found: {new_pf}. Duplicate prefixes are not supported, "
                    "and only the first occurrence will be included in the sync. To load data "
                    "from a single Network View, use the 'infoblox_network_view' setting."
                )

    def load_ipaddresses(self):
        """Load InfobloxIPAddress DiffSync model."""
        if self.job.debug:
            self.job.logger.debug("Loading IP addresses from Infoblox.")
        ipaddrs = self.conn.get_all_ipv4address_networks(prefixes=self.subnets)
        default_ext_attrs = get_default_ext_attrs(review_list=ipaddrs)
        for _ip in ipaddrs:
            _, prefix_length = _ip["network"].split("/")
            dns_name = ""
            if _ip["names"]:
                dns_name = get_dns_name(possible_fqdn=_ip["names"][0])
            namespace = map_network_view_to_namespace(_ip["network_view"])
            ip_ext_attrs = get_ext_attr_dict(extattrs=_ip.get("extattrs", {}))
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
            )
            if not loaded:
                self.job.logger.warning(
                    f"Duplicate IP Address {_ip['ip_address']}/{prefix_length} in {_ip['network']} attempting to be loaded."
                )

    def load_vlanviews(self):
        """Load InfobloxVLANView DiffSync model."""
        if self.job.debug:
            self.job.logger.debug("Loading VLAN Views from Infoblox.")
        vlanviews = self.conn.get_vlanviews()
        default_ext_attrs = get_default_ext_attrs(review_list=vlanviews)
        for _vv in vlanviews:
            vv_ext_attrs = get_ext_attr_dict(extattrs=_vv.get("extattrs", {}))
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
        vlans = self.conn.get_vlans()
        default_ext_attrs = get_default_ext_attrs(review_list=vlans)
        for _vlan in vlans:
            vlan_ext_attrs = get_ext_attr_dict(extattrs=_vlan.get("extattrs", {}))
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
        # Set ipv4 import to True as default
        include_ipv4 = True
        sync_filters = PLUGIN_CFG["infoblox_sync_filters"]
        if "infoblox_import_objects" in PLUGIN_CFG:
            # Use config setting to decide whether to import ipv6
            include_ipv6 = PLUGIN_CFG["infoblox_import_objects"].get("subnets_ipv6")
            self.load_network_views(include_ipv4=include_ipv4, include_ipv6=include_ipv6, sync_filters=sync_filters)
            if PLUGIN_CFG["infoblox_import_objects"].get("subnets"):
                self.load_prefixes(sync_filters=sync_filters)
            if PLUGIN_CFG["infoblox_import_objects"].get("ip_addresses"):
                self.load_ipaddresses()
            if PLUGIN_CFG["infoblox_import_objects"].get("vlan_views"):
                self.load_vlanviews()
            if PLUGIN_CFG["infoblox_import_objects"].get("vlans"):
                self.load_vlans()
        else:
            self.job.logger.info("The `infoblox_import_objects` setting was not found so all objects will be imported.")
            self.load_prefixes()
            self.load_ipaddresses()
            self.load_vlanviews()
            self.load_vlans()
        for obj in ["prefix", "ipaddress", "vlangroup", "vlan", "namespace"]:
            if obj in self.dict():
                self.job.logger.info(f"Loaded {len(self.dict()[obj])} {obj} from Infoblox.")

    def sync_complete(self, source, diff, flags=DiffSyncFlags.NONE, logger=None):
        """Add tags and custom fields to synced objects."""
        source.tag_involved_objects(target=self)
