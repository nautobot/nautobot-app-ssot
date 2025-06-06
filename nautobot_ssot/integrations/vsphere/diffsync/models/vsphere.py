"""vSphere SSoT DiffSync models."""

import datetime
from collections import defaultdict
from typing import List, Optional

from diffsync.enum import DiffSyncModelFlags
from diffsync.exceptions import ObjectCrudException
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from nautobot.extras.models.customfields import CustomField, CustomFieldTypeChoices
from nautobot.extras.models.tags import Tag
from nautobot.ipam.models import IPAddress, Prefix
from nautobot.virtualization.models import (
    Cluster,
    ClusterGroup,
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
        if isinstance(obj, (VirtualMachine, VMInterface, IPAddress)):
            cls.tag_object(cls, obj)

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

        def _tag_object(nautobot_object):
            """Apply custom field and tag to object, if applicable."""
            tag, _ = Tag.objects.get_or_create(name=tag_name)
            if hasattr(nautobot_object, "tags"):
                nautobot_object.tags.add(tag)
            if hasattr(nautobot_object, "cf"):
                # Ensure that the "ssot-synced-from-vsphere" custom field is present
                if not any(cfield for cfield in CustomField.objects.all() if cfield.key == custom_field_key):
                    custom_field_obj, _ = CustomField.objects.get_or_create(
                        type=CustomFieldTypeChoices.TYPE_DATE,
                        key=custom_field_key,
                        defaults={
                            "label": "Last synced from vSphere on",
                        },
                    )
                    synced_from_models = [VirtualMachine, VMInterface, IPAddress]
                    for model in synced_from_models:
                        custom_field_obj.content_types.add(ContentType.objects.get_for_model(model))
                    custom_field_obj.validated_save()

                # Update custom field date stamp
                nautobot_object.cf[custom_field_key] = TODAY
            nautobot_object.validated_save()

        _tag_object(nautobot_object)

    @classmethod
    def _get_queryset(cls, config, cluster_filters):
        """Get the queryset used to load the models data from Nautobot. This is overriden to pass in the config object."""
        available_fields = {field.name for field in cls._model._meta.get_fields()}
        parameter_names = [
            parameter for parameter in list(cls._identifiers) + list(cls._attributes) if parameter in available_fields
        ]
        # Here we identify any foreign keys (i.e. fields with '__' in them) so that we can load them directly in the
        # first query if this function hasn't been overridden.
        prefetch_related_parameters = [parameter.split("__")[0] for parameter in parameter_names if "__" in parameter]
        qs = cls.get_queryset(config, cluster_filters)
        return qs.prefetch_related(*prefetch_related_parameters)

    @classmethod
    def get_queryset(cls, config, cluster_filters):
        """Return the queryset for the model. This is overriden to pass in the config object."""
        return cls._model.objects.all()


class InterfacesDict(TypedDict):
    """Typed dict to relate interface to IP."""

    name: str
    virtual_machine__name: str


class PrefixModel(vSphereModelDiffSync):
    """Prefix model."""

    # When syncing with a cluster filter, we may not grab every prefix that exists from a previous non filtered sync.
    # This flag ensures we don't delete any prefixes
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

    # TODO(2.4): Overwriting this method so that the prefix ges called with `save()` before `validated_save()` due to bug https://github.com/nautobot/nautobot/issues/6738 in py3.8-stable CI test.
    @classmethod
    def _update_obj_with_parameters(cls, obj, parameters, adapter):
        """Update a given Nautobot ORM object with the given parameters."""
        relationship_fields = {
            # Example: {"group": {"name": "Group Name", "_model_class": TenantGroup}}
            "foreign_keys": defaultdict(dict),
            # Example: {"tags": [Tag-1, Tag-2]}
            "many_to_many_fields": defaultdict(list),
            # Example: TODO
            "custom_relationship_foreign_keys": defaultdict(dict),
            # Example: TODO
            "custom_relationship_many_to_many_fields": defaultdict(dict),
        }
        for field, value in parameters.items():
            cls._handle_single_field(field, obj, value, relationship_fields, adapter)

        # Set foreign keys
        cls._lookup_and_set_foreign_keys(relationship_fields["foreign_keys"], obj, adapter)

        # Save the object to the database
        try:
            obj.save()
        except (ValidationError, ValueError) as error:
            raise ObjectCrudException(
                f"Validated save failed for Django object:\n{error}\nParameters: {parameters}"
            ) from error
        # Handle relationship association creation. This needs to be after object creation, because relationship
        # association objects rely on both sides already existing.
        cls._lookup_and_set_custom_relationship_foreign_keys(
            relationship_fields["custom_relationship_foreign_keys"], obj, adapter
        )
        cls._set_custom_relationship_to_many_fields(
            relationship_fields["custom_relationship_many_to_many_fields"], obj, adapter
        )

        # Set many-to-many fields after saving.
        cls._set_many_to_many_fields(relationship_fields["many_to_many_fields"], obj)


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
                virtual_machine__name=attrs["vm_interfaces"][0]["virtual_machine__name"],
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
    _identifiers = ("name", "cluster__name")
    _attributes = (
        "status__name",
        "vcpus",
        "memory",
        "disk",
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
                    "primary_ip6": attrs.pop("primary_ip6__host", None),
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
                    "primary_ip6": attrs.pop("primary_ip6__host", None),
                }
            )
        return super().update(attrs)

    @classmethod
    def _get_queryset(cls, config, cluster_filters):
        """Get the queryset used to load the models data from Nautobot. This is overriden to pass in the config object."""
        available_fields = {field.name for field in cls._model._meta.get_fields()}
        parameter_names = [
            parameter for parameter in list(cls._identifiers) + list(cls._attributes) if parameter in available_fields
        ]
        # Here we identify any foreign keys (i.e. fields with '__' in them) so that we can load them directly in the
        # first query if this function hasn't been overridden.
        prefetch_related_parameters = [parameter.split("__")[0] for parameter in parameter_names if "__" in parameter]
        qs = cls.get_queryset(config, cluster_filters)
        return qs.prefetch_related(*prefetch_related_parameters)

    @classmethod
    def get_queryset(cls, config, cluster_filters):
        """Return the queryset for the model. This is overriden to pass in the config object."""
        if config.sync_tagged_only and cluster_filters:
            return cls._model.objects.filter(tags__name__in=["SSoT Synced from vSphere"], cluster__in=cluster_filters)
        elif config.sync_tagged_only:
            return cls._model.objects.filter(tags__name__in=["SSoT Synced from vSphere"])
        elif cluster_filters:
            return cls._model.objects.filter(cluster__in=cluster_filters)

        return cls._model.objects.all()


class ClusterModel(vSphereModelDiffSync):
    """Cluster Model Diffsync model."""

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
    def _get_queryset(cls, config, cluster_filters):
        """Get the queryset used to load the models data from Nautobot. This is overriden to pass in the config object."""
        available_fields = {field.name for field in cls._model._meta.get_fields()}
        parameter_names = [
            parameter for parameter in list(cls._identifiers) + list(cls._attributes) if parameter in available_fields
        ]
        # Here we identify any foreign keys (i.e. fields with '__' in them) so that we can load them directly in the
        # first query if this function hasn't been overridden.
        prefetch_related_parameters = [parameter.split("__")[0] for parameter in parameter_names if "__" in parameter]
        qs = cls.get_queryset(config, cluster_filters)
        return qs.prefetch_related(*prefetch_related_parameters)

    @classmethod
    def get_queryset(cls, config, cluster_filters):
        """Return the queryset for the model. This is overriden to pass in the config object and cluster filters."""
        if cluster_filters:
            return cluster_filters
        return cls._model.objects.all()


class ClusterGroupModel(vSphereModelDiffSync):
    """ClusterGroup Diffsync model."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.NATURAL_DELETION_ORDER | DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _model = ClusterGroup
    _modelname = "clustergroup"
    _identifiers = ("name",)
    _attributes = ()
    _children = {"cluster": "clusters"}

    name: str
    clusters: Optional[List[ClusterModel]] = list()
