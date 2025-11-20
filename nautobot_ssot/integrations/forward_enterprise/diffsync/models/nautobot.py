"""Nautobot Models for Forward Enterprise integration with SSoT app."""

from typing import List, Optional

try:
    from typing import Annotated  # Python>=3.9
except ImportError:
    from typing_extensions import Annotated

from diffsync.exceptions import ObjectCrudException
from nautobot.ipam.models import VLAN, VRF, IPAddress, IPAddressToInterface, Namespace, Prefix, VLANGroup
from pydantic import Field

from nautobot_ssot.contrib import CustomFieldAnnotation, NautobotModel
from nautobot_ssot.contrib.typeddicts import VRFDict
from nautobot_ssot.integrations.forward_enterprise import constants
from nautobot_ssot.integrations.forward_enterprise.utils.location_helpers import (
    extract_location_from_vlan_group_name,
    get_or_create_location_for_vlan_group,
)
from nautobot_ssot.integrations.forward_enterprise.utils.nautobot import (
    ensure_vlan_group_content_type_on_location_type,
)


class NautobotVRFModel(NautobotModel):
    """Nautobot VRF model."""

    _model = VRF
    _modelname = "vrf"
    _identifiers = ("name", "namespace__name")
    _attributes = ("rd", "description", "system_of_record", "last_synced_from_sor")

    @classmethod
    def _get_queryset(cls, data=None):  # pylint: disable=unused-argument
        """Return queryset of VRFs that belong to Forward Enterprise."""
        return cls._model.objects.filter(_custom_field_data__system_of_record="Forward Enterprise")

    name: str
    namespace__name: str
    description: Optional[str] = ""
    rd: Optional[str] = ""
    tenant__name: Optional[str] = None
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create or update VRF, handling constraint violations gracefully."""
        if adapter.job:
            adapter.job.logger.info("Creating VRF: %s (Namespace: %s)", ids["name"], ids["namespace__name"])
        try:
            # Try to get existing VRF first
            namespace = Namespace.objects.get(name=ids["namespace__name"])
            existing_vrf = VRF.objects.filter(name=ids["name"], namespace=namespace).first()

            if existing_vrf:
                # Update any changed attributes, avoiding constraint violations
                for attr_name, attr_value in attrs.items():
                    if attr_name == "rd" and attr_value:
                        # Check if RD already exists for another VRF
                        rd_exists = VRF.objects.filter(rd=attr_value).exclude(pk=existing_vrf.pk).exists()
                        if not rd_exists:
                            existing_vrf.rd = attr_value
                    elif hasattr(existing_vrf, attr_name.replace("__", ".")):
                        setattr(existing_vrf, attr_name.replace("__", "."), attr_value)

                try:
                    existing_vrf.validated_save()
                except (ValueError, TypeError, AttributeError) as exception:
                    if adapter.job:
                        adapter.job.logger.warning("Could not update VRF %s: %s", ids["name"], exception)

                # Return DiffSync model instance for the existing VRF
                return cls(adapter=adapter, **ids, **attrs)

            # VRF doesn't exist, create normally with validation
            return super().create(adapter, ids, attrs)

        except (AttributeError, TypeError, ValueError, Namespace.DoesNotExist) as exception:
            if adapter.job:
                adapter.job.logger.warning("Error in VRF create method: %s, falling back to default create", exception)
            return super().create(adapter, ids, attrs)


class NautobotPrefixModel(NautobotModel):
    """Nautobot Prefix model for creating Prefixes in Nautobot."""

    _model = Prefix
    _modelname = "prefix"
    _identifiers = ("network", "prefix_length", "namespace__name")
    _attributes = (
        "description",
        "vrfs",
        "tenant__name",
        "status__name",
        "system_of_record",
        "last_synced_from_sor",
    )

    @classmethod
    def _get_queryset(cls, data=None):  # pylint: disable=unused-argument
        """Return queryset of Prefixes that belong to Forward Enterprise."""
        return cls._model.objects.filter(_custom_field_data__system_of_record="Forward Enterprise")

    network: str
    prefix_length: int
    namespace__name: str
    description: Optional[str] = ""
    vrfs: List[VRFDict] = Field(default_factory=list)
    tenant__name: Optional[str] = None
    status__name: str = "Active"
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None

    @staticmethod
    def _assign_vrfs_to_prefix(django_prefix, vrfs, adapter, log_prefix=""):
        """Assign VRFs to a Django Prefix object.

        This is a shared method used by both create() and the post-sync VRF assignment.
        Eliminates code duplication and ensures consistent VRF handling.

        Args:
            django_prefix: Django Prefix model instance
            vrfs: List of VRF references (dict or string format)
            adapter: DiffSync adapter instance
            log_prefix: Optional prefix for log messages

        Returns:
            tuple: (assigned_count, failed_count)
        """
        assigned_count = 0
        failed_count = 0

        for vrf_item in vrfs:
            # Handle dict format (VRFDict) - this is the expected format from the adapter
            if isinstance(vrf_item, dict):
                vrf_name = vrf_item.get("name")
                vrf_namespace = vrf_item.get("namespace__name")
            # Handle string format for backward compatibility
            elif isinstance(vrf_item, str) and "__" in vrf_item:
                vrf_name, vrf_namespace = vrf_item.split("__", 1)
            else:
                if adapter and adapter.job:
                    adapter.job.logger.warning(
                        f"{log_prefix}Invalid VRF format: {vrf_item}, expected dict or 'vrf_name__namespace_name' string"
                    )
                failed_count += 1
                continue

            if vrf_name and vrf_namespace:
                try:
                    namespace = Namespace.objects.get(name=vrf_namespace)
                    vrf_obj = VRF.objects.get(name=vrf_name, namespace=namespace)

                    # Check if already assigned to avoid duplicate additions
                    if not django_prefix.vrfs.filter(pk=vrf_obj.pk).exists():
                        django_prefix.vrfs.add(vrf_obj)
                        assigned_count += 1
                        if adapter and adapter.job:
                            adapter.job.logger.debug(
                                f"{log_prefix}Assigned VRF {vrf_name} to prefix {django_prefix.network}/{django_prefix.prefix_length}"
                            )

                except Namespace.DoesNotExist:
                    if adapter and adapter.job:
                        adapter.job.logger.warning(
                            f"{log_prefix}Namespace {vrf_namespace} does not exist for VRF {vrf_name}"
                        )
                    failed_count += 1
                except VRF.DoesNotExist:
                    if adapter and adapter.job:
                        adapter.job.logger.debug(
                            f"{log_prefix}VRF {vrf_name} (namespace: {vrf_namespace}) not yet created, will retry in post-sync"
                        )
                    failed_count += 1

        return assigned_count, failed_count

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create prefix with proper VRF assignment handling and graceful duplicate handling.

        VRF assignment is attempted during create but may fail if VRFs don't exist yet.
        The post-sync phase will retry any failed assignments after all objects are created.
        """
        if adapter.job:
            adapter.job.logger.info("Creating Prefix: %s/%s", ids["network"], ids["prefix_length"])
        try:
            # Remove vrfs from attrs temporarily to avoid contrib model processing
            vrfs = attrs.pop("vrfs", [])

            # Create the prefix without VRFs first
            new_prefix_obj = super().create(adapter, ids, attrs)

            # Handle VRF assignment if VRFs are specified
            if vrfs:
                try:
                    # Get the actual Django model instance
                    django_prefix = Prefix.objects.get(
                        network=ids["network"],
                        prefix_length=ids["prefix_length"],
                        namespace__name=ids["namespace__name"],
                    )

                    # Use shared method to assign VRFs (DRY principle)
                    assigned, failed = cls._assign_vrfs_to_prefix(django_prefix, vrfs, adapter)

                    if assigned > 0 and adapter.job:
                        adapter.job.logger.info(
                            f"Assigned {assigned} VRF(s) to prefix {ids['network']}/{ids['prefix_length']}"
                        )
                    if failed > 0 and adapter.job:
                        adapter.job.logger.debug(
                            f"Could not assign {failed} VRF(s) to prefix (will retry in post-sync)"
                        )

                except (KeyError, AttributeError, TypeError, ValueError) as exception:
                    if adapter.job:
                        adapter.job.logger.warning(f"Error assigning VRFs to prefix: {exception}")

            return new_prefix_obj

        except ObjectCrudException as exception:
            # Check if this is a duplicate prefix error
            error_msg = str(exception).lower()
            if "prefix" in error_msg and "already exists" in error_msg:
                # Prefix already exists, which is normal in sync scenarios
                # Return None to indicate no object was created (this is normal for DiffSync)
                return None

            # Re-raise if it's a different error
            raise
        except (KeyError, AttributeError, TypeError, ValueError) as exception:
            if adapter.job:
                adapter.job.logger.warning(
                    f"Error in prefix create method: {exception}, falling back to default create"
                )
            return super().create(adapter, ids, attrs)


class NautobotIPAddressModel(NautobotModel):
    """Nautobot IPAddress model for creating IP addresses in Nautobot."""

    _model = IPAddress
    _modelname = "ipaddress"
    _identifiers = ("host", "mask_length")
    _attributes = (
        "description",
        "status__name",
        "role",
        "dns_name",
        "tenant__name",
        "parent__network",
        "parent__prefix_length",
        "system_of_record",
        "last_synced_from_sor",
    )

    @classmethod
    def _get_queryset(cls, data=None):  # pylint: disable=unused-argument
        """Return queryset of IP Addresses that belong to Forward Enterprise."""
        return cls._model.objects.filter(_custom_field_data__system_of_record="Forward Enterprise")

    host: str
    mask_length: int
    description: Optional[str] = ""
    status__name: str = "Active"
    role: Optional[str] = None
    dns_name: Optional[str] = ""
    tenant__name: Optional[str] = None
    parent__network: str
    parent__prefix_length: int
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IP address with graceful duplicate handling."""
        if adapter.job:
            adapter.job.logger.info("Creating IP Address: %s/%s", ids["host"], ids["mask_length"])
        try:
            # Try to create the IP address normally
            return super().create(adapter, ids, attrs)
        except ObjectCrudException as exception:
            # Check if this is a duplicate IP address error
            error_msg = str(exception).lower()
            if "ip address" in error_msg and "already exists" in error_msg:
                # IP address already exists, which is normal in sync scenarios
                # Return None to indicate no object was created (this is normal for DiffSync)
                return None

            # Re-raise if it's a different error
            raise
        except (KeyError, AttributeError, TypeError, ValueError) as exception:
            if adapter.job:
                adapter.job.logger.warning(
                    f"Error in IP address create method: {exception}, falling back to default create"
                )
            return super().create(adapter, ids, attrs)


class NautobotIPAssignmentModel(NautobotModel):
    """Nautobot IPAddressToInterface model for assigning IPs to interfaces."""

    _model = IPAddressToInterface
    _modelname = "ipassignment"
    _identifiers = ("interface__device__name", "interface__name", "ip_address__host")
    _attributes = ()

    @classmethod
    def _get_queryset(cls, data=None):  # pylint: disable=unused-argument
        """Return queryset of IP assignments with Forward Enterprise system of record."""
        # Filter by IP addresses that belong to Forward Enterprise
        return cls._model.objects.filter(ip_address___custom_field_data__system_of_record="Forward Enterprise")

    interface__device__name: str
    interface__name: str
    ip_address__host: str

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddressToInterface assignment with graceful duplicate handling.

        Args:
            adapter: The DiffSync adapter
            ids: Dictionary of identifier values
            attrs: Dictionary of attribute values

        Returns:
            Created model instance or None if duplicate exists
        """
        try:
            return super().create(adapter, ids, attrs)
        except ObjectCrudException as exception:
            if "already exists" in str(exception).lower():
                # IP assignment already exists, return None silently
                # Return None to indicate no object was created (this is normal for DiffSync)
                return None

            # Re-raise if it's a different error
            raise
        except (KeyError, AttributeError, TypeError, ValueError) as exception:
            if adapter.job:
                adapter.job.logger.warning(
                    f"Error in IP assignment create method: {exception}, falling back to default create"
                )
            return super().create(adapter, ids, attrs)


class NautobotVLANModel(NautobotModel):
    """Nautobot VLAN model for creating VLANs in Nautobot."""

    _model = VLAN
    _modelname = "vlan"
    _identifiers = ("vid", "name", "vlan_group__name")
    _attributes = (
        "description",
        "status__name",
        "tenant__name",
        "role",
        "system_of_record",
        "last_synced_from_sor",
    )

    @classmethod
    def _get_queryset(cls, data=None):  # pylint: disable=unused-argument
        """Return queryset of VLANs that belong to Forward Enterprise."""
        return cls._model.objects.filter(_custom_field_data__system_of_record="Forward Enterprise")

    vid: int
    name: str
    vlan_group__name: str = constants.DEFAULT_VLAN_GROUP_NAME
    description: Optional[str] = ""
    status__name: str = "Active"
    tenant__name: Optional[str] = None
    role: Optional[str] = None
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None

    @classmethod
    def create(cls, adapter, ids, attrs):  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        """Create VLAN with proper VLAN group handling."""
        if adapter.job:
            adapter.job.logger.info("Creating VLAN: %s (VID: %s)", ids["name"], ids["vid"])
        try:
            # Ensure VLAN groups are allowed content types on Site location type,
            ensure_vlan_group_content_type_on_location_type("Site")

            # Get VLAN group name
            vlan_group_name = ids.get("vlan_group__name", "Forward Enterprise")

            # Extract location name from VLAN group name and get/create location
            location_name = extract_location_from_vlan_group_name(vlan_group_name)
            location, _ = get_or_create_location_for_vlan_group(location_name, adapter.job)

            # Get or create VLAN group for Forward Enterprise
            vlan_group_defaults = {"description": f"VLANs imported from Forward Enterprise for {vlan_group_name}"}
            if location:
                vlan_group_defaults["location"] = location

            vlan_group, created = VLANGroup.objects.get_or_create(
                name=vlan_group_name,
                defaults=vlan_group_defaults,
            )

            if created and adapter.job:
                adapter.job.logger.info(
                    f"Created VLAN group: {vlan_group_name} at location: {location_name if location else 'Unknown'}"
                )

            # Remove vlan_group__name from attrs as we'll set it directly
            attrs_copy = attrs.copy()
            attrs_copy.pop("vlan_group__name", None)

            # Create the VLAN with proper duplicate handling
            try:
                new_vlan_obj = super().create(adapter, ids, attrs_copy)
            except ObjectCrudException as exception:
                # Check if this is a duplicate VLAN error
                error_msg = str(exception).lower()
                if "vlan with this" in error_msg and "already exists" in error_msg:
                    # Return None to indicate no object was created (this is normal for DiffSync)
                    return None

                # Re-raise if it's a different error
                raise

            # Set the VLAN group on the actual Django model
            if new_vlan_obj:
                try:
                    new_vlan = VLAN.objects.get(vid=ids["vid"], name=ids["name"], vlan_group=vlan_group)
                    new_vlan.vlan_group = vlan_group
                    new_vlan.validated_save()
                except VLAN.DoesNotExist:
                    if adapter.job:
                        adapter.job.logger.warning(
                            f"Could not set VLAN group for VLAN {ids['vid']} in group {vlan_group_name}"
                        )

            return new_vlan_obj

        except (KeyError, AttributeError, TypeError, ValueError) as exception:
            if adapter.job:
                adapter.job.logger.warning(f"Error in VLAN create method: {exception}, falling back to default create")
            return super().create(adapter, ids, attrs)
