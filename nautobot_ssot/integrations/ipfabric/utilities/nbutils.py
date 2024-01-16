# pylint: disable=duplicate-code
"""Utility functions for Nautobot ORM."""
import datetime
from typing import Any, Optional

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from django.core.exceptions import ValidationError
from netutils.ip import netmask_to_cidr
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import (
    Device,
    DeviceType,
    Interface,
    Manufacturer,
    Location,
    LocationType,
)
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.models import CustomField, Role, Tag
from nautobot.extras.models.statuses import Status
from nautobot.ipam.models import IPAddress, IPAddressToInterface, Namespace, Prefix
from nautobot.ipam.choices import PrefixTypeChoices
from nautobot_ssot.integrations.ipfabric.constants import LAST_SYNCHRONIZED_CF_NAME


def create_location(location_name, location_id=None):
    """Creates a specified location in Nautobot.

    Args:
        location_name (str): Name of the location.
        location_id (str): ID of the location.
    """
    location_obj, _ = Location.objects.get_or_create(
        name=location_name,
        location_type=LocationType.objects.get(name="Site"),
        status=Status.objects.get(name="Active"),
    )
    if location_id:
        # Ensure custom field is available
        custom_field_obj, _ = CustomField.objects.get_or_create(
            type=CustomFieldTypeChoices.TYPE_TEXT,
            key="ipfabric_site_id",
            defaults={"label": "IPFabric Location ID"},
        )
        custom_field_obj.content_types.add(ContentType.objects.get_for_model(Location))
        location_obj.cf["ipfabric_site_id"] = location_id
        location_obj.validated_save()
    tag_object(nautobot_object=location_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
    return location_obj


def create_manufacturer(vendor_name):
    """Create specified manufacturer in Nautobot."""
    mf_name, _ = Manufacturer.objects.get_or_create(name=vendor_name)
    tag_object(nautobot_object=mf_name, custom_field=LAST_SYNCHRONIZED_CF_NAME)
    return mf_name


def create_device_type_object(device_type, vendor_name):
    """Create a specified device type in Nautobot.

    Args:
        device_type (str): Device model gathered from DiffSync model.
        vendor_name (str): Vendor Name
    """
    mf_name = create_manufacturer(vendor_name)
    device_type_obj, _ = DeviceType.objects.get_or_create(manufacturer=mf_name, model=device_type)
    tag_object(nautobot_object=device_type_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
    return device_type_obj


def get_or_create_device_role_object(role_name, role_color):
    """Create specified device role in Nautobot.

    Args:
        role_name (str): Role name.
        role_color (str): Role color.
    """
    # adds custom field to map custom role names to ipfabric type names
    try:
        role_obj = Role.objects.get(_custom_field_data__ipfabric_type=role_name)
    except Role.DoesNotExist:
        role_obj = Role.objects.create(name=role_name, color=role_color)
        role_obj.cf["ipfabric_type"] = role_name
        role_obj.validated_save()
        role_obj.content_types.set([ContentType.objects.get_for_model(Device)])
        tag_object(nautobot_object=role_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
    return role_obj


def create_status(status_name, status_color, description="", app_label="dcim", model="device"):
    """Verify status object exists in Nautobot. If not, creates specified status. Defaults to dcim | device.

    Args:
        status_name (str): Status name.
        status_color (str): Status color.
        description (str): Description
        app_label (str): App Label ("DCIM")
        model (str): Django Model ("DEVICE")
    """
    try:
        status_obj = Status.objects.get(name=status_name)
    except Status.DoesNotExist:
        content_type = ContentType.objects.get(app_label=app_label, model=model)
        status_obj = Status.objects.create(
            name=status_name,
            color=status_color,
            description=description,
        )
        status_obj.content_types.set([content_type])
    return status_obj


def create_ip(ip_address, subnet_mask, status="Active", object_pk=None):
    """Verify ip address exists in Nautobot. If not, creates specified ip.

    Utility behavior is manipulated by `settings` if duplicate ip's are allowed.

    Args:
        ip_address (str): IP address.
        subnet_mask (str): Subnet mask used for IP Address.
        status (str): Status to assign to IP Address.
        object_pk: Object primary key
    """
    status_obj = Status.objects.get_for_model(IPAddress).get(name=status)
    namespace_obj = Namespace.objects.get(name="Global")
    cidr = netmask_to_cidr(subnet_mask)
    try:
        ip_obj, _ = IPAddress.objects.get_or_create(address=f"{ip_address}/{cidr}", status=status_obj)
    except ValidationError:
        parent, _ = Prefix.objects.get_or_create(
            network="0.0.0.0",  # nosec B104
            prefix_length=0,
            type=PrefixTypeChoices.TYPE_NETWORK,
            status=Status.objects.get_for_model(Prefix).get(name="Active"),
            namespace=namespace_obj,
        )
        ip_obj, _ = IPAddress.objects.get_or_create(address=f"{ip_address}/{cidr}", status=status_obj, parent=parent)

    if object_pk:
        assign_ip = IPAddressToInterface(ip_address=ip_obj, interface_id=object_pk.pk)
        assign_ip.validated_save()
        # Tag Interface (object_pk)
        tag_object(nautobot_object=object_pk, custom_field=LAST_SYNCHRONIZED_CF_NAME)

    # Tag IP Addr
    tag_object(nautobot_object=ip_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
    return ip_obj


def create_interface(device_obj, interface_details):
    """Verify interface exists on specified device. If not, creates interface.

    Args:
        device_obj (Device): Device object to check interface against.
        interface_details (dict): interface details.
    """
    interface_fields = (
        "name",
        "description",
        "enabled",
        "mac_address",
        "mtu",
        "type",
        "mgmt_only",
        "status",
    )
    fields = {k: v for k, v in interface_details.items() if k in interface_fields and v}
    try:
        fields["status"] = Status.objects.get_for_model(Interface).get(name=fields.get(fields["status"], "Active"))
        interface_obj, _ = device_obj.interfaces.get_or_create(**fields)
    except IntegrityError:
        interface_obj, _ = device_obj.interfaces.get_or_create(name=fields["name"])
        interface_obj.description = fields.get("description", "")
        interface_obj.enabled = fields.get("enabled")
        interface_obj.mac_address = fields.get("mac_address")
        interface_obj.mtu = fields.get("mtu")
        interface_obj.type = fields.get("type")
        interface_obj.mgmt_only = fields.get("mgmt_only", False)
        interface_obj.status = Status.objects.get_for_model(Interface).get(name=fields.get("status", "Active"))
        interface_obj.validated_save()
    tag_object(nautobot_object=interface_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
    return interface_obj


def create_vlan(vlan_name: str, vlan_id: int, vlan_status: str, location_obj: Location, description: str):
    """Creates or obtains VLAN object.

    Args:
        vlan_name (str): VLAN Name
        vlan_id (int): VLAN ID
        vlan_status (str): VLAN Status
        location_obj (Location): Location Django Model
        description (str): VLAN Description

    Returns:
        (VLAN): Returns created or obtained VLAN object.
    """
    vlan_obj, _ = location_obj.vlans.get_or_create(
        name=vlan_name, vid=vlan_id, status=Status.objects.get(name=vlan_status), description=description
    )
    tag_object(nautobot_object=vlan_obj, custom_field=LAST_SYNCHRONIZED_CF_NAME)
    return vlan_obj


def tag_object(nautobot_object: Any, custom_field: str, tag_name: Optional[str] = "SSoT Synced from IPFabric"):
    """Apply the given tag and custom field to the identified object.

    Args:
        nautobot_object (Any): Nautobot ORM Object
        custom_field (str): Name of custom field to update
        tag_name (Optional[str], optional): Tag name. Defaults to "SSoT Synced From IPFabric".
    """
    if tag_name == "SSoT Synced from IPFabric":
        tag, _ = Tag.objects.get_or_create(
            name="SSoT Synced from IPFabric",
            defaults={
                "description": "Object synced at some point from IPFabric to Nautobot",
                "color": ColorChoices.COLOR_LIGHT_GREEN,
            },
        )
    else:
        tag, _ = Tag.objects.get_or_create(name=tag_name)

    today = datetime.date.today().isoformat()

    def _tag_object(nautobot_object):
        """Apply custom field and tag to object, if applicable."""
        if hasattr(nautobot_object, "tags"):
            nautobot_object.tags.add(tag)
        if hasattr(nautobot_object, "cf"):
            # Update custom field date stamp
            nautobot_object.cf["system_of_record"] = "IPFabric"
            nautobot_object.cf[custom_field] = today
        nautobot_object.validated_save()

    _tag_object(nautobot_object)
    # Ensure proper save
