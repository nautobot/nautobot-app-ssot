"""Mock Infoblox API client that generates synthetic data at configurable scale.

Produces realistic-looking network/IP/DNS data without making any real API calls.
The generated data follows the exact dict structure that InfobloxAdapter.load()
expects from the real InfobloxApi client.
"""

import ipaddress
import random


# Network view names in priority order — mirrors real-world naming conventions
_NV_NAMES = ["default", "prod", "staging", "mgmt", "dmz", "corp", "iot", "guest"]


class MockInfobloxClient:
    """Generates synthetic Infoblox API responses at configurable scale.

    Scale knobs:
        num_namespaces      — number of Infoblox network views
        prefixes_per_namespace — /24 subnets per network view
        ips_per_prefix      — host IPs to populate within each /24 (max 254)
        a_record_pct        — fraction of IPs that get an A record
        ptr_record_pct      — fraction of IPs that get a PTR record

    Every IP gets at least an A record so it passes the adapter's
    "has_fixed_address or has_a_record or has_host_record" guard.
    """

    def __init__(
        self,
        num_namespaces: int = 3,
        prefixes_per_namespace: int = 10,
        ips_per_prefix: int = 100,
        a_record_pct: float = 0.8,
        ptr_record_pct: float = 0.7,
        seed: int = 42,
    ):
        self.num_namespaces = num_namespaces
        self.prefixes_per_namespace = prefixes_per_namespace
        self.ips_per_prefix = min(ips_per_prefix, 254)
        self.a_record_pct = a_record_pct
        self.ptr_record_pct = ptr_record_pct

        rng = random.Random(seed)
        self._network_views = self._build_network_views()
        self._prefixes_by_nv = self._build_prefixes()
        self._ips_by_prefix_nv, self._dns_records = self._build_ips_and_dns(rng)

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _nv_name(self, idx: int) -> str:
        if idx < len(_NV_NAMES):
            return _NV_NAMES[idx]
        return f"nv-{idx}"

    def _build_network_views(self) -> list:
        return [{"name": self._nv_name(i), "extattrs": {}} for i in range(self.num_namespaces)]

    def _build_prefixes(self) -> dict:
        """Build prefix dicts keyed by network_view name.

        Uses 10.<nv_idx>.<pfx_idx>.0/24 addressing to guarantee uniqueness.
        """
        result = {}
        for nv_idx in range(self.num_namespaces):
            nv = self._nv_name(nv_idx)
            subnets = []
            for pfx_idx in range(self.prefixes_per_namespace):
                network = f"10.{nv_idx}.{pfx_idx}.0/24"
                subnets.append(
                    {
                        "_ref": f"network/ref:{network}/{nv}",
                        "network": network,
                        "network_view": nv,
                        "comment": f"Perf-test prefix {network} in {nv}",
                        "extattrs": {},
                        "rir": "NONE",
                        "vlans": [],
                        "ranges": [],
                    }
                )
            result[nv] = subnets
        return result

    def _build_ips_and_dns(self, rng: random.Random) -> tuple:
        """Build IP address dicts and DNS record lookup dicts.

        Returns:
            ips_by_key  — dict[(network_str, nv_name)] → list of IP dicts
            dns_records — dict[ref_str] → record dict (A or PTR)
        """
        ips_by_key = {}
        dns_records = {}

        for nv_idx in range(self.num_namespaces):
            nv = self._nv_name(nv_idx)
            for pfx_idx in range(self.prefixes_per_namespace):
                network_str = f"10.{nv_idx}.{pfx_idx}.0/24"
                hosts = list(ipaddress.IPv4Network(network_str).hosts())

                ip_list = []
                for host in hosts[: self.ips_per_prefix]:
                    ip_str = str(host)
                    hostname = f"host-{ip_str.replace('.', '-')}.example.com"

                    has_a = rng.random() < self.a_record_pct
                    has_ptr = rng.random() < self.ptr_record_pct

                    # Guarantee at least one A record so the adapter includes this IP
                    if not has_a:
                        has_a = True

                    objects = []

                    if has_a:
                        ref = f"record:a/ref_{ip_str}_{nv}"
                        objects.append(ref)
                        dns_records[ref] = {
                            "ipv4addr": ip_str,
                            "name": hostname,
                            "comment": "",
                            "extattrs": {},
                        }

                    if has_ptr:
                        ref = f"record:ptr/ref_{ip_str}_{nv}"
                        objects.append(ref)
                        dns_records[ref] = {
                            "ipv4addr": ip_str,
                            "ptrdname": hostname,
                            "comment": "",
                            "extattrs": {},
                        }

                    ip_list.append(
                        {
                            "ip_address": ip_str,
                            "network": network_str,
                            "network_view": nv,
                            "status": "USED",
                            "types": ["A"],
                            "objects": objects,
                            "mac_address": "",
                            "extattrs": {},
                            "names": [hostname],
                            "usage": ["DNS"],
                        }
                    )

                ips_by_key[(network_str, nv)] = ip_list

        return ips_by_key, dns_records

    # ------------------------------------------------------------------
    # InfobloxApi interface — methods called by InfobloxAdapter.load()
    # ------------------------------------------------------------------

    def get_network_views(self) -> list:
        return self._network_views

    def get_network_containers(self, network_view: str = None, ipv6: bool = False) -> list:
        return []

    def get_all_subnets(self, network_view: str = None, prefix: str = None, ipv6: bool = False) -> list:
        if ipv6:
            return []
        return self._prefixes_by_nv.get(network_view, [])

    def get_tree_from_container(self, root_container, network_view) -> list:
        return []

    def get_child_subnets_from_container(self, prefix, network_view) -> list:
        return []

    def get_all_ipv4address_networks(self, prefixes: list) -> list:
        """Return IPs for the given list of (network_str, network_view) tuples."""
        result = []
        for network, nv in prefixes:
            result.extend(self._ips_by_prefix_nv.get((network, nv), []))
        return result

    def get_ipaddr_status(self, ip_dict: dict) -> str:
        return "Active"

    def get_a_record_by_ref(self, ref: str) -> dict:
        return self._dns_records[ref]

    def get_ptr_record_by_ref(self, ref: str) -> dict:
        return self._dns_records[ref]

    def get_host_record_by_ref(self, ref: str) -> dict:
        return self._dns_records[ref]

    def get_fixed_address_by_ref(self, ref: str) -> dict:
        return {"name": "", "comment": ""}

    def get_vlanviews(self) -> list:
        return []

    def get_vlans(self) -> list:
        return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def expected_counts(self) -> dict:
        """Return the object counts this client will produce, for test assertions."""
        total_prefixes = sum(len(v) for v in self._prefixes_by_nv.values())
        total_ips = sum(len(v) for v in self._ips_by_prefix_nv.values())
        total_dns = len(self._dns_records)
        return {
            "namespaces": self.num_namespaces,
            "prefixes": total_prefixes,
            "ip_addresses": total_ips,
            "dns_records": total_dns,
            "total": self.num_namespaces + total_prefixes + total_ips + total_dns,
        }
