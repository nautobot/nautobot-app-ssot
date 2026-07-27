"""Proxmox VE SSoT DiffSync models."""

import random
from typing import Annotated, List, Optional

from diffsync import DiffSyncModel
from diffsync.enum import DiffSyncModelFlags
from django.contrib.contenttypes.models import ContentType
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import Device, Interface
from nautobot.extras.models.tags import Tag
from nautobot.ipam.models import IPAddress, Prefix
from nautobot.virtualization.models import (
    Cluster,
    ClusterGroup,
    VirtualMachine,
    VMInterface,
)
from typing_extensions import TypedDict

from nautobot_ssot.contrib import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    NautobotModel,
    RelationshipSideEnum,
)
from nautobot_ssot.contrib.typeddicts import InterfaceDict, TagDict
from nautobot_ssot.integrations.proxmox.constants import (
    HOST_RELATIONSHIP_LABEL,
    NODE_CPU_COUNT_CF,
    NODE_MEMORY_GB_CF,
    NODE_PVE_VERSION_CF,
    SSOT_CUSTOM_FIELD_KEY,
)
from nautobot_ssot.integrations.proxmox.diffsync.models.base import ProxmoxModelDiffSync


class InterfacesDict(TypedDict):
    """Typed dict to relate an interface to an IP."""

    name: str
    virtual_machine__name: str


class ClusterRefDict(TypedDict):
    """Typed dict to relate a node Device to its Cluster (many-to-many)."""

    name: str


class DeviceRefDict(TypedDict):
    """Typed dict to relate a Virtual Machine to its host node Device (custom relationship)."""

    name: str


class PrefixModel(ProxmoxModelDiffSync):
    """Prefix model."""

    # When syncing with a cluster filter we may not see every prefix from a previous unfiltered sync,
    # so never delete prefixes.
    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _model = Prefix
    _modelname = "prefix"
    _identifiers = ("network", "prefix_length", "namespace__name", "status__name")
    _attributes = ("type",)

    network: str
    prefix_length: int
    namespace__name: str
    status__name: str
    type: str

    # TODO(2.4): Save with `save()` before `validated_save()` due to nautobot/nautobot#6738.
    @classmethod
    def _update_obj_with_parameters(cls, obj, parameters, adapter):
        """Update a given Nautobot ORM object with the given parameters.

        Args:
            obj (Prefix): The Nautobot Prefix to update.
            parameters (dict[str, Any]): The parameters to set on the Prefix.
            adapter (Adapter): The adapter used to look up related objects in the cache.
        """
        cls._update_obj_save_first(obj, parameters, adapter)


class IPAddressModel(ProxmoxModelDiffSync):
    """IPAddress DiffSync model."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _model = IPAddress
    _modelname = "ip_address"
    _identifiers = ("host", "mask_length", "status__name")
    _attributes = ("vm_interfaces", "interfaces")

    host: str
    mask_length: int
    status__name: str
    vm_interfaces: List[InterfacesDict] = []
    interfaces: List[InterfaceDict] = []

    @classmethod
    def get_queryset(cls, config, cluster_filters):  # pylint: disable=unused-argument
        """Only load IP addresses previously synced from Proxmox VE.

        Scoping is derived from the ``last_synced_from_proxmox_on`` custom field (stamped on every
        sync), not the cosmetic SSoT tag, so another integration deleting that tag can't affect
        which objects this integration considers its own.

        Args:
            config (SSOTProxmoxConfig): The integration configuration object.
            cluster_filters (QuerySet): Clusters the sync is scoped to, or an empty value for all.

        Returns:
            QuerySet: The IPAddress queryset to load.
        """
        return cls._model.objects.filter(_custom_field_data__has_key=SSOT_CUSTOM_FIELD_KEY)


class VMInterfaceModel(ProxmoxModelDiffSync):
    """VMInterface DiffSync model."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.NATURAL_DELETION_ORDER

    _model = VMInterface
    _modelname = "interface"
    _identifiers = ("name", "virtual_machine__name")
    _attributes = ("enabled", "mac_address", "status__name")

    name: str
    virtual_machine__name: str
    enabled: bool
    status__name: str
    mac_address: Optional[str] = None


class DeviceInterfaceModel(ProxmoxModelDiffSync):
    """DCIM Interface DiffSync model representing a Proxmox VE node's network interface."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.NATURAL_DELETION_ORDER

    _model = Interface
    _modelname = "device_interface"
    _identifiers = ("name", "device__name")
    _attributes = ("type", "enabled", "status__name", "mtu", "bridge__name", "lag__name", "parent_interface__name")

    name: str
    device__name: str
    type: str
    enabled: bool
    status__name: str
    mtu: Optional[int] = None
    # Intra-device interface relationships (bridge members, bond slaves, VLAN parents). The write is
    # deferred to the adapter's `sync_complete` so it doesn't depend on interface creation order;
    # all three target interfaces live on the same node Device.
    bridge__name: Optional[str] = None
    lag__name: Optional[str] = None
    parent_interface__name: Optional[str] = None

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create the interface, deferring intra-device relationship links until all exist.

        Args:
            adapter (Adapter): The Nautobot sync adapter.
            ids (dict[str, Any]): The natural keys for the interface.
            attrs (dict[str, Any]): The attributes to assign to the new interface.

        Returns:
            DeviceInterfaceModel: The created interface model.
        """
        cls._defer_links(adapter, ids, attrs)
        return super().create(adapter, ids, attrs)

    def update(self, attrs):
        """Update the interface, deferring intra-device relationship links until all exist.

        Args:
            attrs (dict[str, Any]): The attributes to update on the interface.

        Returns:
            DeviceInterfaceModel: The updated interface model.
        """
        ids = {"name": self.name, "device__name": self.device__name}
        self._defer_links(self.adapter, ids, attrs)
        return super().update(attrs)

    @staticmethod
    def _defer_links(adapter, ids, attrs):
        """Pop relationship attributes and queue them for resolution in sync_complete.

        Args:
            adapter (Adapter): The Nautobot sync adapter holding the deferred-link queue.
            ids (dict[str, Any]): The natural keys for the interface (``name``/``device__name``).
            attrs (dict[str, Any]): The attributes being created/updated; link keys are popped from it.
        """
        link_keys = ("bridge__name", "lag__name", "parent_interface__name")
        if any(key in attrs for key in link_keys):
            adapter._interface_links.append(
                {
                    "device__name": ids["device__name"],
                    "name": ids["name"],
                    "bridge__name": attrs.pop("bridge__name", None),
                    "lag__name": attrs.pop("lag__name", None),
                    "parent_interface__name": attrs.pop("parent_interface__name", None),
                }
            )

    @classmethod
    def get_queryset(cls, config, cluster_filters):  # pylint: disable=unused-argument
        """Only load Interfaces on Devices previously synced from Proxmox VE.

        Scoping traverses to the host Device's ``last_synced_from_proxmox_on`` custom field (Device
        is the object that actually gets tagged/stamped by ``ProxmoxModelDiffSync``; the Interface
        itself never is), not the cosmetic SSoT tag.

        Args:
            config (SSOTProxmoxConfig): The integration configuration object.
            cluster_filters (QuerySet): Clusters the sync is scoped to, or an empty value for all.

        Returns:
            QuerySet: The Interface queryset to load.
        """
        return cls._model.objects.filter(device___custom_field_data__has_key=SSOT_CUSTOM_FIELD_KEY)


class DeviceModel(ProxmoxModelDiffSync):
    """Device DiffSync model representing a Proxmox VE node (hypervisor host)."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _model = Device
    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "device_type__model",
        "role__name",
        "location__name",
        "status__name",
        "clusters",
        "pve_version",
        "cpu_count",
        "memory_gb",
        "primary_ip4__host",
    )
    _children = {"device_interface": "interfaces"}

    name: str
    device_type__model: str
    role__name: str
    location__name: str
    status__name: str
    # Membership in the Proxmox VE Cluster (Nautobot models Cluster<->Device hosts as many-to-many).
    clusters: List[ClusterRefDict] = []
    # Hardware / version detail from /nodes/{node}/status, stored on custom fields.
    pve_version: Annotated[Optional[str], CustomFieldAnnotation(key=NODE_PVE_VERSION_CF)] = None
    cpu_count: Annotated[Optional[int], CustomFieldAnnotation(key=NODE_CPU_COUNT_CF)] = None
    memory_gb: Annotated[Optional[int], CustomFieldAnnotation(key=NODE_MEMORY_GB_CF)] = None
    # The node's management IP; assignment is deferred to sync_complete since the IP/interface must
    # exist first.
    primary_ip4__host: Optional[str] = None
    interfaces: List[DeviceInterfaceModel] = []

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create the node Device, deferring primary IP assignment until its IP exists.

        The primary IP cannot be set until the IP/interface exist, so it is popped here and assigned
        in the adapter's ``sync_complete`` callback.

        Args:
            adapter (Adapter): The Nautobot sync adapter.
            ids (dict[str, Any]): The natural keys for the Device.
            attrs (dict[str, Any]): The attributes to assign to the new Device.

        Returns:
            DeviceModel: The created Device model.
        """
        if attrs.get("primary_ip4__host"):
            adapter._device_primary_ips.append({"name": ids["name"], "primary_ip4": attrs.pop("primary_ip4__host")})
        return super().create(adapter, ids, attrs)

    def update(self, attrs):
        """Update the node Device, deferring primary IP assignment until its IP exists.

        Args:
            attrs (dict[str, Any]): The attributes to update on the Device.

        Returns:
            DeviceModel: The updated Device model.
        """
        if attrs.get("primary_ip4__host"):
            self.adapter._device_primary_ips.append({"name": self.name, "primary_ip4": attrs.pop("primary_ip4__host")})
        return super().update(attrs)

    @classmethod
    def get_queryset(cls, config, cluster_filters):  # pylint: disable=unused-argument
        """Only load Devices previously synced from Proxmox VE.

        Scoping is derived from the ``last_synced_from_proxmox_on`` custom field, not the cosmetic
        SSoT tag.

        Args:
            config (SSOTProxmoxConfig): The integration configuration object.
            cluster_filters (QuerySet): Clusters the sync is scoped to, or an empty value for all.

        Returns:
            QuerySet: The Device queryset to load.
        """
        return cls._model.objects.filter(_custom_field_data__has_key=SSOT_CUSTOM_FIELD_KEY)


class VirtualMachineModel(ProxmoxModelDiffSync):
    """Virtual Machine DiffSync model (QEMU VM or LXC container)."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.NATURAL_DELETION_ORDER

    _model = VirtualMachine
    _modelname = "virtual_machine"
    _identifiers = ("name", "cluster__name")
    _attributes = (
        "status__name",
        "vcpus",
        "memory",
        "disk",
        "host_device",
        "primary_ip4__host",
        "primary_ip6__host",
        "tags",
    )
    _children = {"interface": "interfaces"}

    name: str
    status__name: str
    vcpus: Optional[int] = None
    memory: Optional[int] = None
    disk: Optional[int] = None
    cluster__name: str
    # Nautobot's VirtualMachine has no host-Device FK, so the Proxmox node hosting the VM is linked
    # via the "Proxmox VM Host" custom relationship (Device -> VirtualMachine, one-to-many).
    host_device: Annotated[
        Optional[DeviceRefDict],
        CustomRelationshipAnnotation(name=HOST_RELATIONSHIP_LABEL, side=RelationshipSideEnum.DESTINATION),
    ] = None
    primary_ip4__host: Optional[str] = None
    primary_ip6__host: Optional[str] = None
    tags: List[TagDict] = []

    interfaces: List[VMInterface] = []

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create the VM, deferring primary IP assignment until interfaces/IPs exist.

        The primary IPs cannot be set until the interfaces/IPs exist, so they are popped here and
        assigned in the adapter's ``sync_complete`` callback.

        Args:
            adapter (Adapter): The Nautobot sync adapter.
            ids (dict[str, Any]): The natural keys for the VM.
            attrs (dict[str, Any]): The attributes to assign to the new VM.

        Returns:
            VirtualMachineModel: The created VM model.
        """
        if attrs.get("primary_ip4__host") or attrs.get("primary_ip6__host"):
            adapter._primary_ips.append(
                {
                    "device": {**ids},
                    "primary_ip4": attrs.pop("primary_ip4__host", None),
                    "primary_ip6": attrs.pop("primary_ip6__host", None),
                }
            )
        # A None host_device means the VM has no hosting node; drop it so the contrib layer doesn't
        # try to build a custom-relationship association from a missing value.
        if attrs.get("host_device") is None:
            attrs.pop("host_device", None)
        return super().create(adapter, ids, attrs)

    def update(self, attrs):
        """Update the VM, deferring primary IP assignment until interfaces/IPs exist.

        Args:
            attrs (dict[str, Any]): The attributes to update on the VM.

        Returns:
            VirtualMachineModel: The updated VM model.
        """
        if attrs.get("primary_ip4__host") or attrs.get("primary_ip6__host"):
            self.adapter._primary_ips.append(
                {
                    "device": {"name": self.name, "cluster__name": self.cluster__name},
                    "primary_ip4": attrs.pop("primary_ip4__host", None),
                    "primary_ip6": attrs.pop("primary_ip6__host", None),
                }
            )
        if "host_device" in attrs and attrs["host_device"] is None:
            attrs.pop("host_device")
        return super().update(attrs)

    @classmethod
    def get_queryset(cls, config, cluster_filters):  # pylint: disable=unused-argument
        """Load existing Proxmox-synced VMs, optionally scoped to selected clusters.

        Scoping is derived from the ``last_synced_from_proxmox_on`` custom field rather than the
        cosmetic SSoT tag, so it's unaffected by another integration deleting/recreating that tag
        mid-sync.

        Args:
            config (SSOTProxmoxConfig): The integration configuration object.
            cluster_filters (QuerySet): Clusters the sync is scoped to, or an empty value for all.

        Returns:
            QuerySet: The VirtualMachine queryset to load.
        """
        if cluster_filters:
            return cls._model.objects.filter(
                _custom_field_data__has_key=SSOT_CUSTOM_FIELD_KEY, cluster__in=cluster_filters
            )
        return cls._model.objects.filter(_custom_field_data__has_key=SSOT_CUSTOM_FIELD_KEY)


class ClusterModel(ProxmoxModelDiffSync):
    """Cluster DiffSync model."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.NATURAL_DELETION_ORDER | DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _model = Cluster
    _modelname = "cluster"
    _identifiers = ("name",)
    _attributes = (
        "cluster_type__name",
        "cluster_group__name",
    )

    name: str
    cluster_type__name: str
    cluster_group__name: Optional[str] = None

    @classmethod
    def get_queryset(cls, config, cluster_filters):
        """Return the queryset for the model, honoring cluster filters.

        Args:
            config (SSOTProxmoxConfig): The integration configuration object.
            cluster_filters (QuerySet): Clusters the sync is scoped to, or an empty value for all.

        Returns:
            QuerySet: The Cluster queryset to load.
        """
        if cluster_filters:
            return cluster_filters
        return cls._model.objects.all()


class ClusterGroupModel(ProxmoxModelDiffSync):
    """ClusterGroup DiffSync model."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.NATURAL_DELETION_ORDER | DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _model = ClusterGroup
    _modelname = "clustergroup"
    _identifiers = ("name",)
    _attributes = ()
    _children = {"cluster": "clusters"}

    name: str
    clusters: Optional[List[ClusterModel]] = list()


class TagModel(ProxmoxModelDiffSync):
    """Tag DiffSync model."""

    _model = Tag
    _modelname = "tag"
    _identifiers = ("name",)
    _attributes = ("description",)
    _children = {}

    name: str
    description: Optional[str] = ""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create a Tag in Nautobot.

        Args:
            adapter (Adapter): The Nautobot sync adapter.
            ids (dict[str, Any]): The natural keys for the Tag.
            attrs (dict[str, Any]): The attributes to assign to the new Tag.

        Returns:
            TagModel: The created Tag model.
        """
        adapter.job.logger.info(f"Creating Nautobot Tag: {ids['name']}")
        _color = random.choice(ColorChoices.values())  # noqa: S311
        _new_tag = Tag(
            name=ids["name"],
            color=_color,
            description=attrs["description"],
        )
        _new_tag.validated_save()
        _new_tag.content_types.set([ContentType.objects.get_for_model(VirtualMachine)])
        _new_tag.validated_save()
        return DiffSyncModel.create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update a Tag in Nautobot.

        Args:
            attrs (dict[str, Any]): The attributes to update on the Tag.

        Returns:
            TagModel: The updated Tag model.
        """
        self.adapter.job.logger.info(f"Updating Tag {self.name}")
        _update_tag = Tag.objects.get(name=self.name)
        if attrs.get("description"):
            _update_tag.description = attrs["description"]
        _update_tag.validated_save()
        return super(NautobotModel, self).update(attrs)

    def delete(self):
        """Delete a Tag in Nautobot.

        Returns:
            TagModel: The deleted Tag model, or ``None`` if the Tag was not found.
        """
        self.adapter.job.logger.debug(f"Delete Tag: {self.name}")
        try:
            _tag = Tag.objects.get(name=self.name)
            super().delete()
            _tag.delete()
            return self
        except Tag.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find Tag {self.name} for deletion. {err}")
