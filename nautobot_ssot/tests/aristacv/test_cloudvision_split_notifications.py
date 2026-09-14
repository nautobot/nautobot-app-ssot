"""Generic regression net for the CloudVision split-notification bug class.

CloudVision's gRPC Connector streams an object's attributes across an arbitrary number of
notifications and batches. Which attribute lands in which frame is not part of the contract, and a
frame carrying state routinely omits the object's identity key (`intfId`/`name`). The only
reliable identity is the wildcard element of the gRPC path, `notif["path_elements"]`.

Every query helper in `cloudvision.py` must therefore be a function of the *merged* per-object
attribute set and never of how CloudVision happened to frame it. This module asserts exactly that:
for each helper it computes a baseline from a canonical (one notification per object) rendering of a
real captured fixture, then re-frames that same data every way CloudVision is allowed to and asserts
the result never changes.

This bug has been fixed one function at a time in #1188, #1267 and #1308, and was still open as
#1338, because each fix shipped with a hand-written test covering only the function named in the
ticket. `test_every_wildcard_function_is_registered` is what stops that pattern: a new helper that
uses `Wildcard()` without an entry in `QUERY_HELPERS` fails the build.
"""

import ast
import inspect
from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import MagicMock, patch

from nautobot.apps.testing import TestCase

from nautobot_ssot.integrations.aristacv.utils import cloudvision
from nautobot_ssot.tests.aristacv.fixtures import fixtures

DEVICE_ID = "JPE12345678"

# Keys CloudVision may or may not include in any given frame. A helper that needs one of these to
# identify an object is broken by definition; the path element is the identity.
IDENTITY_KEYS = ("intfId", "name")


def _object_key(notification):
    """Identity of the object a notification describes: its full gRPC path."""
    return tuple(notification["path_elements"])


def _notification(path_elements, updates):
    return {"path_elements": list(path_elements), "updates": deepcopy(updates)}


def canonical(batches):
    """Collapse batches so each object has exactly one notification holding all its attributes.

    This is the framing the original hand-written fixtures assume, and the framing every helper is
    expected to agree with no matter how the same data actually arrives.
    """
    merged = {}
    for batch in batches:
        for notification in batch["notifications"]:
            key = _object_key(notification)
            if key not in merged:
                merged[key] = _notification(notification["path_elements"], {})
            merged[key]["updates"].update(deepcopy(notification["updates"]))
    return [{"notifications": list(merged.values())}]


def explode_updates(batches):
    """Split every notification into one notification per update key."""
    exploded = []
    for batch in batches:
        notifications = []
        for notification in batch["notifications"]:
            if not notification["updates"]:
                notifications.append(_notification(notification["path_elements"], {}))
                continue
            for key, value in notification["updates"].items():
                notifications.append(_notification(notification["path_elements"], {key: value}))
        exploded.append({"notifications": notifications})
    return exploded


def reverse_frames(batches):
    """Reverse the order of every notification in the query, across batch boundaries.

    CloudVision does not promise an order. A helper that resolves a priority (for example eeprom
    media type over local media type) frame by frame, instead of once over the merged attributes,
    returns a different answer here.
    """
    notifications = [notification for batch in batches for notification in batch["notifications"]]
    return [
        {"notifications": [_notification(n["path_elements"], n["updates"]) for n in reversed(notifications)]},
    ]


def strip_identity_keys(batches):
    """Drop `intfId`/`name` from every update payload."""
    stripped = []
    for batch in batches:
        notifications = [
            _notification(
                notification["path_elements"],
                {key: value for key, value in notification["updates"].items() if key not in IDENTITY_KEYS},
            )
            for notification in batch["notifications"]
        ]
        stripped.append({"notifications": notifications})
    return stripped


def one_notification_per_batch(batches):
    """Give every notification its own batch, catching accumulators scoped inside the batch loop."""
    return [
        {"notifications": [_notification(notification["path_elements"], notification["updates"])]}
        for batch in batches
        for notification in batch["notifications"]
    ]


def single_batch(batches):
    """Coalesce every notification into one batch, catching per-batch emit assumptions."""
    return [
        {
            "notifications": [
                _notification(notification["path_elements"], notification["updates"])
                for batch in batches
                for notification in batch["notifications"]
            ]
        }
    ]


def interleave_objects(batches):
    """Round-robin notifications across objects so no object's frames are contiguous."""
    by_object = {}
    for batch in batches:
        for notification in batch["notifications"]:
            by_object.setdefault(_object_key(notification), []).append(notification)
    interleaved = []
    queues = list(by_object.values())
    while any(queues):
        for queue in queues:
            if queue:
                notification = queue.pop(0)
                interleaved.append(_notification(notification["path_elements"], notification["updates"]))
    return [{"notifications": interleaved}]


def compose(*transforms):
    """Left-to-right composition of framing transforms."""

    def _composed(batches):
        for transform in transforms:
            batches = transform(batches)
        return batches

    return _composed


# Every re-framing CloudVision is permitted to produce. A correct helper returns the same result for
# all of them, and the same result as for the canonical framing used as the baseline.
TRANSFORMS = (
    ("exploded", explode_updates),
    ("exploded_reversed", compose(explode_updates, reverse_frames)),
    ("exploded_without_identity_keys", compose(explode_updates, strip_identity_keys)),
    ("one_notification_per_batch", compose(explode_updates, one_notification_per_batch)),
    ("single_coalesced_batch", compose(explode_updates, single_batch)),
    ("interleaved_objects", compose(explode_updates, interleave_objects, one_notification_per_batch)),
    (
        "worst_case",
        compose(
            explode_updates,
            reverse_frames,
            strip_identity_keys,
            interleave_objects,
            one_notification_per_batch,
        ),
    ),
)


class QueryHelper:
    """One registry entry: a query helper plus the captured payloads its queries return."""

    def __init__(self, function, queries, kwargs=None, patches=None):
        """Register a helper.

        Args:
            function (callable): The `cloudvision` helper under test.
            queries (list): One list of batches per `client.get` call the helper makes, in order.
            kwargs (dict): Extra keyword arguments beyond `client` and `dId`.
            patches (dict): Attributes to patch on the `cloudvision` module for the call.
        """
        self.function = function
        self.queries = queries
        self.kwargs = kwargs or {}
        self.patches = patches or {}

    @property
    def name(self):
        """Name of the helper under test, matched against the wildcard functions in the module."""
        return self.function.__name__

    def call(self, transform):
        """Run the helper against the registered payloads re-framed by `transform`."""
        client = MagicMock()
        client.get = MagicMock(side_effect=[transform(deepcopy(query)) for query in self.queries])
        with ExitStack() as stack:
            for attribute, replacement in self.patches.items():
                stack.enter_context(patch.object(cloudvision, attribute, replacement))
            return self.function(client=client, dId=DEVICE_ID, **self.kwargs)


# The eeprom and local-media captures describe the same interface, so concatenating them is a real
# two-frame payload where the correct media type (eeprom) must win regardless of frame order.
TRANSCEIVER_QUERY = fixtures.TRANSCEIVER_EEPROM_QUERY + fixtures.TRANSCEIVER_LOCAL_QUERY

QUERY_HELPERS = (
    QueryHelper(
        cloudvision.get_interfaces_chassis,
        queries=[fixtures.CHASSIS_INTF_QUERY],
        patches={"get_query": MagicMock(return_value={"Linecard1": None})},
    ),
    QueryHelper(cloudvision.get_interfaces_fixed, queries=[fixtures.FIXED_INTF_QUERY]),
    QueryHelper(
        cloudvision.get_interfaces_port_channel,
        queries=[fixtures.PORT_CHANNEL_STATUS_QUERY, fixtures.PORT_CHANNEL_CONFIG_QUERY],
    ),
    QueryHelper(cloudvision.get_port_channel_members, queries=[fixtures.LAG_INPUT_PHYINTF_QUERY]),
    QueryHelper(cloudvision.get_all_interface_transceivers, queries=[TRANSCEIVER_QUERY]),
    QueryHelper(
        cloudvision.get_interface_transceiver,
        queries=[TRANSCEIVER_QUERY],
        kwargs={"interface": "Ethernet1"},
    ),
    QueryHelper(cloudvision.get_all_interface_modes, queries=[fixtures.TRUNK_INTF_MODE_QUERY]),
    QueryHelper(
        cloudvision.get_all_interface_descriptions,
        queries=[fixtures.INTF_DESCRIPTION_QUERY, fixtures.ROUTED_INTF_DESCRIPTION_QUERY],
    ),
    QueryHelper(
        cloudvision.get_routed_interface_description,
        queries=[fixtures.ROUTED_INTF_DESCRIPTION_QUERY],
        kwargs={"interface": "Loopback0"},
    ),
    QueryHelper(cloudvision.get_ip_interfaces, queries=[fixtures.IP_INTF_QUERY]),
)


def _sort_key(item):
    return repr(sorted(item.items())) if isinstance(item, dict) else repr(item)


def normalize(result):
    """Make results order-insensitive; re-framing may legitimately reorder a returned list."""
    if isinstance(result, list):
        return sorted((normalize(item) for item in result), key=_sort_key)
    return result


def wildcard_query_functions():
    """Names of every module-level `cloudvision` function that issues a wildcard query."""
    module = ast.parse(inspect.getsource(cloudvision))
    names = set()
    for node in module.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id == "Wildcard":
                names.add(node.name)
                break
    return names


class TestSplitNotificationInvariance(TestCase):
    """Assert every CloudVision query helper ignores how notifications are framed."""

    databases = ("default", "job_logs")

    def test_results_are_invariant_to_notification_framing(self):
        for helper in QUERY_HELPERS:
            baseline = helper.call(canonical)
            with self.subTest(function=helper.name, transform="canonical"):
                self.assertTrue(
                    baseline,
                    f"{helper.name} returned nothing for its own fixture, so the invariance checks "
                    "below would pass vacuously. Fix the registered fixture.",
                )
            for transform_name, transform in TRANSFORMS:
                with self.subTest(function=helper.name, transform=transform_name):
                    self.assertEqual(
                        normalize(helper.call(transform)),
                        normalize(baseline),
                        f"{helper.name} returned a different result when CloudVision framed the "
                        f"same data as '{transform_name}'. Identify objects by "
                        "notif['path_elements'] and merge attributes across notifications before "
                        "interpreting them.",
                    )

    def test_every_wildcard_function_is_registered(self):
        """Fail when a new wildcard query helper is added without split-notification coverage."""
        registered = {helper.name for helper in QUERY_HELPERS}
        unregistered = wildcard_query_functions() - registered
        self.assertEqual(
            unregistered,
            set(),
            f"{sorted(unregistered)} issue wildcard CloudVision queries but are not in "
            "QUERY_HELPERS, so nothing checks them against split notifications. Add an entry with a "
            "captured payload fixture.",
        )
