"""vSphere SSoT DiffSync models."""

import datetime
from typing import List, Optional

from diffsync.enum import DiffSyncModelFlags
from django.contrib.contenttypes.models import ContentType
from nautobot.core.choices import ColorChoices
from nautobot.extras.models.customfields import CustomField, CustomFieldTypeChoices
from nautobot.extras.models.tags import Tag
from nautobot.ipam.models import IPAddress, Prefix
from nautobot.virtualization.models import (
    Cluster,
    ClusterGroup,
    ClusterType,
    VirtualMachine,
    VMInterface,
)
from typing_extensions import TypedDict

from nautobot_ssot.contrib import NautobotModel

TODAY = datetime.date.today().isoformat()


class vSphereModelDiffSync(NautobotModel):
    """vSphere Model DiffSync model."""

    @classmethod
    def _update_obj_with_parameters(cls, obj, parameters, adapter):
        """Update the object with the parameters.

        Args:
            obj (Any): The object to update.
            parameters (dict[str, Any]): The parameters to update the object with.
            adapter (Adapter): The adapter to use to update the object.
        """
        super()._update_obj_with_parameters(obj, parameters, adapter)
        cls.tag_object(cls, obj)

    def create_ssot_tag(self):
        """Create vSphere SSoT Tag."""
        ssot_tag, _ = Tag.objects.get_or_create(
            slug="ssot-synced-from-vsphere",
            name="SSoT Synced from vSphere",
            defaults={
                "description": "Object synced at some point from VMWare vSphere to Nautobot",
                "color": ColorChoices.COLOR_LIGHT_GREEN,
            },
        )
        return ssot_tag

    def tag_object(
        self,
        nautobot_object,
        custom_field_key="last_synced_from_vsphere_on",
        tag_name="SSoT Synced from vSphere",
    ):
        """Apply the given tag and custom field to the identified object.

        Args:
            nautobot_object (Any): Nautobot ORM Object
            custom_field (str): Name of custom field to update
            tag_name (Optional[str], optional): Tag name. Defaults to "SSoT Synced From vsphere".
        """
        if tag_name == "SSoT Synced from vSphere":
            tag = self.create_ssot_tag()
        else:
            tag, _ = Tag.objects.get_or_create(name=tag_name)

        def _tag_object(nautobot_object):
            """Apply custom field and tag to object, if applicable."""
            if hasattr(nautobot_object, "tags"):
                nautobot_object.tags.add(tag)
            if hasattr(nautobot_object, "cf"):
                # Ensure that the "ssot-synced-from-vsphere" custom field is present
                if not any(
                    cfield
                    for cfield in CustomField.objects.all()
                    if cfield.key == custom_field_key
                ):
                    custom_field_obj, _ = CustomField.objects.get_or_create(
                        type=CustomFieldTypeChoices.TYPE_DATE,
                        key=custom_field_key,
                        defaults={
                            "label": "Last synced from vSphere on",
                        },
                    )
                    synced_from_models = [
                        Cluster,
                        ClusterType,
                        ClusterGroup,
                        VirtualMachine,
                        VMInterface,
                    ]
                    for model in synced_from_models:
                        custom_field_obj.content_types.add(
                            ContentType.objects.get_for_model(model)
                        )
                    custom_field_obj.validated_save()

                # Update custom field date stamp
                nautobot_object.cf[custom_field_key] = TODAY
            nautobot_object.validated_save()

        _tag_object(nautobot_object)


class InterfacesDict(TypedDict):
    """Typed dict to relate interface to IP."""

    name: str
    virtual_machine__name: str


class PrefixModel(vSphereModelDiffSync):
    """Prefix model."""

    _model = Prefix
    _modelname = "prefix"
    _identifiers = ("network", "prefix_length", "namespace__name", "status__name")
    _attributes = ("type",)

    network: str
    prefix_length: int
    namespace__name: str
    status__name: str
    type: str


class IPAddressModel(vSphereModelDiffSync):
    """IPAddress Diffsync model."""

    _model = IPAddress
    _modelname = "ip_address"
    _identifiers = ("host", "mask_length", "status__name")
    _attributes = ("vm_interfaces",)

    host: str
    mask_length: int
    status__name: str
    vm_interfaces: List[InterfacesDict] = []

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create the IP address.

        This is being overriden because the interface that the IP address is assigned to may already exist. Diffsync won't take that into account.

        Args:
            adapter (Adapter): The adapter.
            ids (dict[str, Any]): The natural keys for the IP address.
            attrs (dict[str, Any]): The attributes to assign to the IP address.

        Returns:
            IPAddressModel: The IP address model.
        """
        try:
            ip_address = cls._model.objects.get(**ids)
            vm_interface = VMInterface.objects.get(
                name=attrs["vm_interfaces"][0]["name"],
                virtual_machine__name=attrs["vm_interfaces"][0][
                    "virtual_machine__name"
                ],
            )
            vm_interface.ip_addresses.set([ip_address])
            vm_interface.validated_save()
            # Calling return base as super() isn't called here.
            return cls.create_base(adapter, ids, attrs)
        except cls._model.DoesNotExist:
            # If the IP address doesn't exist, normal diffsync process will create it and associate with the interface.
            return super().create(adapter, ids, attrs)


class VMInterfaceModel(vSphereModelDiffSync):
    """VMInterface Diffsync model."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.NATURAL_DELETION_ORDER

    _model = VMInterface
    _modelname = "interface"
    _identifiers = ("name", "virtual_machine__name")
    _attributes = ("enabled", "mac_address", "status__name")
    _children = {"ip_address": "ip_addresses"}

    name: str
    virtual_machine__name: str
    enabled: bool
    status__name: str
    mac_address: Optional[str] = None
    ip_addresses: List[IPAddress] = []


class VirtualMachineModel(vSphereModelDiffSync):
    """Virtual Machine Diffsync model."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.NATURAL_DELETION_ORDER

    _model = VirtualMachine
    _modelname = "virtual_machine"
    _identifiers = ("name",)
    _attributes = (
        "status__name",
        "vcpus",
        "memory",
        "disk",
        "cluster__name",
        "primary_ip4__host",
        "primary_ip6__host",
    )
    _children = {"interface": "interfaces"}

    name: str
    status__name: str
    vcpus: Optional[int] = None
    memory: Optional[int] = None
    disk: Optional[int] = None
    cluster__name: str
    primary_ip4__host: Optional[str] = None
    primary_ip6__host: Optional[str] = None

    interfaces: List[VMInterface] = []

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create the device.

        This overridden method removes the primary IP addresses since those
        cannot be set until after the interfaces are created. The primary IPs
        are set in the `sync_complete` callback of the adapter.

        Args:
            diffsync (VsphereDiffSync): The nautobot sync adapter.
            ids (dict[str, Any]): The natural keys for the device.
            attrs (dict[str, Any]): The attributes to assign to the newly created
                device.

        Returns:
            DeviceModel: The device model.
        """
        if attrs["primary_ip4__host"] or attrs["primary_ip6__host"]:
            adapter._primary_ips.append(
                {
                    "device": {**ids},
                    "primary_ip4": attrs.pop("primary_ip4__host", None),
                    "primary_ip6": attrs.pop("primary_ip4__host", None),
                }
            )
        return super().create(adapter, ids, attrs)

    def update(self, attrs):
        """Update the device.

        This overridden method removes the primary IP addresses since those
        cannot be set until after the interfaces and IPs are created. The primary IPs
        are set in the `sync_complete` callback of the adapter.

        Args:
            attrs (dict[str, Any]): The attributes to update on the device.

        Returns:
            DeviceModel: The device model.
        """
        if attrs.get("primary_ip4__host") or attrs.get("primary_ip6__host"):
            self.adapter._primary_ips.append(
                {
                    "device": {"name": self.name},
                    "primary_ip4": attrs.pop("primary_ip4__host", None),
                    "primary_ip6": attrs.pop("primary_ip4__host", None),
                }
            )
        return super().update(attrs)


class ClusterModel(vSphereModelDiffSync):
    """Cluster Model Diffsync model."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.NATURAL_DELETION_ORDER

    _model = Cluster
    _modelname = "cluster"
    _identifiers = ("name",)
    _attributes = (
        "cluster_type__name",
        "cluster_group__name",
    )
    _children = {"virtual_machine": "virtual_machines"}

    name: str
    cluster_type__name: str
    cluster_group__name: Optional[str] = None

    virtual_machines: List[VirtualMachineModel] = list()


class ClusterGroupModel(vSphereModelDiffSync):
    """ClusterGroup Diffsync model."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.NATURAL_DELETION_ORDER

    _model = ClusterGroup
    _modelname = "clustergroup"
    _identifiers = ("name",)
    _attributes = ()
    _children = {"cluster": "clusters"}

    name: str
    clusters: Optional[List[ClusterModel]] = list()
