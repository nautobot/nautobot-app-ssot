"""General utils for IPFabric."""

import ipaddress
import re
import threading
from collections import defaultdict
from functools import wraps
from itertools import takewhile
from typing import Optional

VIRTUAL = "virtual"
BRIDGE = "bridge"
LAG = "lag"

GBIC = "gbic"
SFP = "sfp"
LR = "lr"
SR = "sr"
SX = "sx"
LX = "lx"
XFP = "xfp"
X2 = "x2"
XENPAK = "xenpak"
QSFP = "qsfp"

HUNDRED_MEG = "100m"
HUNDRED_MEG_BASE = "100base"
GIG = "1g"
GIG_BASE = "1000base"
RJ45 = "rj45"
TWO_AND_HALF_GIG_BASE = "2.5gbase"
FIVE_GIG_BASE = "5gbase"
TEN_GIG = "10g"
TEN_GIG_BASE_T = "10gbaset"
TWENTY_FIVE_GIG = "25g"
FORTY_GIG = "40g"
FIFTY_GIG = "50g"
HUNDRED_GIG = "100g"
TWO_HUNDRED_GIG = "200g"
FOUR_HUNDRED_GIG = "400g"
EIGHT_HUNDRED_GIG = "800g"


INTERFACE_NAME_TYPES = (
    (r"po(rt-?channel)?\d", "lag"),
    (r"vl(an)?\d", "virtual"),
    (r"lo(opback)?\d", "virtual"),
    (r"tu(nnel)?\d", "virtual"),
    (r"vx(lan)?\d", "virtual"),
    (r"fa(stethernet)?\d", "100base-tx"),
    (r"gi(gabitethernet)?\d", "1000base-t"),
    (r"te(ngigabitethernet)?\d", "10gbase-x-sfpp"),
    (r"twentyfivegigabitethernet\d", "25gbase-x-sfp28"),
    (r"fo(rtygigabitethernet)?\d", "40gbase-x-qsfpp"),
    (r"fi(ftygigabitethernet)?\d", "50gbase-x-sfp56"),
    (r"hu(ndredgigabitethernet)?\d", "100gbase-x-qsfp28"),
    (r"twohundredgigabitethernet\d", "200gbase-x-qsfp56"),
)


def convert_media_type(media_type: str, interface_name: str) -> Optional[str]:
    """Return the Nautobot Interface type for a reported media type, or None if nothing resolves.

    Read from the media type IP Fabric reports, and failing that from the Interface's name, which is
    the only other thing that names what a port is. None where neither answers: a type standing for
    "not resolved" would be indistinguishable from one genuinely resolved to that value, and would
    overwrite whatever Nautobot holds with a guess on every run.

    Args:
        media_type: The media type of an interface (i.e. SFP-10GBase).
        interface_name: The name of the interface with `media_type`.

    Returns:
        The corresponding representation of `media_type` in Nautobot, or None.
    """
    return type_of_media(media_type) or type_of_interface_name(interface_name)


def lag_member_names(reported: str) -> list:
    """Return the Interface names a port channel's member column lists.

    IP Fabric reports members as one string, each name followed by its state in brackets:
    `Et35(DOWN), Et36(DOWN)`. The state is taken off the end rather than the name read from the
    front, because a name may carry brackets of its own, and only the last pair is the state.
    """
    members = []
    for part in (reported or "").split(","):
        name = part.strip().rsplit("(", 1)[0].strip()
        if name:
            members.append(name)
    return members


def parent_interface_name(interface_name: str) -> Optional[str]:
    """Return the Interface a subinterface hangs off, or None where the name names no parent.

    A dot separates a physical port from the logical interface configured on it, on every platform
    this sync has met: `GigabitEthernet0/1.100` on IOS, `ge-0/0/0.0` on Junos. The part before the
    last dot is the port, which is what Nautobot wants `parent_interface` pointed at.

    The name is the only evidence available. IP Fabric's interface inventory reports no relation
    between a subinterface and its port, so the caller confirms the parent is a port the same Device
    reported before using it.
    """
    port, separator, unit = interface_name.rpartition(".")
    if not separator or not port or not unit:
        return None
    return port


def interface_name_kind(interface_name: str) -> str:
    """Return the leading letters of an Interface's name, which is what names the kind of port.

    `Ethernet1/1` and `Ethernet49` are one kind reported twice, so counting Interfaces by this rather
    than by name says which pattern is missing from `INTERFACE_NAME_TYPES` instead of listing every
    port that matched none of them.
    """
    return "".join(takewhile(str.isalpha, interface_name))


def type_of_interface_name(interface_name: str) -> Optional[str]:
    """Return the Nautobot Interface type an Interface's name implies, or None if none does."""
    interface_name = interface_name.lower()
    for regex, iface_type in INTERFACE_NAME_TYPES:
        if re.match(regex, interface_name):
            return iface_type
    return None


def type_of_media(  # pylint: disable=too-many-return-statements,too-many-branches,too-many-statements
    media_type: str,
) -> Optional[str]:
    """Return the Nautobot Interface type the reported media type names, or None if none does."""
    if media_type:
        media_type = media_type.lower().replace("-", "")
        if VIRTUAL in media_type:
            return VIRTUAL
        if BRIDGE in media_type:
            return BRIDGE
        if LAG in media_type:
            return LAG

        if TEN_GIG_BASE_T in media_type:
            return "10gbase-t"

        # Going from 10Gig to lower bandwidths to allow media that supports multiple
        # bandwidths to use highest supported bandwidth
        if TEN_GIG in media_type:
            nautobot_media_type = "10gbase-x-"
            if XFP in media_type:
                nautobot_media_type += "xfp"
            elif X2 in media_type:
                nautobot_media_type += "x2"
            elif XENPAK in media_type:
                nautobot_media_type += "xenpak"
            else:
                nautobot_media_type += "sfpp"
            return nautobot_media_type

        # Flipping order of 5gig and 2.5g as both use the string 5gbase
        if TWO_AND_HALF_GIG_BASE in media_type:
            return "2.5gbase-t"

        if FIVE_GIG_BASE in media_type:
            return "5gbase-t"

        if GIG_BASE in media_type or RJ45 in media_type or GIG in media_type:
            nautobot_media_type = "1000base-"
            if GBIC in media_type:
                nautobot_media_type += "x-gbic"
            elif SFP in media_type or SR in media_type or LR in media_type or SX in media_type or LX in media_type:
                nautobot_media_type += "x-sfp"
            else:
                nautobot_media_type += "t"
            return nautobot_media_type

        if HUNDRED_MEG_BASE in media_type or HUNDRED_MEG in media_type:
            return "100base-tx"

        if TWENTY_FIVE_GIG in media_type:
            return "25gbase-x-sfp28"

        if FORTY_GIG in media_type:
            return "40gbase-x-qsfpp"

        if FIFTY_GIG in media_type:
            return "50gbase-x-sfp56"

        if HUNDRED_GIG in media_type:
            nautobot_media_type = "100gbase-x-"
            if QSFP in media_type:
                nautobot_media_type += "qsfp28"
            else:
                nautobot_media_type += "cfp"
            return nautobot_media_type

        if TWO_HUNDRED_GIG in media_type:
            nautobot_media_type = "200gbase-x-"
            if QSFP in media_type:
                nautobot_media_type += "qsfp56"
            else:
                nautobot_media_type += "cfp2"
            return nautobot_media_type

        if FOUR_HUNDRED_GIG in media_type:
            nautobot_media_type = "400gbase-x-"
            if QSFP in media_type:
                nautobot_media_type += "qsfp112"
            else:
                nautobot_media_type += "osfp"
            return nautobot_media_type

        if EIGHT_HUNDRED_GIG in media_type:
            nautobot_media_type = "800gbase-x-"
            if QSFP in media_type:
                nautobot_media_type += "qsfpdd"
            else:
                nautobot_media_type += "osfp"
            return nautobot_media_type
    return None


class job_scoped_cache:  # pylint: disable=invalid-name
    """Drop-in replacement for @lru_cache, safe for concurrent job runs.

    Each thread/process gets its own isolated cache store.

    Usage:
        @job_scoped_cache
        def get_status(name):
            return Status.objects.get(name=name)

        @job_scoped_cache(group="facility_circuits")
        def get_service_type(code):
            return ServiceType.objects.filter(service_type_code=code).first()

        # Keep only the most recent entries, for results too large to hold one of per key:
        @job_scoped_cache(maxsize=2)
        def get_interfaces(device):
            return list(device.interfaces.all())

        # Clear only one group:
        job_scoped_cache.clear_group("facility_circuits")

        # Clear everything (backward-compatible):
        job_scoped_cache.clear_all()
    """

    _all_instances = []
    _groups = defaultdict(list)
    _local = threading.local()

    def __init__(self, fn=None, *, group=None, maxsize=None):
        """Initialize the cache.

        Args:
            fn: The function to cache, when used without arguments.
            group: Name of a group, so this cache can be cleared apart from the others.
            maxsize: How many results to keep, oldest evicted first. Unbounded by default, which
                suits small results keyed by a name; set it where one result is large enough that
                keeping one per key over a whole run would cost real memory.
        """
        self._group = group
        self._maxsize = maxsize
        if fn is not None:
            # Called as @job_scoped_cache (no arguments)
            self._init_fn(fn)

    def _init_fn(self, fn):
        """Initialize function."""
        self._fn = fn
        self._id = id(self)
        wraps(fn)(self)
        job_scoped_cache._all_instances.append(self)
        if self._group:
            job_scoped_cache._groups[self._group].append(self)

    def __call__(self, *args, **kwargs):
        """Handle call to function, checks cache, calls function if missing and caches result."""
        if not hasattr(self, "_fn"):
            # Called as @job_scoped_cache(group="..."), so this receives the function
            self._init_fn(args[0])
            return self
        state = self._get_state()
        key = (args, tuple(sorted(kwargs.items())))
        if key in state["store"]:
            state["hits"] += 1
            return state["store"][key]
        state["misses"] += 1
        result = self._fn(*args, **kwargs)
        store = state["store"]
        store[key] = result
        if self._maxsize is not None and len(store) > self._maxsize:
            # One entry is added per miss, so the bound is exceeded by at most one. Insertion
            # ordered, so the first key is the oldest.
            del store[next(iter(store))]
        return result

    def _get_state(self):
        """Return state of cache."""
        stores = getattr(job_scoped_cache._local, "stores", None)
        if stores is None:
            stores = {}
            job_scoped_cache._local.stores = stores
        if self._id not in stores:
            stores[self._id] = {"store": {}, "hits": 0, "misses": 0}
        return stores[self._id]

    def cache_clear(self):
        """Clear all cache info for an instance."""
        state = self._get_state()
        state["store"].clear()
        state["hits"] = 0
        state["misses"] = 0

    def cache_info(self):
        """Returns cache info."""
        from collections import namedtuple  # pylint: disable=import-outside-toplevel

        state = self._get_state()
        _CacheInfo = namedtuple("CacheInfo", ["hits", "misses", "maxsize", "currsize"])
        return _CacheInfo(state["hits"], state["misses"], self._maxsize, len(state["store"]))

    @classmethod
    def clear_group(cls, group):
        """Clear caches for all functions registered under a specific group."""
        for instance in cls._groups.get(group, []):
            instance.cache_clear()

    @classmethod
    def clear_all(cls):
        """Clears all cache info on all instances and groups."""
        for instance in cls._all_instances:
            instance.cache_clear()


def parse_vlan_ranges(value):
    """Return the VLAN IDs a switchport range names, as a sorted list.

    IP Fabric reports a trunk's VLANs the way the device's configuration does, as a comma separated
    mix of single IDs and inclusive ranges: `110-119,999`. A part that is not a number or a range,
    or a range that counts backwards, is skipped rather than guessed at.
    """
    vlan_ids = set()
    for part in str(value or "").split(","):
        part = part.strip()
        if not part:
            continue
        bounds = part.split("-")
        try:
            numbers = [int(bound) for bound in bounds]
        except ValueError:
            continue
        if len(numbers) == 1:
            vlan_ids.add(numbers[0])
        elif len(numbers) == 2 and numbers[0] <= numbers[1]:
            vlan_ids.update(range(numbers[0], numbers[1] + 1))
    return sorted(vlan_id for vlan_id in vlan_ids if 1 <= vlan_id <= 4094)


def host_route_length(host):
    """Return the prefix length of the route covering only the given address."""
    try:
        return ipaddress.ip_address(host).max_prefixlen
    except ValueError:
        return 32
