# pylint: disable=duplicate-code
"""DiffSync adapter class for Ip Fabric."""

import ipaddress
import logging
from collections import defaultdict
from itertools import chain

from diffsync import ObjectAlreadyExists
from diffsync.exceptions import ObjectNotFound
from nautobot.dcim.constants import NONCONNECTABLE_IFACE_TYPES
from nautobot.dcim.models import Device
from nautobot.ipam.models import VLAN
from netutils.interface import canonical_interface_name
from netutils.mac import mac_to_format

from nautobot_ssot.integrations.ipfabric.constants import (
    DEFAULT_CABLE_STATUS,
    DEFAULT_DEVICE_ROLE,
    DEFAULT_DEVICE_STATUS,
    DEFAULT_INTERFACE_MAC,
    DEFAULT_INTERFACE_MTU,
    IP_FABRIC_USE_CANONICAL_INTERFACE_NAME,
    PSEUDO_MANAGEMENT_INTERFACE_NAME,
    SYNC_IPF_DEV_TYPE_TO_ROLE,
)
from nautobot_ssot.integrations.ipfabric.diffsync import DiffSyncModelAdapters
from nautobot_ssot.integrations.ipfabric.utilities import utils as ipfabric_utils
from nautobot_ssot.integrations.ipfabric.utilities.cables import canonical_endpoints
from nautobot_ssot.integrations.ipfabric.utilities.utils import host_route_length

try:
    from ipfabric import IPFClient
except ImportError:
    IPFClient = None


logger = logging.getLogger("nautobot.jobs")

device_serial_max_length = Device._meta.get_field("serial").max_length
name_max_length = VLAN._meta.get_field("name").max_length

# Keys the FHRP tables may carry the virtual address under. IP Fabric discovers a table's columns
# from the appliance rather than declaring them in the SDK, so the name is confirmed at run time and
# a table that carries none of these is reported rather than passed over in silence.
FHRP_VIRTUAL_ADDRESS_KEYS = ("vip", "virtualIp", "virtualIP")

# Marks a record whose address has no subnet of its own to report, and so may take the subnet of an
# address already resolved for its Interface. True of an FHRP virtual address, which is configured
# against a group rather than an interface. Not true of a managed address the table simply did not
# cover: there the subnet is missing data, and inferring one would write the address under a parent
# Prefix IP Fabric never reported.
INHERITS_SUBNET = "_inherits_subnet"


# pylint: disable=too-many-locals,too-many-nested-blocks,too-many-branches
class IPFabricDiffSync(DiffSyncModelAdapters):
    """IPFabric adapter for DiffSync."""

    def __init__(self, job, sync, client: IPFClient, location_filter, *args, **kwargs):
        """Initialize the NautobotDiffSync."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.client = client
        # Resolved once addressing is read, and empty when addresses are out of scope.
        self.prefix_length_by_address = {}
        # Addresses already reported as having no subnet, so that an address on many Interfaces is
        # reported once. A job log entry is a database write, so this is I/O rather than noise.
        self._reported_missing_subnet = set()
        # Every address IP Fabric reports, indexed by the Interface it sits on.
        self.addresses_by_interface = defaultdict(list)
        # Held because a VRF is network wide while this filter is not, so a filtered run must not
        # delete the VRFs of the sites it cannot see; see `DiffSyncModelAdapters.network_wide`.
        self.location_filter = location_filter
        if location_filter:
            self.client.attribute_filters = {"siteName": ["ieq", location_filter]}
            logging.info("Applied IP Fabric Attribute Filter: %s", self.client.attribute_filters)

    def load_sites(self):
        """Add IP Fabric Location objects as DiffSync Location models.

        Loaded even when Locations are out of scope, since Devices and VLANs are their children, but
        then as tree nodes carrying placeholder attributes rather than as data to write.
        """
        sites = self.client.inventory.sites.all()
        for site in sites:
            try:
                self.add(self.location_model(site["siteName"], site_id=site["id"], status="Active"))
            except ObjectAlreadyExists:
                logger.warning(f"Duplicate Location discovered, {site}")

    def load_device_interfaces(self, device_model, device_interfaces, device_primary_ips):
        """Create and load DiffSync Interface model objects for a specific device."""
        # The pseudo interface exists only to carry a NAT management address, so with addresses out
        # of scope there is nothing for it to hold, and strict about Interfaces there is nothing this
        # side may invent. Skipped rather than passed a null address, which
        # `pseudo_management_interface` reads as "no Interface claims it", fabricating one for it.
        pseudo_interface = (
            pseudo_management_interface(device_model.name, device_interfaces, device_primary_ips)
            if self.carries_pseudo_management_interface()
            else None
        )

        if pseudo_interface:
            device_interfaces.append(pseudo_interface)
            logger.info("Pseudo MGMT Interface: %s", pseudo_interface)

        for iface in device_interfaces:
            iface_name = iface["intName"]
            if IP_FABRIC_USE_CANONICAL_INTERFACE_NAME:
                iface_name = canonical_interface_name(iface_name)

            try:
                interface = self.interface(
                    name=iface_name,
                    device_name=iface.get("hostname"),
                    description=iface.get("dscr", ""),
                    enabled=True,
                    mac_address=(
                        mac_to_format(iface.get("mac"), "MAC_COLON_TWO").upper()
                        if iface.get("mac")
                        else DEFAULT_INTERFACE_MAC
                    ),
                    mtu=iface.get("mtu") if iface.get("mtu") else DEFAULT_INTERFACE_MTU,
                    type=ipfabric_utils.convert_media_type(iface.get("media"), iface_name),
                    mgmt_only=iface.get("mgmt_only", False),
                    status="Active",
                )
                self.add(interface)
                device_model.add_child(interface)
            except ObjectAlreadyExists:
                logger.warning(f"Duplicate Interface discovered, {iface}")
                continue
            # Addresses are their own models under the Interface. Out of scope none is reported, so
            # the Nautobot adapter reports none either and what it holds is left alone.
            if self.scope.ip_addresses:
                self.load_interface_addresses(interface, iface, iface_name, device_primary_ips)

    def prefix_length_of(self, record, iface_name, resolved):
        """Return the prefix length IP Fabric reports for a record's address, or None if it has none.

        Four sources, in order, so that every address resolves the same way whichever table it came
        from. The managed address table first, which is the only place IP Fabric says what subnet an
        address was configured with. Then the record's own subnet, which only the Interface this
        adapter fabricates carries, and it says so itself. Then a subnet already resolved for this
        Interface that contains the address, for a record marked `INHERITS_SUBNET`. A NAT management
        address resolves at the second rung,
        where a host route is the value rather than a fallback; whether it is carried at all is the
        separate question `strict.interfaces` answers.

        Where nothing resolves it and addresses are not among the object types this run is strict
        about, it falls back to a host route, reported once per address so that every address it was
        applied to can be found. Once per address rather than once per use, because one address can
        be on many Interfaces and a job log entry is a database write; the length is chosen per
        address anyway, so there is nothing a second report would add.
        """
        host = record["ip"]
        # One length per address rather than per device: see `prefix_lengths_by_address`.
        length = self.prefix_length_by_address.get(host)
        if length is not None:
            return length
        if record.get("net"):
            own_length = reported_prefix_length(record["net"])
            if own_length is not None:
                return own_length
        if record.get(INHERITS_SUBNET):
            containing = containing_prefix_length(host, resolved)
            if containing is not None:
                return containing
        first_sighting = host not in self._reported_missing_subnet
        self._reported_missing_subnet.add(host)
        if not self.strict.ip_addresses:
            if first_sighting:
                self.job.logger.warning(
                    "IP Fabric reports no subnet for %s, so it is synced as a host route, first seen "
                    "on Interface %s of Device %s. Select IP Addresses under Strict Objects to leave "
                    "it alone instead.",
                    host,
                    iface_name,
                    record.get("hostname"),
                )
            return host_route_length(host)
        if first_sighting and self.job.debug:
            self.job.logger.debug(
                "IP Fabric reports no subnet for %s on Interface %s of Device %s, so the address is not synced",
                host,
                iface_name,
                record.get("hostname"),
            )
        return None

    def load_interface_addresses(self, interface_model, iface, iface_name, device_primary_ips):
        """Add every address IP Fabric reports on the Interface as a model of its own.

        The management address of the Interface this adapter fabricates is not in the address table,
        since it belongs to no interface, so it is taken from the Interface record itself. Every
        other address comes from the table, which is what carries the secondary, virtual and IPv6
        ones the record does not name.
        """
        serial = iface.get("sn")
        reported = list(self.addresses_by_interface.get((serial, iface["intName"]), ()))
        # `loginIpv4` is what a release before 7.3 names it, so both keys are read.
        own_address = iface.get("primaryIp") or iface.get("loginIpv4")
        if own_address and not any(record.get("ip") == own_address for record in reported):
            reported.append({**iface, "ip": own_address})

        # Records that resolve on their own first, so one that inherits can take the length of a
        # subnet already resolved for this Interface.
        reported.sort(key=lambda record: bool(record.get(INHERITS_SUBNET)))
        resolved = {}

        for record in reported:
            host = record.get("ip")
            if not host:
                continue
            length = self.prefix_length_of(record, iface_name, resolved)
            if length is None:
                # Withheld rather than carrying a length this side does not know, so that the
                # Nautobot adapter withholds the same address and the mask it holds is left alone.
                # Written, the address would land under the wrong parent Prefix.
                self.addresses_without_a_subnet.add((iface.get("hostname"), iface_name, host))
                continue
            resolved[host] = length
            try:
                address = self.interface_address(
                    device_name=iface.get("hostname"),
                    interface_name=iface_name,
                    host=host,
                    mask_length=length,
                    is_primary=self.scope.primary_ip and host in device_primary_ips,
                    status="Active",
                )
                self.add(address)
                interface_model.add_child(address)
            except ObjectAlreadyExists:
                # One address reported twice for an Interface, which the two tables can do for a
                # virtual address that is also configured on it.
                logger.warning("Duplicate address %s discovered on Interface %s", host, iface_name)

    @staticmethod
    def link_endpoint(link, side):
        """Return the "local" or "remote" side of a connectivity matrix entry as an endpoint."""
        hostname = link.get(f"{side}Host")
        interface_name = link.get(f"{side}Int")
        if not hostname or not interface_name:
            return None
        if IP_FABRIC_USE_CANONICAL_INTERFACE_NAME:
            interface_name = canonical_interface_name(interface_name)
        return hostname, interface_name

    def endpoints_are_cableable(self, *endpoints):
        """Determine whether a Cable can be synced between the given endpoints.

        Both Interfaces must have been loaded, since a Location filter or a stack member's interfaces
        being reported against its master can leave one end out of scope. Both must also be of a type
        Nautobot will cable, as `Cable.clean()` rejects the virtual and wireless types that IP Fabric
        reports tunnel links over.
        """
        for device_name, interface_name in endpoints:
            try:
                interface = self.get(self.interface, {"name": interface_name, "device_name": device_name})
            except ObjectNotFound:
                if self.job.debug:
                    logger.debug(
                        "Not syncing a Cable for %s:%s as no such Interface was loaded", device_name, interface_name
                    )
                return False
            if interface.type in NONCONNECTABLE_IFACE_TYPES:
                if self.job.debug:
                    logger.debug(
                        "Not syncing a Cable for %s:%s as Nautobot will not cable a %s Interface",
                        device_name,
                        interface_name,
                        interface.type,
                    )
                return False
        return True

    def reported_links(self):
        """Return the links the connectivity matrix describes, as canonically ordered endpoint pairs.

        A set, because the matrix reports each link once from each of its two devices and both
        reports reduce to the same pair.
        """
        links = set()
        for link in self.client.technology.interfaces.connectivity_matrix.all():
            local = self.link_endpoint(link, "local")
            remote = self.link_endpoint(link, "remote")
            if not local or not remote:
                if self.job.debug:
                    logger.debug("Skipping connectivity matrix entry with an incomplete endpoint, %s", link)
                continue
            if local == remote:
                logger.warning(f"Skipping connectivity matrix entry that links an Interface to itself, {link}")
                continue
            links.add(canonical_endpoints(local, remote))
        return links

    def recordable_links(self):
        """Return the reported links Nautobot can record, which is at most one per Interface.

        An Interface terminates at most one Cable in every version this app supports. The versions
        that model breakout cables give one Cable several terminations per side; they do not give an
        Interface several Cables. IP Fabric describes a cloud subnet as a link from each Interface in
        it to the subnet, so one Interface can be reported on many links and only one can be kept.

        Taken in sorted order, so that the link kept is the same one on every run. Choosing
        differently between runs would leave each run deleting the Cable the run before it made.
        """
        taken = set()
        recordable = []
        unrecordable = defaultdict(int)
        for endpoints in sorted(self.reported_links()):
            if not self.endpoints_are_cableable(*endpoints):
                continue
            occupied = [endpoint for endpoint in endpoints if endpoint in taken]
            if occupied:
                for endpoint in occupied:
                    unrecordable[endpoint] += 1
                continue
            taken.update(endpoints)
            recordable.append(endpoints)

        for (device_name, interface_name), count in sorted(unrecordable.items()):
            logger.warning(
                "%s:%s is reported on %d further link(s), which Nautobot cannot record because an "
                "Interface terminates at most one Cable",
                device_name,
                interface_name,
                count,
            )
        return recordable

    def load_cables(self):
        """Add IP Fabric connectivity matrix entries as DiffSync Cable models."""
        for endpoint_a, endpoint_b in self.recordable_links():
            self.add(
                self.cable(
                    termination_a_device=endpoint_a[0],
                    termination_a_name=endpoint_a[1],
                    termination_b_device=endpoint_b[0],
                    termination_b_name=endpoint_b[1],
                    status=DEFAULT_CABLE_STATUS,
                )
            )

    def index_by_interface(self, record) -> None:
        """Index an address record by the Interface it sits on, where it names one.

        A record naming no Interface still decides the length chosen for its address, since that is
        resolved per address across every device reporting it; it simply cannot be attached to an
        Interface here.
        """
        interface_name = record.get("intName")
        if interface_name:
            self.addresses_by_interface[(record.get("sn"), interface_name)].append(record)

    def fhrp_addresses(self):
        """Yield the FHRP virtual addresses IP Fabric reports, as address table records.

        A virtual address is configured on the device and renders into its configuration, so it
        belongs in Nautobot alongside the interface's own addresses. Shaped like a managed address
        record so that one loader handles all three sources.

        The whole table is requested rather than named columns, because the column carrying the
        virtual address differs between releases and IP Fabric does not declare it offline.
        """
        unnamed = 0
        for row in self.client.technology.fhrp.group_members.all():
            host = next((row[key] for key in FHRP_VIRTUAL_ADDRESS_KEYS if row.get(key)), None)
            if not host:
                unnamed += 1
                continue
            # A virtual address has no subnet of its own in this table; it sits in the subnet of the
            # interface holding it, which the managed address table reports.
            yield {
                "sn": row.get("sn"),
                "hostname": row.get("hostname"),
                "intName": row.get("intName"),
                "ip": host,
                INHERITS_SUBNET: True,
            }
        if unnamed:
            self.job.logger.warning(
                "IP Fabric reports %d FHRP group members with no virtual address under any of %s, so "
                "those addresses are not synced. The column may be named differently in this release.",
                unnamed,
                ", ".join(FHRP_VIRTUAL_ADDRESS_KEYS),
            )

    def load_vrfs(self):
        """Add IP Fabric VRFs as DiffSync Vrf models.

        Two tables feed this. The VRF detail table names every VRF and the route distinguisher each
        device carrying it reports, and the L3 VPN route targets table adds the targets. The VRF
        summary table is not read: it names the same VRFs but carries no route distinguisher, so the
        detail table has to be read regardless and answers both questions.
        """
        detail_rows = self.client.technology.routing.vrf_detail.all(columns=["sn", "hostname", "vrf", "rd"])
        target_rows = []
        if self.scope.route_targets:
            target_rows = self.client.technology.mpls.l3vpn_vrf_targets.all(
                columns=["sn", "hostname", "vrf", "rd", "af", "importRT", "exportRT"]
            )
        reconciled = reconcile_vrfs(detail_rows, target_rows)
        self.load_route_targets(reconciled)
        for name, attrs in reconciled.items():
            try:
                self.add(self.network_wide(self.vrf, name=name, status="Active", **attrs))
            except ObjectAlreadyExists:
                logger.warning("Duplicate VRF discovered, %s", name)
        if self.scope.device_vrfs:
            self.load_vrf_device_assignments(detail_rows)
        if self.scope.interface_vrfs:
            self.load_interface_vrfs()

    def load_interface_vrfs(self):
        """Add the VRF each Interface is in as DiffSync InterfaceVrf models.

        Read from IP Fabric's VRF interfaces table rather than from the managed addressing it
        already reads, because an Interface can be in a VRF while carrying no address at all.

        Only Interfaces this run loaded are covered, for the reason the Device assignments are: an
        Interface the sync never saw would be reported as absent from Nautobot on every run.
        """
        rows = self.client.technology.routing.vrf_interfaces.all(columns=["sn", "hostname", "intName", "vrf"])
        for row in rows:
            device_name, interface_name, vrf_name = row.get("hostname"), row.get("intName"), row.get("vrf")
            if not device_name or not interface_name or not vrf_name:
                continue
            if IP_FABRIC_USE_CANONICAL_INTERFACE_NAME:
                interface_name = canonical_interface_name(interface_name)
            try:
                self.get(self.interface, {"name": interface_name, "device_name": device_name})
            except ObjectNotFound:
                if self.job.debug:
                    logger.debug(
                        "Not syncing the VRF of %s:%s, as no such Interface was loaded",
                        device_name,
                        interface_name,
                    )
                continue
            try:
                self.add(
                    self.interface_vrf(
                        adapter=self,
                        device_name=device_name,
                        interface_name=interface_name,
                        vrf_name=vrf_name,
                    )
                )
            except ObjectAlreadyExists:
                logger.warning("Duplicate Interface VRF discovered, %s:%s", device_name, interface_name)

    def load_vrf_device_assignments(self, detail_rows):
        """Add the Devices each VRF is configured on as DiffSync VrfDeviceAssignment models.

        Only Devices this run loaded are assigned. A Location filter, or a stack member whose VRFs
        are reported against its master, can leave a hostname the VRF detail table names outside the
        run, and an assignment to a Device the sync never saw would be reported as absent from
        Nautobot on every run and never written.
        """
        unknown_devices = set()
        assigned = 0
        for vrf_name, device_name in sorted(
            {(row.get("vrf"), row.get("hostname")) for row in detail_rows if row.get("vrf") and row.get("hostname")}
        ):
            try:
                self.get(self.device, {"name": device_name})
            except ObjectNotFound:
                unknown_devices.add(device_name)
                continue
            try:
                self.add(self.vrf_device_assignment(adapter=self, vrf_name=vrf_name, device_name=device_name))
                assigned += 1
            except ObjectAlreadyExists:
                logger.warning("Duplicate VRF assignment discovered, %s on %s", vrf_name, device_name)

        if not unknown_devices:
            return
        if assigned:
            # Some matched, so the rest are the Devices this run does not cover, which a Location
            # filter or Sync Tagged Only is expected to leave out.
            if self.job.debug:
                logger.debug(
                    "Not syncing the VRFs IP Fabric reports on %s, as no such Devices were loaded",
                    ", ".join(sorted(unknown_devices)),
                )
            return
        # Nothing matched at all, which is not a narrowed run but a disagreement about names: the
        # VRF table reports a hostname the Device inventory does not. Reported rather than left to
        # look like a network with no VRFs on any device.
        # Through the job rather than the module logger, since this is the only thing that explains
        # an otherwise silent result and it has to reach the Job Result log.
        self.job.logger.warning(
            "IP Fabric reports VRFs on %d device(s), none of which match a Device this run loaded, so "
            "no VRF will be assigned to any Device. The first few are %s",
            len(unknown_devices),
            ", ".join(sorted(unknown_devices)[:5]),
        )

    def load_route_targets(self, reconciled):
        """Add the Route Targets the reconciled VRFs name as DiffSync RouteTarget models.

        Taken from what was reconciled rather than from the table directly, so that a target only
        one device of a VRF reported is not created: that VRF records no targets at all, and a
        Route Target nothing points at would be left behind on every run.
        """
        named = set()
        for attrs in reconciled.values():
            named.update(attrs["import_targets"])
            named.update(attrs["export_targets"])
        for name in sorted(named):
            self.add(self.network_wide(self.route_target, name=name))

    def load_data(self):
        """Load shared data from IP Fabric.

        Each table is fetched only when something in scope reads it. These are the largest requests
        the job makes, so a narrowed sync should not pay to download and index a table it will never
        look at.
        """
        reported_addresses = []
        stacks, interfaces = defaultdict(list), defaultdict(list)
        vlans_by_location = defaultdict(list)

        if self.scope.vlans:
            for vlan in self.client.fetch_all("tables/vlan/site-summary"):
                vlans_by_location[vlan["siteName"]].append(vlan)

        if self.scope.ip_addresses:
            # No filter on `type`: a secondary address is configured on the device and renders into
            # its configuration, so it belongs in Nautobot alongside the primary one.
            # Only the columns the sync reads: these are the largest requests the job makes, and
            # every row of two unfiltered tables carries each one asked for.
            ip_columns = ["sn", "intName", "net", "ip"]
            for table in (
                self.client.technology.addressing.managed_ip_ipv4,
                self.client.technology.addressing.managed_ip_ipv6,
            ):
                for ip_address in table.all(columns=ip_columns):
                    reported_addresses.append(ip_address)
                    self.index_by_interface(ip_address)
            for virtual in self.fhrp_addresses():
                self.index_by_interface(virtual)
            self.prefix_length_by_address = prefix_lengths_by_address(reported_addresses)

        # Get all interfaces for devices
        if self.scope.interfaces:
            for interface in self.client.inventory.interfaces.all():
                interfaces[interface["sn"]].append(interface)

        # Get all stacks for devices. Stack membership is Device data, so it is read whatever else is
        # in scope.
        for stack in self.client.technology.platforms.stacks_members.all(
            columns=["master", "member", "memberSn", "pn", "sn"]
        ):
            stacks[stack["sn"]].append(stack)
        return vlans_by_location, stacks, interfaces

    def load(self):  # pylint: disable=too-many-locals,too-many-statements
        """Load data from IP Fabric."""
        self.load_sites()
        vlans_by_location, stacks, interfaces = self.load_data()

        for location in self.get_all(self.location):
            if location.name is None:
                continue
            location_vlans = vlans_by_location.get(location.name, [])
            for vlan_record in location_vlans:
                vlan_name = vlan_record.get("vlanName")
                vlan_id = vlan_record["vlanId"]
                vlan_desc = vlan_record.get("dscr")
                if not vlan_id or not 1 <= vlan_id <= 4094:
                    logger.warning(f"Not syncing VLAN, NAME: {vlan_name} due to invalid VLAN ID: {vlan_id}.")
                    continue
                description = vlan_desc if vlan_desc else f"VLAN ID: {vlan_id}"
                vlan_label = vlan_name if vlan_name else f"{vlan_record['siteName']}:{vlan_id}"
                if len(vlan_label) > name_max_length:
                    logger.warning(
                        f"Truncating the name of VLAN {vlan_id} at {vlan_record['siteName']} to the "
                        f"{name_max_length} characters Nautobot holds: {vlan_label}"
                    )
                    vlan_label = vlan_label[:name_max_length]
                try:
                    vlan = self.vlan(
                        name=vlan_label,
                        location=vlan_record["siteName"],
                        vid=vlan_id,
                        status="Active",
                        description=description,
                    )
                    self.add(vlan)
                    location.add_child(vlan)
                except ObjectAlreadyExists:
                    logger.warning(f"Duplicate VLAN discovered at {vlan_record['siteName']}: VLAN ID {vlan_id}")
            for device in self.client.devices.by_site.get(location.name, []):
                base_args = {
                    "diffsync": self,
                    "location_name": device.site,
                    "model": device.model or f"Default-{device.vendor}",
                    "vendor": device.vendor.capitalize(),
                    "role": device.dev_type or DEFAULT_DEVICE_ROLE if SYNC_IPF_DEV_TYPE_TO_ROLE else None,
                    "status": DEFAULT_DEVICE_STATUS,
                    "platform": device.family,
                }
                if device.sn not in stacks:
                    serial_number = device.sn
                    args = base_args.copy()
                    args["name"] = device.hostname
                    args["serial_number"] = serial_number if len(serial_number) < device_serial_max_length else ""
                    member_devices = [args]
                else:
                    # member with the lowest member number will be considered master,
                    # and vc_priority and vc_position will both be derived from the member field,
                    # as the role field will depend on operational state and not config,
                    # and this will cause uneccessary diffs.
                    stack_members = stacks[device.sn]
                    stack_members.sort(key=lambda x: x["member"])
                    member_devices = []
                    for index, member in enumerate(stack_members):
                        # using `or` syntax in case memberSn is defined as None
                        member_sn = member.get("memberSn") or ""
                        args = base_args.copy()
                        if pn := member.get("pn"):
                            args["model"] = pn
                        args.update(
                            {
                                "serial_number": member_sn if len(member_sn) < device_serial_max_length else "",
                                "name": f"{device.hostname}-member{member.get('member')}",
                                "vc_name": device.hostname,
                                "vc_master": False,
                                "vc_priority": member.get("member"),
                                "vc_position": member.get("member"),
                            }
                        )
                        if index == 0:
                            args.update(
                                {
                                    "name": device.hostname,
                                    "vc_master": True,
                                }
                            )
                        member_devices.append(args)

                for index, dev in enumerate(member_devices):
                    if not dev["serial_number"]:
                        logger.warning(
                            f"Serial Number will not be recorded for {dev['name']} due to character limit exceeds {device_serial_max_length}"
                        )
                    try:
                        device_model = self.device(**dev)
                        self.add(device_model)
                        location.add_child(device_model)
                        if index == 0 and self.scope.interfaces:
                            self.load_device_interfaces(
                                device_model,
                                interfaces.get(device.sn, []),
                                primary_addresses_of(device),
                            )
                    except ObjectAlreadyExists:
                        logger.warning(f"Duplicate Device discovered, {device.model_dump()}")

        if self.scope.cables:
            self.load_cables()

        if self.scope.vrfs:
            self.load_vrfs()

        # Read only while loading, and it holds a record per address, so it is not carried into the
        # diff and sync phases where both adapters' models are already resident.
        self.addresses_by_interface.clear()

        if self.addresses_without_a_subnet:
            self.job.logger.warning(
                "Not syncing %d Interface addresses because IP Fabric reports no usable subnet for "
                "them. Enable debug logging to see which addresses those were.",
                len(self.addresses_without_a_subnet),
            )


def primary_addresses_of(device):
    """Return the addresses IP Fabric logs in to the Device on, as host strings.

    These are the addresses Nautobot records as the Device's primary ones. `loginIpv4` and
    `loginIpv6` are reported separately, so a dual stack Device names one of each and Nautobot can
    carry a `primary_ip4` and a `primary_ip6` rather than only whichever came first. `loginIp` is the
    older single column, read where the newer two are absent.

    Each is expected to be among the addresses the Interfaces already reported, which is where its
    prefix length comes from; marking one primary does not resolve an address of its own. The
    exception is an address reached through NAT, which belongs to no interface at all and is what
    `pseudo_management_interface` exists for.
    """
    hosts = {str(address) for address in (device.login_ipv4, device.login_ipv6) if address}
    if hosts:
        return hosts
    return {str(device.login_ip.ip)} if device.login_ip else set()


def pseudo_management_interface(hostname, device_interfaces, device_primary_ips):
    """Return a dict for a non-existing interface for a NAT management address.

    Fabricated only for a primary address no Interface reports, since every other one is already
    carried by the Interface holding it. Where more than one is unreported the first is carried, as
    the record describes a single address; a Device reached through NAT on both IP versions is not
    something IP Fabric has been seen to report.
    """
    reported = {iface.get("primaryIp") for iface in device_interfaces}
    unreported = sorted(device_primary_ips - reported)
    if not unreported:
        return None
    device_primary_ip = unreported[0]
    return {
        "hostname": hostname,
        "intName": PSEUDO_MANAGEMENT_INTERFACE_NAME,
        "dscr": "pseudo interface for NAT IP address",
        "primaryIp": device_primary_ip,
        # Declared here rather than recognised by name in `prefix_length_of`. A NAT address belongs
        # to no interface, so the managed address table reports no subnet for it and a host route is
        # the whole of it: the value, not a fallback. Known for certain where the dict is built.
        "net": f"{device_primary_ip}/{host_route_length(device_primary_ip)}",
        "type": "virtual",
        "mgmt_only": True,
    }


def containing_prefix_length(host, resolved):
    """Return the length of the subnet among `resolved` that contains `host`, or None.

    An FHRP virtual address has no subnet of its own in the FHRP tables. It sits in the subnet of the
    interface holding it, so the length is taken from whichever of that Interface's own addresses
    covers it. The narrowest is chosen, matching how Nautobot parents an address.
    """
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return None
    lengths = []
    for sibling, length in resolved.items():
        try:
            network = ipaddress.ip_network(f"{sibling}/{length}", strict=False)
        except ValueError:
            continue
        if address in network:
            lengths.append(length)
    return max(lengths) if lengths else None


def reported_prefix_length(net):
    """Return the prefix length of a subnet IP Fabric reported, or None if it did not report one.

    A value that does not parse is not a subnet an address can be described with. The caller reports
    and skips it rather than raising: one unusable row would otherwise end the job while it was still
    reading, losing every address that was fine.

    Either IP version is accepted. The length is what the sync records, so a v6 prefix needs no
    conversion into a v4 netmask to be usable.

    Whether the subnet contains the address it was reported for is not checked here. That is a
    different kind of wrong data, and one this sync has no better answer for than the mask itself.
    """
    try:
        return ipaddress.ip_network(net, strict=False).prefixlen
    except ValueError:
        return None


def prefix_lengths_by_address(reported_addresses):
    """Return one prefix length per address, the narrowest of those reported for it.

    IP Fabric indexes addressing by serial number and so describes a subnet per device. An address
    on two devices can therefore be reported in two subnets, while Nautobot holds one mask per
    address, so two Interfaces sharing an address cannot each carry the mask reported for them. One
    mask is chosen here, for every Interface holding that address, so that the two sides agree.

    The narrowest report is the one chosen, because it agrees with the address's parent: Nautobot
    parents an address to the most specific Prefix containing it. A fixed rule rather than the order
    IP Fabric answers in, which is not guaranteed.

    A length rather than a netmask, so that the same choice serves an IPv6 address as an IPv4 one.

    Every record is folded in, whichever device reported it. Grouping them per device first would
    hide one device reporting the same address in two subnets, which is as much a disagreement worth
    naming as two devices doing so.
    """
    lengths = {}
    contested = set()
    unusable = set()
    for record in reported_addresses:
        address = record.get("ip")
        if not address or not record.get("net"):
            continue
        length = reported_prefix_length(record["net"])
        if length is None:
            unusable.add(record["net"])
            continue
        if address in lengths and lengths[address] != length:
            contested.add(address)
        lengths[address] = max(length, lengths.get(address, 0))
    if unusable:
        # Per distinct value rather than per row: the table holds a record per device, so a column
        # the appliance fills wrongly is one problem reported once, not once per device.
        logger.warning(
            "IP Fabric reports %d subnet values that are not usable subnets: %s",
            len(unusable),
            ", ".join(repr(net) for net in sorted(unusable, key=str)),
        )
    for address in sorted(contested):
        logger.warning(
            "IP Fabric reports %s in more than one subnet, so its Interfaces cannot each carry "
            "the mask reported for them; using the narrowest, /%d",
            address,
            lengths[address],
        )
    return lengths


def agreed_targets(by_device):
    """Return the one set of route targets every device reported, and whether they disagreed.

    The targets come back empty where the devices disagreed, since there is then no one set to
    record for the VRF.
    """
    reported = {frozenset(targets) for targets in by_device.values()}
    if len(reported) > 1:
        return [], True
    return sorted(next(iter(reported), frozenset())), False


def reconcile_vrfs(detail_rows, target_rows):
    """Return the network wide value of each VRF's attributes, keyed by VRF name.

    IP Fabric reports a route distinguisher per device and route targets per device and address
    family, while Nautobot holds one of each per VRF. Where every device carrying a VRF reports the
    same value, that value is the VRF's. Where they disagree the network is misconfigured, and the
    disagreement is recorded rather than one report being picked arbitrarily: a VRF silently
    carrying one device's route distinguisher is worse than one carrying none and saying why.

    The two are reconciled independently, so a VRF whose devices agree on its route distinguisher
    but not on its route targets still records the route distinguisher.

    Address families are combined rather than reconciled against each other, because Nautobot holds
    one set of targets per VRF: a device importing one target for IPv4 and another for IPv6 imports
    both.

    The detail table names every VRF and its route distinguisher on each device carrying it, and the
    L3 VPN route targets table adds the targets. The latter is empty where route targets are out of
    scope, which leaves every VRF reporting none of them.
    """
    route_distinguishers = defaultdict(set)
    imports, exports = defaultdict(dict), defaultdict(dict)
    names = set()

    for row in chain(detail_rows, target_rows):
        if name := row.get("vrf"):
            names.add(name)
            if rd := row.get("rd"):
                route_distinguishers[name].add(rd)

    for row in target_rows:
        name = row.get("vrf")
        if not name:
            continue
        # Keyed by serial number rather than hostname, since two sites may hold a device of one name
        # and the reports of each are their own.
        device = row.get("sn") or row.get("hostname")
        imports[name].setdefault(device, set()).update(row.get("importRT") or ())
        exports[name].setdefault(device, set()).update(row.get("exportRT") or ())

    reconciled = {}
    for name in sorted(names):
        conflicts = []
        reported_rds = route_distinguishers.get(name, set())
        if len(reported_rds) > 1:
            conflicts.append("route distinguisher")
            route_distinguisher = None
        else:
            route_distinguisher = next(iter(reported_rds), None)

        import_targets, imports_disagree = agreed_targets(imports.get(name, {}))
        export_targets, exports_disagree = agreed_targets(exports.get(name, {}))
        if imports_disagree or exports_disagree:
            conflicts.append("route targets")

        conflict = f"IP Fabric's devices disagree about this VRF's {' and '.join(conflicts)}" if conflicts else ""
        if conflict:
            logger.warning("%s, so none is recorded for the VRF named %s", conflict, name)
        reconciled[name] = {
            "rd": route_distinguisher,
            "import_targets": import_targets,
            "export_targets": export_targets,
            "conflict": conflict,
        }
    return reconciled
