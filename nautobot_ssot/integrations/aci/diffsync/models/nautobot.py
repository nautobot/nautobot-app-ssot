"""Nautobot Models for Cisco ACI integration with SSoT plugin."""

import logging
from diffsync.exceptions import ObjectNotCreated
from django.utils.text import slugify
from django.contrib.contenttypes.models import ContentType
from nautobot.tenancy.models import Tenant as OrmTenant
from nautobot.dcim.models import DeviceType as OrmDeviceType
from nautobot.dcim.models import DeviceRole as OrmDeviceRole
from nautobot.dcim.models import Device as OrmDevice
from nautobot.dcim.models import InterfaceTemplate as OrmInterfaceTemplate
from nautobot.dcim.models import Interface as OrmInterface
from nautobot.ipam.models import IPAddress as OrmIPAddress
from nautobot.ipam.models import Prefix as OrmPrefix
from nautobot.ipam.models import VRF as OrmVrf
from nautobot.dcim.models import Manufacturer
from nautobot.dcim.models import Site
from nautobot.extras.models import Status
from nautobot.extras.models import Tag
from nautobot_ssot_aci.diffsync.models.base import (
    Tenant,
    Vrf,
    DeviceType,
    DeviceRole,
    Device,
    InterfaceTemplate,
    Interface,
    IPAddress,
    Prefix,
)
from nautobot_ssot_aci.constant import PLUGIN_CFG


logger = logging.getLogger("rq.worker")


class NautobotTenant(Tenant):
    """Nautobot implementation of the Tenant Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Tenant object in Nautobot."""
        _tenant = OrmTenant(name=ids["name"], description=attrs["description"], comments=attrs["comments"])
        _tenant.tags.add(Tag.objects.get(slug=PLUGIN_CFG.get("tag").lower().replace(" ", "-")))
        _tenant.tags.add(Tag.objects.get(name=attrs["site_tag"]))
        _tenant.validated_save()
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Tenant object in Nautobot."""
        _tenant = OrmTenant.objects.get(name=self.name)
        if attrs.get("description"):
            _tenant.description = attrs["description"]
        if attrs.get("comments"):
            _tenant.comments = attrs["comments"]
        _tenant.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Tenant object in Nautobot."""
        self.diffsync.job.log_warning(f"Tenant {self.name} will be deleted.")
        super().delete()
        _tenant = OrmTenant.objects.get(name=self.get_identifiers()["name"])
        self.diffsync.objects_to_delete["tenant"].append(_tenant)
        return self


class NautobotVrf(Vrf):
    """Nautobot implementation of the VRF Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create VRF object in Nautobot."""
        _tenant = OrmTenant.objects.get(name=ids["tenant"])
        _vrf = OrmVrf(name=ids["name"], tenant=_tenant)
        _vrf.tags.add(Tag.objects.get(slug=PLUGIN_CFG.get("tag").lower().replace(" ", "-")))
        _vrf.tags.add(Tag.objects.get(name=attrs["site_tag"]))
        _vrf.validated_save()
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update VRF object in Nautobot."""
        _tenant = OrmTenant.objects.get(name=self.tenant)
        _vrf = OrmVrf.objects.get(name=self.name, tenant=_tenant)
        if attrs.get("description"):
            _vrf.description = attrs["description"]
            self.diffsync.job.log_success(
                obj=_vrf, message=f"VRF Update tenant: {_tenant} vrf: {_vrf} desc: {_vrf.description}"
            )
        if attrs.get("rd"):
            _vrf.rd = attrs["rd"]
        _vrf.validated_save()
        self.diffsync.job.log_success(obj=_vrf, message=f"VRF updated for tenant: {_tenant}")
        return super().update(attrs)

    def delete(self):
        """Delete VRF object in Nautobot."""
        self.diffsync.job.log_warning(f"VRF {self.name} will be deleted.")
        super().delete()
        _tenant = OrmTenant.objects.get(name=self.tenant)
        _vrf = OrmVrf.objects.get(name=self.name, tenant=_tenant)
        self.diffsync.objects_to_delete["vrf"].append(_vrf)  # pylint: disable=protected-access
        return self


class NautobotDeviceType(DeviceType):
    """Nautobot implementation of the DeviceType Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create DeviceType object in Nautobot."""
        _devicetype = OrmDeviceType(
            model=ids["model"],
            manufacturer=Manufacturer.objects.get(name=attrs["manufacturer"]),
            part_number=ids["part_nbr"],
            u_height=attrs["u_height"],
            comments=attrs["comments"],
        )
        _tag = Tag.objects.get(slug=slugify(PLUGIN_CFG.get("tag")))
        _devicetype.tags.add(_tag)
        _devicetype.validated_save()

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update DeviceType object in Nautobot."""
        _devicetype = OrmDeviceType.objects.get(model=self.model)
        if attrs.get("manufacturer"):
            _devicetype.manufacturer = Manufacturer.objects.get(name=attrs["manufacturer"])
        if attrs.get("comments"):
            _devicetype.comments = attrs["comments"]
        if attrs.get("u_height"):
            _devicetype.u_height = attrs["u_height"]
        _devicetype.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete DeviceType object in Nautobot."""
        self.diffsync.job.log_warning(f"Device Type {self.model} will be deleted.")
        _devicetype = OrmDeviceType.objects.get(model=self.get_identifiers()["model"])
        _devicetype.delete()
        return super().delete()


class NautobotDeviceRole(DeviceRole):
    """Nautobot implementation of the DeviceRole Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create DeviceRole object in Nautobot."""
        _ids_name = ids["name"]
        _devicerole = OrmDeviceRole(name=_ids_name, slug=f"{_ids_name}-ssot-aci", description=attrs["description"])
        _devicerole.validated_save()
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update DeviceRole object in Nautobot."""
        _devicerole = OrmDeviceRole.objects.get(name=self.name)
        if attrs.get("description"):
            _devicerole.description = attrs["description"]
        _devicerole.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete DeviceRole object in Nautobot."""
        self.diffsync.job.log_warning(f"Device Role {self.name} will be deleted.")
        _devicerole = OrmDeviceRole.objects.get(name=self.get_identifiers()["name"])
        _devicerole.delete()
        return super().delete()


class NautobotDevice(Device):
    """Nautobot implementation of the Device Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Device object in Nautobot."""
        _device = OrmDevice(
            name=ids["name"],
            device_role=OrmDeviceRole.objects.get(name=attrs["device_role"]),
            device_type=OrmDeviceType.objects.get(model=attrs["device_type"]),
            serial=attrs["serial"],
            comments=attrs["comments"],
            site=Site.objects.get(name=ids["site"]),
            status=Status.objects.get(name="Active"),
        )

        _device.custom_field_data["aci_node_id"] = attrs["node_id"]
        _device.custom_field_data["aci_pod_id"] = attrs["pod_id"]
        _device.tags.add(Tag.objects.get(slug=PLUGIN_CFG.get("tag").lower().replace(" ", "-")))
        _device.tags.add(Tag.objects.get(name=attrs["site_tag"]))
        _device.validated_save()
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Device object in Nautobot."""
        _device = OrmDevice.objects.get(name=self.name, site=Site.objects.get(name=self.get_identifiers()["site"]))
        if attrs.get("serial"):
            _device.serial = attrs["serial"]
        if attrs.get("device_type"):
            _device.device_type = OrmDeviceType.objects.get(model=attrs["device_type"])
        if attrs.get("device_role"):
            _device.device_role = OrmDeviceRole.objects.get(name=attrs["device_role"])
        if attrs.get("comments"):
            _device.comments = attrs["comments"]
        if attrs.get("node_id"):
            _device.custom_field_data["aci_node_id"] = attrs["node_id"]
        if attrs.get("pod_id"):
            _device.custom_field_data["aci_pod_id"] = attrs["pod_id"]
        _device.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Device object in Nautobot."""
        self.diffsync.job.log_warning(f"Device {self.name} will be deleted.")
        super().delete()
        _device = OrmDevice.objects.get(name=self.name, site=Site.objects.get(name=self.site))
        self.diffsync.objects_to_delete["device"].append(_device)  # pylint: disable=protected-access
        return self


class NautobotInterfaceTemplate(InterfaceTemplate):
    """Nautobot implementation of the InterfaceTemplate Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create InterfaceTemplate object in Nautobot."""
        _interfacetemplate = OrmInterfaceTemplate(
            device_type=OrmDeviceType.objects.get(model=ids["device_type"]),
            name=ids["name"],
            type=ids["type"],
            mgmt_only=attrs["mgmt_only"],
        )
        _interfacetemplate.validated_save()

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update InterfaceTemplate object in Nautobot."""
        _interfacetemplate = OrmInterfaceTemplate.objects.get(
            name=self.get_identifiers()["name"],
            device_type=OrmDeviceType.objects.get(model=self.get_identifiers()["device_type"]),
        )
        if attrs.get("mgmt_only"):
            _interfacetemplate.mgmt_only = attrs["mgmt_only"]
        _interfacetemplate.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete InterfaceTemplate object in Nautobot."""
        self.diffsync.job.log_warning(f"Interface Template {self.name} will be deleted.")
        _interfacetemplate = OrmInterfaceTemplate.objects.get(
            name=self.get_identifiers()["name"],
            device_type=OrmDeviceType.objects.get(model=self.get_identifiers()["device_type"]),
        )
        _interfacetemplate.delete()
        return super().delete()


class NautobotInterface(Interface):
    """Nautobot implementation of the Interface Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Interface object in Nautobot."""
        _interface = OrmInterface(
            name=ids["name"],
            device=OrmDevice.objects.get(name=ids["device"], site=Site.objects.get(name=ids["site"])),
            description=attrs["description"],
            type=attrs["type"],
        )
        _interface.custom_field_data["gbic_vendor"] = attrs["gbic_vendor"]
        _interface.custom_field_data["gbic_sn"] = attrs["gbic_sn"]
        _interface.custom_field_data["gbic_type"] = attrs["gbic_type"]
        _interface.custom_field_data["gbic_model"] = attrs["gbic_model"]
        if attrs.get("state") == "up":
            _interface.tags.add(Tag.objects.get(slug=PLUGIN_CFG.get("tag_up").lower().replace(" ", "-")))
        else:
            _interface.tags.add(Tag.objects.get(slug=PLUGIN_CFG.get("tag_down").lower().replace(" ", "-")))
        _interface.tags.add(Tag.objects.get(name=attrs["site_tag"]))
        _interface.validated_save()
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Interface object in Nautobot."""
        _interface = OrmInterface.objects.get(
            name=self.get_identifiers()["name"],
            device=OrmDevice.objects.get(
                name=self.get_identifiers()["device"], site=Site.objects.get(name=self.get_identifiers()["site"])
            ),
        )
        if attrs.get("description"):
            _interface.description = attrs["description"]
        if attrs.get("type"):
            _interface.type = attrs["type"]
        if attrs.get("gbic_vendor"):
            _interface.custom_field_data["gbic_vendor"] = attrs["gbic_vendor"]
        if attrs.get("gbic_type"):
            _interface.custom_field_data["gbic_type"] = attrs["gbic_type"]
        if attrs.get("gbic_sn"):
            _interface.custom_field_data["gbic_sn"] = attrs["gbic_sn"]
        if attrs.get("gbic_model"):
            _interface.custom_field_data["gbic_model"] = attrs["gbic_model"]
        if attrs.get("state") == "up":
            _interface.tags.add(Tag.objects.get(slug=PLUGIN_CFG.get("tag_up").lower().replace(" ", "-")))
            _interface.tags.remove(Tag.objects.get(slug=PLUGIN_CFG.get("tag_down").lower().replace(" ", "-")))
        else:
            _interface.tags.add(Tag.objects.get(slug=PLUGIN_CFG.get("tag_down").lower().replace(" ", "-")))
            _interface.tags.remove(Tag.objects.get(slug=PLUGIN_CFG.get("tag_up").lower().replace(" ", "-")))
        _interface.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Interface object in Nautobot."""
        self.diffsync.job.log_warning(f"Interface {self.name} will be deleted.")
        try:
            device = OrmDevice.objects.get(
                name=self.get_identifiers()["device"], site=Site.objects.get(name=self.get_identifiers()["site"])
            )
        except OrmDevice.DoesNotExist:
            self.diffsync.job.log_warning(
                f"Device {self.get_identifiers()['device']} does not exist, skipping deletion of interface {self.name}"
            )
        else:
            _interface = OrmInterface.objects.get(name=self.get_identifiers()["name"], device=device)
            _interface.delete()
        return super().delete()


class NautobotIPAddress(IPAddress):
    """Nautobot implementation of the IPAddress Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create IPAddress object in Nautobot."""
        _device = attrs["device"]
        _interface = attrs["interface"]
        if attrs["device"] and attrs["interface"]:
            obj_type = ContentType.objects.get(model="interface")
            try:
                obj_id = (
                    OrmDevice.objects.get(name=attrs["device"], site=Site.objects.get(name=ids["site"]))
                    .interfaces.get(name=attrs["interface"])
                    .id
                )
            except ObjectNotCreated:
                diffsync.job.log_warning(message=f"{_device} creating interface {_interface}")
        else:
            obj_type = None
            obj_id = None
        if ids["tenant"]:
            tenant_name = OrmTenant.objects.get(name=ids["tenant"])
        else:
            tenant_name = None
        try:
            vrf_tenant = OrmTenant.objects.get(name=attrs["vrf_tenant"])
        except OrmTenant.DoesNotExist:
            diffsync.job.log_warning(message=f"Tenant {attrs['vrf_tenant']} not found for VRF {ids['vrf']}")
            vrf_tenant = None

        if ids["vrf"] and vrf_tenant:
            try:
                vrf_name = OrmVrf.objects.get(name=ids["vrf"], tenant=OrmTenant.objects.get(name=vrf_tenant))
            except OrmVrf.DoesNotExist:
                diffsync.job.log_warning(message=f"VRF {ids['vrf']} not found to associate IP Address {ids['address']}")
                vrf_name = None

        else:
            vrf_name = None

        _ipaddress = OrmIPAddress(
            address=ids["address"],
            status=Status.objects.get(name=attrs["status"]),
            description=attrs["description"],
            tenant=tenant_name,
            assigned_object_type=obj_type,
            assigned_object_id=obj_id,
            vrf=vrf_name,
        )
        _ipaddress.tags.add(Tag.objects.get(slug=PLUGIN_CFG.get("tag").lower().replace(" ", "-")))
        _ipaddress.tags.add(Tag.objects.get(name=attrs["site_tag"]))
        _ipaddress.validated_save()
        # Update device with newly created address in the "Primary IPv4 field"
        if attrs["device"]:
            device = OrmDevice.objects.get(name=attrs["device"], site=Site.objects.get(name=ids["site"]))
            device.primary_ip4 = OrmIPAddress.objects.get(address=ids["address"])
            device.save()
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update IPAddress object in Nautobot."""
        _ipaddress = OrmIPAddress.objects.get(address=self.address)
        if attrs.get("description"):
            _ipaddress.description = attrs["description"]
        if attrs.get("tenant"):
            _ipaddress.tenant = OrmTenant.objects.get(name=self.get_identifiers()["tenant"])
        if attrs.get("device") and attrs.get("interface"):
            _ipaddress.assigned_object_type = ContentType.objects.get(model="interface")
            _ipaddress.assigned_object_id = (
                OrmDevice.objects.get(name=attrs["device"], site=self.get_identifiers()["site"])
                .interfaces.get(name=attrs["interface"])
                .id
            )
        if attrs.get("status"):
            _ipaddress.status = Status.objects.get(name=attrs["status"])
        if attrs.get("tenant"):
            _ipaddress.tenant = OrmTenant.objects.get(name=self.get_identifiers()["tenant"])
        if attrs.get("vrf") and attrs.get("vrf_tenant"):
            _ipaddress.vrf = OrmVrf.objects.get(
                name=self.get_identifiers()["vrf"],
                tenant=OrmTenant.objects.get(name=self.get_identifiers()["vrf_tenant"]),
            )
        _ipaddress.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete IPAddress object in Nautobot."""
        self.diffsync.job.log_warning(f"IP Address {self.address} will be deleted.")
        super().delete()
        _ipaddress = OrmIPAddress.objects.get(
            address=self.get_identifiers()["address"],
            tenant=OrmTenant.objects.get(name=self.tenant),
            vrf=OrmVrf.objects.get(name=self.vrf, tenant=OrmTenant.objects.get(name=self.vrf_tenant)),
        )
        self.diffsync.objects_to_delete["ipaddress"].append(_ipaddress)  # pylint: disable=protected-access
        return self


class NautobotPrefix(Prefix):
    """Nautobot implementation of the Prefix Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Prefix object in Nautobot."""
        try:
            vrf_tenant = OrmTenant.objects.get(name=attrs["vrf_tenant"])
        except OrmTenant.DoesNotExist:
            diffsync.job.log_warning(message=f"Tenant {attrs['vrf_tenant']} not found for VRF {attrs['vrf']}")
            vrf_tenant = None

        if ids["vrf"] and vrf_tenant:
            try:
                vrf = OrmVrf.objects.get(name=ids["vrf"], tenant=OrmTenant.objects.get(name=attrs["vrf_tenant"]))
            except OrmVrf.DoesNotExist:
                diffsync.job.log_warning(message=f"VRF {ids['vrf']} not found to associate prefix {ids['prefix']}")
                vrf = None
        else:
            vrf = None
        _prefix = OrmPrefix(
            prefix=ids["prefix"],
            status=Status.objects.get(name=attrs["status"]),
            description=attrs["description"],
            tenant=OrmTenant.objects.get(name=ids["tenant"]),
            site=Site.objects.get(name=ids["site"]),
            vrf=vrf,
        )
        _prefix.tags.add(Tag.objects.get(slug=PLUGIN_CFG.get("tag").lower().replace(" ", "-")))
        _prefix.tags.add(Tag.objects.get(name=attrs["site_tag"]))
        _prefix.validated_save()
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Prefix object in Nautobot."""
        _tenant = OrmTenant.objects.get(name=self.tenant)
        _prefix = OrmPrefix.objects.get(prefix=self.prefix, tenant=_tenant)

        if attrs.get("description"):
            _prefix.description = attrs["description"]
        if attrs.get("tenant"):
            _prefix.tenant = OrmTenant.objects.get(name=self.get_identifiers()["tenant"])
        if attrs.get("status"):
            _prefix.status = Status.objects.get(name=attrs["status"])
        if self.get_identifiers().get("vrf") and attrs.get("vrf_tenant"):
            _prefix.vrf = OrmVrf.objects.get(
                name=self.get_identifiers()["vrf"], tenant=OrmTenant.objects.get(name=attrs["vrf_tenant"])
            )
        _prefix.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Prefix object in Nautobot."""
        self.diffsync.job.log_warning(f"Prefix {self.prefix} will be deleted.")
        super().delete()
        _prefix = OrmPrefix.objects.get(
            prefix=self.get_identifiers()["prefix"],
            tenant=OrmTenant.objects.get(name=self.tenant),
            vrf=OrmVrf.objects.get(name=self.vrf, tenant=OrmTenant.objects.get(name=self.vrf_tenant)),
        )
        self.diffsync.objects_to_delete["prefix"].append(_prefix)  # pylint: disable=protected-access
        return self


NautobotDevice.update_forward_refs()
NautobotDeviceType.update_forward_refs()
