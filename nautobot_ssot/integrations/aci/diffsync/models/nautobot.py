"""Nautobot Models for Cisco ACI integration with SSoT app."""

import logging
from ipaddress import ip_network
from django.contrib.contenttypes.models import ContentType
from nautobot.tenancy.models import Tenant as OrmTenant
from nautobot.dcim.models import DeviceType as OrmDeviceType
from nautobot.dcim.models import Device as OrmDevice
from nautobot.dcim.models import InterfaceTemplate as OrmInterfaceTemplate
from nautobot.dcim.models import Interface as OrmInterface
from nautobot.dcim.models import Location, LocationType
from nautobot.ipam.models import IPAddress as OrmIPAddress
from nautobot.ipam.models import Namespace, IPAddressToInterface, VLAN
from nautobot.ipam.models import Prefix as OrmPrefix
from nautobot.ipam.models import VRF as OrmVrf
from nautobot_ssot.models import AppProfile as OrmAppProfile
from nautobot_ssot.models import BridgeDomain as OrmBridgeDomain
from nautobot_ssot.models import EPG as OrmEPG
from nautobot_ssot.models import EPGPath as OrmEPGPath
from nautobot.dcim.models import Manufacturer
from nautobot.extras.models import Role, Status, Tag
from nautobot_ssot.integrations.aci.diffsync.models.base import (
    Tenant,
    Vrf,
    DeviceType,
    DeviceRole,
    Device,
    InterfaceTemplate,
    Interface,
    IPAddress,
    Prefix,
    AppProfile,
    BridgeDomain,
    EPG,
    EPGPath,
)
from nautobot_ssot.integrations.aci.constant import PLUGIN_CFG


logger = logging.getLogger(__name__)


class NautobotTenant(Tenant):
    """Nautobot implementation of the Tenant Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Tenant object in Nautobot."""
        _tenant = OrmTenant(name=ids["name"], description=attrs["description"], comments=attrs["comments"])
        _tenant.tags.add(Tag.objects.get(name=PLUGIN_CFG.get("tag")))
        _tenant.tags.add(Tag.objects.get(name=attrs["site_tag"]))
        _tenant.validated_save()

        Namespace.objects.create(name=ids["name"])
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
        self.diffsync.job.logger.warning(f"Tenant {self.name} will be deleted.")
        super().delete()
        _tenant = OrmTenant.objects.get(name=self.name)
        self.diffsync.objects_to_delete["tenant"].append(_tenant)
        return self


class NautobotVrf(Vrf):
    """Nautobot implementation of the VRF Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create VRF object in Nautobot."""
        _tenant = OrmTenant.objects.get(name=ids["tenant"])
        _vrf = OrmVrf(name=ids["name"], tenant=_tenant, namespace=Namespace.objects.get(name=attrs["namespace"]))
        _vrf.tags.add(Tag.objects.get(name=PLUGIN_CFG.get("tag")))
        _vrf.tags.add(Tag.objects.get(name=attrs["site_tag"]))
        _vrf.validated_save()
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update VRF object in Nautobot."""
        _tenant = OrmTenant.objects.get(name=self.tenant)
        _vrf = OrmVrf.objects.get(name=self.name, tenant=_tenant)
        if attrs.get("description"):
            _vrf.description = attrs["description"]
            self.diffsync.job.logger.info(f"VRF Update tenant: {_tenant} vrf: {_vrf} desc: {_vrf.description}")
        if attrs.get("rd"):
            _vrf.rd = attrs["rd"]
        _vrf.validated_save()
        self.diffsync.job.logger.info(f"VRF updated for tenant: {_tenant}")
        return super().update(attrs)

    def delete(self):
        """Delete VRF object in Nautobot."""
        self.diffsync.job.logger.warning(f"VRF {self.name} will be deleted.")
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
        _tag = Tag.objects.get(name=PLUGIN_CFG.get("tag"))
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
        self.diffsync.job.logger.warning(f"Device Type {self.model} will be deleted.")
        _devicetype = OrmDeviceType.objects.get(model=self.model)
        _devicetype.delete()
        return super().delete()


class NautobotDeviceRole(DeviceRole):
    """Nautobot implementation of the DeviceRole Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create DeviceRole object in Nautobot."""
        _devicerole = Role.objects.create(name=ids["name"], description=attrs["description"])
        _devicerole.content_types.add(ContentType.objects.get_for_model(OrmDevice))
        _devicerole.validated_save()
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update DeviceRole object in Nautobot."""
        _devicerole = Role.objects.get(name=self.name)
        if attrs.get("description"):
            _devicerole.description = attrs["description"]
        _devicerole.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete DeviceRole object in Nautobot."""
        self.diffsync.job.logger.warning(f"Device Role {self.name} will be deleted.")
        _devicerole = Role.objects.get(name=self.name)
        _devicerole.delete()
        return super().delete()


class NautobotDevice(Device):
    """Nautobot implementation of the Device Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Device object in Nautobot."""
        _device = OrmDevice(
            name=ids["name"],
            role=Role.objects.get(name=attrs["device_role"]),
            device_type=OrmDeviceType.objects.get(model=attrs["device_type"]),
            serial=attrs["serial"],
            comments=attrs["comments"],
            location=Location.objects.get(name=ids["site"], location_type=LocationType.objects.get(name="Site")),
            status=Status.objects.get(name="Active"),
        )

        _device.custom_field_data["aci_node_id"] = attrs["node_id"]
        _device.custom_field_data["aci_pod_id"] = attrs["pod_id"]
        _device.tags.add(Tag.objects.get(name=PLUGIN_CFG.get("tag")))
        _device.tags.add(Tag.objects.get(name=attrs["site_tag"]))
        _device.validated_save()
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Device object in Nautobot."""
        _device = OrmDevice.objects.get(
            name=self.name,
            location=Location.objects.get(name=self.site, location_type=LocationType.objects.get(name="Site")),
        )
        if attrs.get("serial"):
            _device.serial = attrs["serial"]
        if attrs.get("device_type"):
            _device.device_type = OrmDeviceType.objects.get(model=attrs["device_type"])
        if attrs.get("device_role"):
            _device.role = Role.objects.get(name=attrs["device_role"])
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
        self.diffsync.job.logger.warning(f"Device {self.name} will be deleted.")
        super().delete()
        _device = OrmDevice.objects.get(
            name=self.name,
            location=Location.objects.get(name=self.site, location_type=LocationType.objects.get(name="Site")),
        )
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
            name=self.name,
            device_type=OrmDeviceType.objects.get(model=self.device_type),
        )
        if attrs.get("mgmt_only"):
            _interfacetemplate.mgmt_only = attrs["mgmt_only"]
        _interfacetemplate.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete InterfaceTemplate object in Nautobot."""
        self.diffsync.job.logger.warning(f"Interface Template {self.name} will be deleted.")
        _interfacetemplate = OrmInterfaceTemplate.objects.get(
            name=self.name,
            device_type=OrmDeviceType.objects.get(model=self.device_type),
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
            device=OrmDevice.objects.get(
                name=ids["device"],
                location=Location.objects.get(name=ids["site"], location_type=LocationType.objects.get(name="Site")),
            ),
            description=attrs["description"],
            status=Status.objects.get(name="Active") if attrs["state"] == "up" else Status.objects.get(name="Failed"),
            type=attrs["type"],
        )
        _interface.custom_field_data["gbic_vendor"] = attrs["gbic_vendor"]
        _interface.custom_field_data["gbic_sn"] = attrs["gbic_sn"]
        _interface.custom_field_data["gbic_type"] = attrs["gbic_type"]
        _interface.custom_field_data["gbic_model"] = attrs["gbic_model"]
        if attrs.get("state") == "up":
            _interface.tags.add(Tag.objects.get(name=PLUGIN_CFG.get("tag_up")))
        else:
            _interface.tags.add(Tag.objects.get(name=PLUGIN_CFG.get("tag_down")))
        _interface.tags.add(Tag.objects.get(name=attrs["site_tag"]))
        _interface.validated_save()
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Interface object in Nautobot."""
        _interface = OrmInterface.objects.get(
            name=self.name,
            device=OrmDevice.objects.get(
                name=self.device,
                location=Location.objects.get(name=self.site, location_type=LocationType.objects.get(name="Site")),
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
            _interface.tags.add(Tag.objects.get(name=PLUGIN_CFG.get("tag_up")))
            _interface.tags.remove(Tag.objects.get(name=PLUGIN_CFG.get("tag_down")))
        else:
            _interface.tags.add(Tag.objects.get(name=PLUGIN_CFG.get("tag_down")))
            _interface.tags.remove(Tag.objects.get(name=PLUGIN_CFG.get("tag_up")))
        _interface.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Interface object in Nautobot."""
        self.diffsync.job.logger.warning(f"Interface {self.name} will be deleted.")
        try:
            device = OrmDevice.objects.get(
                name=self.device,
                location=Location.objects.get(name=self.site, location_type=LocationType.objects.get(name="Site")),
            )
        except OrmDevice.DoesNotExist:
            self.diffsync.job.logger.warning(
                f"Device {self.device} does not exist, skipping deletion of interface {self.name}"
            )
        else:
            _interface = OrmInterface.objects.get(name=self.name, device=device)
            _interface.delete()
        return super().delete()


class NautobotIPAddress(IPAddress):
    """Nautobot implementation of the IPAddress Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create IPAddress object in Nautobot."""
        _device = attrs["device"]
        _interface = attrs["interface"]
        intf = None
        if attrs["device"] and attrs["interface"]:
            try:
                intf = OrmInterface.objects.get(name=_interface, device__name=_device)
            except OrmInterface.DoesNotExist:
                diffsync.job.logger.warning(f"{_device} missing interface {_interface} to assign {ids['address']}")
        if ids["tenant"]:
            tenant_name = OrmTenant.objects.get(name=ids["tenant"])
        else:
            tenant_name = None

        namespace = Namespace.objects.get(name=ids["namespace"])
        _ipaddress = OrmIPAddress.objects.create(
            address=ids["address"],
            status=Status.objects.get(name=attrs["status"]),
            description=attrs["description"],
            namespace=namespace,
            parent=OrmPrefix.objects.get(prefix=attrs["prefix"], namespace=namespace),
            tenant=tenant_name,
        )
        if intf:
            mapping = IPAddressToInterface.objects.create(ip_address=_ipaddress, interface=intf)
            mapping.validated_save()
        _ipaddress.tags.add(Tag.objects.get(name=PLUGIN_CFG.get("tag")))
        _ipaddress.tags.add(Tag.objects.get(name=attrs["site_tag"]))
        _ipaddress.validated_save()
        # Update device with newly created address in the "Primary IPv4 field"
        if attrs["device"]:
            device = OrmDevice.objects.get(
                name=_device,
                location=Location.objects.get(name=ids["site"], location_type=LocationType.objects.get(name="Site")),
            )
            device.primary_ip4 = OrmIPAddress.objects.get(address=ids["address"])
            device.save()
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update IPAddress object in Nautobot."""
        _ipaddress = OrmIPAddress.objects.get(address=self.address)
        if attrs.get("description"):
            _ipaddress.description = attrs["description"]
        if attrs.get("tenant"):
            _ipaddress.tenant = OrmTenant.objects.get(name=self.tenant)
        if attrs.get("device") and attrs.get("interface"):
            intf = OrmInterface.objects.get(name=attrs["interface"], device__name=attrs["device"])
            mapping = IPAddressToInterface.objects.create(ip_address=_ipaddress, interface=intf)
            mapping.validated_save()
        if attrs.get("status"):
            _ipaddress.status = Status.objects.get(name=attrs["status"])
        if attrs.get("tenant"):
            _ipaddress.tenant = OrmTenant.objects.get(name=self.tenant)
        _ipaddress.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete IPAddress object in Nautobot."""
        self.diffsync.job.logger.warning(f"IP Address {self.address} will be deleted.")
        super().delete()
        _ipaddress = OrmIPAddress.objects.get(
            address=self.address,
            tenant=OrmTenant.objects.get(name=self.tenant),
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
            diffsync.job.logger.warning(f"Tenant {attrs['vrf_tenant']} not found for VRF") # modified to avoid Key Error
            vrf_tenant = None

        if ids["vrf"] and vrf_tenant:
            try:
                vrf = OrmVrf.objects.get(name=ids["vrf"], tenant=OrmTenant.objects.get(name=attrs["vrf_tenant"]))
            except OrmVrf.DoesNotExist:
                diffsync.job.logger.warning(f"VRF {ids['vrf']} not found to associate prefix {ids['prefix']}")
                vrf = None
        else:
            vrf = None

        logger.info(msg=f"Processing Prefix {ids['prefix']} in Namespace: {attrs['namespace']}")
        _prefix, created = OrmPrefix.objects.get_or_create( #fixing adding error correction
            prefix=ids["prefix"],
            status=Status.objects.get(name=attrs["status"]),
            description=attrs["description"],
            namespace=Namespace.objects.get(name=attrs["namespace"]),
            tenant=OrmTenant.objects.get(name=attrs["vrf_tenant"]),
            location=Location.objects.get(name=ids["site"], location_type=LocationType.objects.get(name="Site")),
        )

        if not created:
            diffsync.job.logger.warning(f"Prefix: {_prefix.prefix} duplicate in Namespace: {_prefix.namespace.name}. Skipping ..")
            return
        if vrf:
            _prefix.vrfs.add(vrf)
        _prefix.tags.add(Tag.objects.get(name=PLUGIN_CFG.get("tag")))
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
            _prefix.tenant = OrmTenant.objects.get(name=self.tenant)
        if attrs.get("status"):
            _prefix.status = Status.objects.get(name=attrs["status"])
        if attrs.get("vrf") and attrs.get("vrf_tenant"):
            _prefix.vrf = OrmVrf.objects.get(name=attrs["vrf"], tenant=OrmTenant.objects.get(name=attrs["vrf_tenant"]))
        _prefix.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Prefix object in Nautobot."""
        self.diffsync.job.logger.warning(f"Prefix {self.prefix} will be deleted.")
        super().delete()

        try:
            tenant = OrmTenant.objects.get(name=self.tenant)
        except OrmTenant.DoesNotExist:
            tenant = None

        try:
            vrf_tenant = OrmTenant.objects.get(name=self.vrf_tenant)
        except OrmTenant.DoesNotExist:
            vrf_tenant = None

        _prefix = OrmPrefix.objects.get(
            prefix=self.prefix,
            tenant=tenant,
            vrf=OrmVrf.objects.get(name=self.vrf, tenant=vrf_tenant),
        )
        self.diffsync.objects_to_delete["prefix"].append(_prefix)  # pylint: disable=protected-access
        return self

class NautobotAppProfile(AppProfile):
    """Nautobot implementation of the AppProfile Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create AP object in Nautobot."""
        _tenant = OrmTenant.objects.get(name=ids["tenant"])
        _appprofile = OrmAppProfile(name=ids["name"], tenant=_tenant, description=attrs["description"])
        _appprofile.tags.add(Tag.objects.get(name=PLUGIN_CFG.get("tag")))
        _appprofile.tags.add(Tag.objects.get(name=attrs["site_tag"]))
        _appprofile.validated_save()
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update AP object in Nautobot."""
        _tenant = OrmTenant.objects.get(name=self.tenant)
        _appprofile = OrmAppProfile.objects.get(name=self.name, tenant=_tenant)
        if attrs.get("description"):
            _appprofile.description = attrs["description"]
            self.diffsync.job.logger.info(f"App Profile Update tenant: {_tenant} app profile: {_appprofile} desc: {_appprofile.description}")
        _appprofile.validated_save()
        self.diffsync.job.logger.info(f"App Profile updated for tenant: {_tenant}")
        return super().update(attrs)

    def delete(self):
        """Delete AP object in Nautobot."""
        self.diffsync.job.logger.warning(f"App Profile {self.name} will be deleted.")
        super().delete()
        _tenant = OrmTenant.objects.get(name=self.tenant)
        _appprofile = OrmAppProfile.objects.get(name=self.name, tenant=_tenant)
        self.diffsync.objects_to_delete["appprofile"].append(_appprofile)  # pylint: disable=protected-access
        return self

class NautobotBridgeDomain(BridgeDomain):
    """Nautobot implementation of the VRF Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create BD object in Nautobot."""
        try:
            _tenant = OrmTenant.objects.get(name=ids["tenant"])
            _namespace = Namespace.objects.get(name=ids["vrf"]["namespace"])
            if ids["tenant"] == ids["vrf"]["vrf_tenant"]: #most frequent case, saving one DB query
                _vrf_tenant = _tenant
            else:
                _vrf_tenant = OrmTenant.objects.get(name=ids["vrf"]["vrf_tenant"])
            _vrf = OrmVrf.objects.get(name=ids["vrf"]["name"], tenant=_vrf_tenant, namespace=_namespace)
        except OrmTenant.DoesNotExist:
            logger.warning(msg=f"Cannot create BD: {ids['name']} - Tenant: {ids['vrf']['tenant']} does not exist.")
            return
        except OrmVrf.DoesNotExist:
            logger.warning(msg=f"Cannot create BD: {ids['name']} - VRF: {ids['vrf']['name']} does not exist.")
            return
        except Namespace.DoesNotExist:
            logger.warning(msg=f"Cannot create BD: {ids['name']} - Namespace: {ids['vrf']['namespace']} does not exist.")
            return
        #ip_addresses = prefixes = []
        #for ip_address in attrs["ip_addresses"]:
        #    net_obj = ip_network(ip_address, strict=False) 
        #    ip_obj = ip_address.split('/')[0]
        #    try:
        #        _prefix = OrmPrefix.objects.get(network=str(net_obj.network_address), namespace=_namespace, tenant=_tenant)
        #        _ip_address = OrmIPAddress.objects.get(host=ip_obj, mask_length=net_obj.prefixlen, parent=_prefix)
        #    except OrmPrefix.DoesNotExist:
        #        logger.warning(msg=f"Cannot attach Gateway: {ip_address} - to BD: {ids['name']} Prefix does not exist.")
        #        continue
        #    except OrmIPAddress.DoesNotExist:
        #        logger.warning(msg=f"Cannot attach Gateway: {ip_address} - to BD: {ids['name']} IP Address does not exist.")
        #        continue
        #    prefixes.append(_prefix.id)
        #    ip_addresses.append(_ip_address.id)           
        # get subnets and ip addressess, pending
        logger.info(msg=f"Creating Bridge Domain: {ids['name']} in VRF: {ids['vrf']['name']}")
        _bd = OrmBridgeDomain(
            name=ids["name"],
            tenant=_tenant,
            vrf=_vrf,
            description=attrs["description"],
            )
        #if prefixes:
        #    _bd.prefixes.set(prefixes)
        #if ip_addresses:
        #    _bd.ip_addresses.set(ip_addresses)
        _bd.tags.add(Tag.objects.get(name=PLUGIN_CFG.get("tag")))
        _bd.tags.add(Tag.objects.get(name=attrs["site_tag"]))
        _bd.validated_save()
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update BD object in Nautobot."""
        try:
           _vrf = OrmVrf.objects.get(name=self.vrf["name"], tenant__name=self.vrf["vrf_tenant"], namespace__name=self.vrf["namespace"])
           _bd = OrmBridgeDomain.objects.get(name=self.name, vrf=_vrf, tenant__name=self.tenant)
        except OrmVrf.DoesNotExist:
            logger.warning(msg=f"Cannot update BD: {self.name} - VRF: {self.vrf['name']} does not exist.")
            return
        except OrmBridgeDomain.DoesNotExist:
            logger.warning(msg=f"Cannot update BD: {self.name} - BD does not exist.")
            return
        if attrs.get("description"):
            _bd.description = attrs["description"]
        if attrs.get("ip_addresses"):
            ip_addresses = prefixes = []
            for ip_address in attrs["ip_addresses"]:
                net_obj = ip_network(ip_address, strict=False) 
                ip_obj = ip_address.split('/')[0]
                try:
                    _ip_address = OrmIPAddress.objects.get(
                        host=ip_obj,
                        mask_length=net_obj.prefixlen,
                        tenant=_vrf.tenant,
                        )
                except OrmIPAddress.DoesNotExist:
                    logger.warning(msg=f"Cannot attach Gateway: {ip_address} - to BD: {self.name} IP Address does not exist.")
                    continue
                ip_addresses.append(_ip_address.id)
        if attrs.get("ip_addresses"):
            _bd.ip_addresses.set(ip_addresses)
        _bd.validated_save()
        self.diffsync.job.logger.info(f"BD {_bd.name} updated in VRF: {_vrf.name}")
        return super().update(attrs)

    def delete(self):
        """Delete BD object in Nautobot."""
        # TODO: write CRUD fx
        ...

class NautobotEPG(EPG):
    """Nautobot implementation of the EPG Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create BD object in Nautobot."""
        try:
           _tenant = OrmTenant.objects.get(name=ids["tenant"])
           _appprofile = OrmAppProfile.objects.get(name=ids["application"], tenant=_tenant)          
           _bd = OrmBridgeDomain.objects.get(name=attrs["bridge_domain"], tenant=_tenant)
        except OrmAppProfile.DoesNotExist:
            logger.warning(msg=f"Cannot create EPG: {ids['name']} - App Profile: {ids['application']} does not exist in Tenant {ids['tenant']}.")
            return
        except OrmBridgeDomain.DoesNotExist:
            logger.warning(msg=f"Cannot create EPG: {ids['name']} - BD: {attrs['bridge_domain']} does not exist in Tenant {ids['tenant']}.")
            return
        except OrmTenant.DoesNotExist:
            logger.warning(msg=f"Cannot create EPG: {ids['name']} - Tenant: {ids['tenant']} does not exist.")
            return

        logger.info(msg=f"Creating EPG: {ids['name']} in APP Profile: {ids['application']}")
        _epg = OrmEPG(
            name=ids["name"],
            tenant=_tenant,
            application=_appprofile,
            bridge_domain=_bd,
            description=attrs["description"],
            )
        _epg.tags.add(Tag.objects.get(name=PLUGIN_CFG.get("tag")))
        _epg.tags.add(Tag.objects.get(name=attrs["site_tag"]))
        _epg.validated_save()
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update BD object in Nautobot."""
        # TODO: write CRUD fx
        ...

    def delete(self):
        """Delete BD object in Nautobot."""
        # TODO: write CRUD fx
        ...

class NautobotEPGPath(EPGPath):
    """Nautobot implementation of the EPG Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create EPG Path object in Nautobot."""
        try:
            _epg = OrmEPG.objects.get(
                name=ids["epg"]["name"],
                application__name=ids["epg"]["application"],
                tenant__name=ids["epg"]["tenant"],
                )
            _interface = OrmInterface.objects.get(
                name=ids["interface"]["name"],
                device__name=ids["interface"]["device"],
                )
        except OrmEPG.DoesNotExist:
            logger.warning(msg=f"Cannot create Path: {_interface.device.name}:{_interface.name}:{ids['vlan']}. EPG {ids['epg']['name']} does not exist.")
            return
        except OrmInterface.DoesNotExist:
            logger.warning(msg=f"Cannot create Path: {_interface.device.name}:{_interface.name}:{ids['vlan']}. Interface does not exist.")
            return

        _vlan_id = ids["vlan"]
        _description = attrs["description"]
        _site_tag = attrs["site_tag"]
        _vlan_name = f"{_site_tag}_{_epg.application.name}_{_epg.name}_{_vlan_id}"
        _vlan, _created = VLAN.objects.get_or_create(
            vid=_vlan_id,
            location__name=_site_tag,
            name=_vlan_name,
            status=Status.objects.get(name="Active")
            )
        if _created:
            _vlan.tags.add(Tag.objects.get(name=PLUGIN_CFG.get("tag")))
            _vlan.tags.add(Tag.objects.get(name=_site_tag))
            _vlan.validated_save()
            logger.info(msg=f"Created VLAN: {_vlan_id} for EPG Path: {_interface.device.name}:{_interface.name}:{_vlan_id}")
        _path_name=f"{_interface.device.name}:{_interface.name}:{_vlan_id}"
        # Find exceptions here

        _epgpath = OrmEPGPath(
            name=_path_name,
            epg=_epg,
            interface=_interface,
            vlan=_vlan,
            description=_description,
            )
        _epgpath.tags.add(Tag.objects.get(name=PLUGIN_CFG.get("tag")))
        _epgpath.tags.add(Tag.objects.get(name=_site_tag))
        _epgpath.validated_save()
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update BD object in Nautobot."""
        # TODO: write CRUD fx
        ...

    def delete(self):
        """Delete BD object in Nautobot."""
        # TODO: write CRUD fx
        ...


NautobotDevice.update_forward_refs()
NautobotDeviceType.update_forward_refs()
NautobotBridgeDomain.update_forward_refs()
