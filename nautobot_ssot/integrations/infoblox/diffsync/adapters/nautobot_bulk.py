"""Bulk-write Nautobot adapter for the Infoblox SSoT integration.

Replaces per-object validated_save() calls with bulk_create() / bulk_update(),
trading per-object change logging for N→ceil(N/250) DB round-trips.

This module does NOT modify the existing NautobotAdapter or its models.
It provides opt-in subclasses used by the performance benchmark and can
be wired into the production job when the trade-offs are acceptable.

FK dependency order for Infoblox:
    OrmNamespace → OrmPrefix → OrmIPAddress

Tag handling
------------
_create_ip_address_common() calls create_tag_sync_from_infoblox() once per IP
(a DB get_or_create + 4 content_type queries) and then _ip.tags.add(tag) which
inserts a row into extras_taggeditem immediately. At 3000 IPs that is ~18,000
extra DB round-trips that cancel out the bulk gains.

BulkNautobotDnsARecord builds IPAddress objects directly, skipping the tag call.
BulkNautobotAdapter tracks IP PKs and bulk-inserts all tag rows in one shot
after flush_all() in sync_complete().
"""

import uuid

from django.contrib.contenttypes.models import ContentType
from nautobot.extras.models.tags import TaggedItem
from nautobot.ipam.choices import IPAddressTypeChoices
from nautobot.ipam.models import IPAddress as OrmIPAddress
from nautobot.ipam.models import Namespace as OrmNamespace
from nautobot.ipam.models import Prefix as OrmPrefix

from nautobot_ssot.integrations.infoblox.choices import DNSRecordTypeChoices
from nautobot_ssot.integrations.infoblox.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.integrations.infoblox.diffsync.models.base import DnsARecord, Network, Namespace
from nautobot_ssot.integrations.infoblox.diffsync.models.nautobot import (
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
    create_tag_sync_from_infoblox,
    map_network_view_to_namespace,
)
from nautobot_ssot.utils.bulk import BulkOperationsMixin


# ---------------------------------------------------------------------------
# Bulk model overrides — only create() is changed; update/delete fall through
# ---------------------------------------------------------------------------


class BulkNautobotNamespace(NautobotNamespace):
    """Queues Namespace creation instead of calling validated_save()."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        _ns = OrmNamespace(name=ids["name"])
        # UUID is set at OrmNamespace() — update map before any DB write
        adapter.namespace_map[ids["name"]] = _ns.pk
        adapter.queue_for_create(OrmNamespace, _ns)
        # Call the base DiffSync Namespace.create() for internal bookkeeping only
        return Namespace.create(ids=ids, adapter=adapter, attrs=attrs)


class BulkNautobotNetwork(NautobotNetwork):
    """Queues Prefix creation instead of calling validated_save()."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        namespace_name = map_network_view_to_namespace(
            value=ids["namespace"],
            network_view_to_namespace_map=adapter.config.infoblox_network_view_to_namespace_map,
            direction="nv_to_ns",
        )
        _prefix = OrmPrefix(
            prefix=ids["network"],
            status_id=adapter.status_map["Active"],
            type=attrs["network_type"],
            description=attrs.get("description", ""),
            namespace_id=adapter.namespace_map[namespace_name],
        )
        # UUID is set — update prefix_map immediately
        adapter.prefix_map[(ids["namespace"], ids["network"])] = _prefix.pk
        adapter.queue_for_create(OrmPrefix, _prefix)
        return Network.create(ids=ids, adapter=adapter, attrs=attrs)


class BulkNautobotDnsARecord(NautobotDnsARecord):
    """Queues IPAddress creation/update via A record instead of calling validated_save().

    A records are the primary vehicle for creating IP addresses in Nautobot
    when dns_record_type = A_RECORD. This class covers the hot path.

    Tags are NOT applied here. BulkNautobotAdapter.sync_complete() bulk-inserts
    all tag associations in one shot after flush_all(), eliminating ~18k DB
    round-trips at medium scale vs calling create_tag_sync_from_infoblox() +
    tags.add() once per IP.
    """

    @classmethod
    def create(cls, adapter, ids, attrs):
        if adapter.config.dns_record_type not in (
            DNSRecordTypeChoices.A_RECORD,
            DNSRecordTypeChoices.A_AND_PTR_RECORD,
        ):
            # Fall back to existing validated_save() path for non-A-record configs
            return NautobotDnsARecord.create.__func__(cls, adapter, ids, attrs)

        addr_w_pfxl = f"{ids['address']}/{ids['prefix_length']}"
        ip_pk = adapter.ipaddr_map.get((addr_w_pfxl, ids["namespace"]))

        if ip_pk:
            # IP already exists in DB — queue an update of dns_name
            _ipaddr = OrmIPAddress.objects.get(id=ip_pk)
            _ipaddr.dns_name = attrs.get("dns_name") or ""
            _ipaddr.custom_field_data.update({"dns_a_record_comment": attrs.get("description") or ""})
            adapter.queue_for_update(OrmIPAddress, _ipaddr, ["dns_name", "custom_field_data"])
        else:
            # Build IPAddress without tags — BulkNautobotAdapter.sync_complete() applies
            # the sync tag in bulk after flush_all() to avoid N DB round-trips.
            try:
                status = adapter.status_map[attrs["status"]]
            except KeyError:
                status = adapter.config.default_status.pk
            ip_type = (attrs.get("ip_addr_type") or "").lower()
            if ip_type not in IPAddressTypeChoices.as_dict():
                ip_type = "host"
            _ipaddr = OrmIPAddress(
                address=addr_w_pfxl,
                status_id=status,
                type=ip_type,
                dns_name=attrs.get("dns_name") or "",
                parent_id=adapter.prefix_map[(ids["namespace"], ids["prefix"])],
            )
            _ipaddr.custom_field_data.update({"dns_a_record_comment": attrs.get("description") or ""})
            # UUID is set — update ipaddr_map and tag queue immediately
            adapter.ipaddr_map[(addr_w_pfxl, ids["namespace"])] = _ipaddr.pk
            adapter._ip_tag_pks.append(_ipaddr.pk)
            adapter.queue_for_create(OrmIPAddress, _ipaddr)

        return DnsARecord.create(ids=ids, adapter=adapter, attrs=attrs)


# ---------------------------------------------------------------------------
# Bulk adapter
# ---------------------------------------------------------------------------


class BulkNautobotAdapter(BulkOperationsMixin, NautobotAdapter):
    """Infoblox NautobotAdapter that uses bulk_create/bulk_update in sync_complete().

    Drop-in replacement for NautobotAdapter. All load() and update/delete
    logic is inherited unchanged. Only the create() path for Namespace,
    Prefix, and IPAddress (via DnsARecord) is replaced with bulk queuing.

    FK flush order: Namespace → Prefix → IPAddress
    Tag associations are bulk-inserted after flush in _flush_ip_tags().
    """

    namespace = BulkNautobotNamespace
    prefix = BulkNautobotNetwork
    ipaddress = NautobotIPAddress  # fixed-address path; rarely used in benchmark
    vlangroup = NautobotVlanGroup
    vlan = NautobotVlan
    dnshostrecord = NautobotDnsHostRecord
    dnsarecord = BulkNautobotDnsARecord
    dnsptrrecord = NautobotDnsPTRRecord

    _bulk_create_order = [OrmNamespace, OrmPrefix, OrmIPAddress]

    # ------------------------------------------------------------------
    # Bulk-write side-effect config (read by sync_complete() when it
    # invokes flush_all). Set as class attrs OR per-instance attrs BEFORE
    # src.sync_to(dst) runs. This lets the LEGACY bulk pipeline (the
    # diff_to / sync_to path) opt into the same side-effects as the
    # streaming pipeline. See nautobot_ssot/utils/bulk.py for kwarg semantics.
    # ------------------------------------------------------------------
    refire_post_save: bool = False
    bulk_signal: bool = False
    bulk_clean: bool = False
    signal_context = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-create/cache the sync tag so it's only fetched once, not once per IP.
        self._sync_tag = create_tag_sync_from_infoblox()
        # UUIDs of IPAddress objects queued for creation — tagged in bulk after flush.
        self._ip_tag_pks: list = []

    def _flush_ip_tags(self) -> None:
        """Bulk-insert extras_taggeditem rows for all IPs created in this sync.

        Called after flush_all() so all IPAddress rows exist in the DB.
        Uses ignore_conflicts=True to be idempotent.
        """
        if not self._ip_tag_pks:
            return
        ct = ContentType.objects.get_for_model(OrmIPAddress)
        TaggedItem.objects.bulk_create(
            [
                TaggedItem(id=uuid.uuid4(), tag=self._sync_tag, content_type=ct, object_id=pk)
                for pk in self._ip_tag_pks
            ],
            batch_size=self._bulk_batch_size,
            ignore_conflicts=True,
        )
        if hasattr(self, "job"):
            self.job.logger.debug(f"Bulk tagged {len(self._ip_tag_pks)} IPAddress objects.")
        self._ip_tag_pks.clear()

    def sync_complete(self, source, *args, **kwargs):
        """Flush all queued bulk operations before running post-sync hooks."""
        pending_creates = self.pending_create_count()
        pending_updates = self.pending_update_count()

        if pending_creates:
            self.job.logger.info(
                f"Flushing {pending_creates} queued creates via bulk_create() "
                f"(order: Namespace → Prefix → IPAddress)."
            )
        if pending_updates:
            self.job.logger.info(f"Flushing {pending_updates} queued updates via bulk_update().")

        self.flush_all(
            refire_post_save=self.refire_post_save,
            bulk_signal=self.bulk_signal,
            bulk_clean=self.bulk_clean,
            signal_context=self.signal_context,
        )
        self._flush_ip_tags()
        super().sync_complete(source, *args, **kwargs)

    # ------------------------------------------------------------------
    # Hook 2 support: ORM resolver for opt-in dump-time full_clean()
    # ------------------------------------------------------------------

    def to_orm_kwargs(self, model_type: str, ids: dict, attrs: dict):
        """Resolve a (model_type, ids, attrs) tuple into ORM construction args.

        Used by `dump_adapter(..., orm_resolver=...)` (Hook 2). Returns
        `(OrmClass, kwargs, exclude_fields)` so the caller can build a
        transient ORM instance and run `full_clean(exclude=exclude_fields,
        validate_unique=False, validate_constraints=False)` to enforce
        Nautobot-level domain rules WITHOUT a DB round-trip.

        FK fields are intentionally NOT populated and are returned in
        `exclude_fields` — Hook 2 is shape/value validation, not relational.
        DB constraints handle FK validity at INSERT time.

        Returns None for model types we don't have a mapping for.
        """
        if model_type == "namespace":
            return OrmNamespace, {"name": ids["name"]}, []
        if model_type == "prefix":
            return (
                OrmPrefix,
                {
                    "prefix": ids["network"],
                    "type": attrs.get("network_type") or "network",
                    "description": attrs.get("description") or "",
                },
                ["namespace", "status"],
            )
        if model_type in ("ipaddress", "dnsarecord", "dnshostrecord", "dnsptrrecord"):
            addr_w_pfxl = f"{ids['address']}/{ids['prefix_length']}"
            ip_type = (attrs.get("ip_addr_type") or "host").lower()
            if ip_type not in IPAddressTypeChoices.as_dict():
                ip_type = "host"
            return (
                OrmIPAddress,
                {
                    "address": addr_w_pfxl,
                    "type": ip_type,
                    "dns_name": attrs.get("dns_name") or "",
                    "description": attrs.get("description") or "",
                },
                ["parent", "status"],
            )
        return None
