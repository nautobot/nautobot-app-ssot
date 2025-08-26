# pylint: disable=duplicate-code
"""Nautobot DiffSync models for Citrix ADM SSoT."""

from datetime import datetime

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import Device as NewDevice
from nautobot.dcim.models import DeviceType, Interface, Location, Manufacturer, Platform, SoftwareVersion
from nautobot.extras.models import Role, Status, Tag
from nautobot.ipam.models import IPAddress, IPAddressToInterface, Namespace, Prefix
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.citrix_adm.diffsync.models.base import (
    Address,
    Datacenter,
    Device,
    IPAddressOnInterface,
    OSVersion,
    Port,
    Subnet,
)


class NautobotDatacenter(Datacenter):
    """Nautobot implementation of Citrix ADM Datacenter model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Site in Nautobot from NautobotDatacenter object."""
        status_active = Status.objects.get(name="Active")
        parent_loc = None
        if adapter.job.dc_loctype.parent and ids.get("region"):
            parent_loc = Location.objects.get_or_create(
                name=ids["region"], location_type=adapter.job.dc_loctype.parent, status=status_active
            )[0]
        if Location.objects.filter(name=ids["name"]).exists():
            adapter.job.logger.warning(f"Site {ids['name']} already exists so skipping creation.")
            return None
        new_site = Location(
            name=ids["name"],
            parent=parent_loc,
            status=status_active,
            latitude=attrs["latitude"],
            longitude=attrs["longitude"],
            location_type=adapter.job.dc_loctype,
        )
        new_site.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Site in Nautobot from NautobotDatacenter object."""
        if not settings.PLUGINS_CONFIG.get("nautobot_ssot").get("citrix_adm_update_sites"):
            self.adapter.job.logger.warning(f"Update sites setting is disabled so skipping updating {self.name}.")
            return None
        site = Location.objects.get(id=self.uuid)
        if "latitude" in attrs:
            site.latitude = attrs["latitude"]
        if "longitude" in attrs:
            site.longitude = attrs["longitude"]
        site.validated_save()
        return super().update(attrs)


class NautobotOSVersion(OSVersion):
    """Nautobot implementation of Citrix ADM Device model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create SoftwareVersion in Nautobot from NautobotOSVersion object."""
        new_ver = SoftwareVersion(
            version=ids["version"],
            platform=Platform.objects.get(name="citrix.adc"),
            status=Status.objects.get(name="Active"),
        )
        new_ver.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def delete(self):
        """Delete SoftwareVersion in Nautobot from NautobotOSVersion object."""
        ver = SoftwareVersion.objects.get(id=self.uuid)
        if hasattr(ver, "validatedsoftwarelcm_set"):
            if ver.validatedsoftwarelcm_set.count() != 0:
                self.adapter.job.logger.warning(
                    f"SoftwareVersion {ver.version} for {ver.platform.name} is used with a ValidatedSoftware so won't be deleted."
                )
        else:
            super().delete()
            ver.delete()
        return self


class NautobotDevice(Device):
    """Nautobot implementation of Citrix ADM Device model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Device in Nautobot from NautobotDevice object."""
        lb_role, created = Role.objects.get_or_create(name=attrs["role"])
        if created:
            lb_role.content_types.add(ContentType.objects.get_for_model(NewDevice))
        lb_dt, _ = DeviceType.objects.get_or_create(
            model=attrs["model"], manufacturer=Manufacturer.objects.get(name="Citrix")
        )
        citrix_platform = Platform.objects.get(name="citrix.adc")
        new_device = NewDevice(
            name=ids["name"],
            status=Status.objects.get(name=attrs["status"]),
            role=lb_role,
            location=Location.objects.get(name=attrs["site"], location_type=adapter.job.dc_loctype),
            device_type=lb_dt,
            serial=attrs["serial"],
            platform=citrix_platform,
        )
        if attrs.get("tenant"):
            new_device.tenant = Tenant.objects.update_or_create(name=attrs["tenant"])[0]
        if attrs.get("version"):
            new_device.software_version = SoftwareVersion.objects.get_or_create(
                version=attrs["version"], platform=citrix_platform
            )[0]
        if attrs.get("hanode"):
            new_device.custom_field_data["ha_node"] = attrs["hanode"]
        new_device.custom_field_data["system_of_record"] = "Citrix ADM"
        new_device.custom_field_data["last_synced_from_sor"] = datetime.today().date().isoformat()
        new_device.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Device in Nautobot from NautobotDevice object."""
        device = NewDevice.objects.get(id=self.uuid)
        if "model" in attrs:
            device.device_type, _ = DeviceType.objects.get_or_create(
                model=attrs["model"], manufacturer=Manufacturer.objects.get(name="Citrix")
            )
        if "status" in attrs:
            device.status = Status.objects.get(name=attrs["status"])
        if "role" in attrs:
            device.role = Role.objects.get_or_create(name=attrs["role"])[0]
        if "serial" in attrs:
            device.serial = attrs["serial"]
        if "site" in attrs:
            device.location = Location.objects.get(name=attrs["site"])
        if "tenant" in attrs:
            if attrs.get("tenant"):
                device.tenant = Tenant.objects.update_or_create(name=attrs["tenant"])[0]
            else:
                device.tenant = None
        if "version" in attrs:
            if attrs.get("version"):
                device.software_version = SoftwareVersion.objects.get_or_create(
                    version=attrs["version"], platform=Platform.objects.get(name="citrix.adc")
                )[0]
            else:
                device.software_version = None
        if "hanode" in attrs:
            device.custom_field_data["ha_node"] = attrs["hanode"]
        device.custom_field_data["system_of_record"] = "Citrix ADM"
        device.custom_field_data["last_synced_from_sor"] = datetime.today().date().isoformat()
        device.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Device in Nautobot from NautobotDevice object."""
        dev = NewDevice.objects.get(id=self.uuid)
        super().delete()
        self.adapter.job.logger.info(f"Deleting Device {dev.name}.")
        self.adapter.objects_to_delete["devices"].append(dev)
        return self


class NautobotPort(Port):
    """Nautobot implementation of Citrix ADM Port model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Interface in Nautobot from NautobotPort object."""
        new_port = Interface(
            name=ids["name"],
            device=NewDevice.objects.get(name=ids["device"]),
            status=Status.objects.get(name=attrs["status"]),
            description=attrs["description"],
            type="virtual",
            mgmt_only=bool(ids["name"] == "Management"),
        )
        new_port.custom_field_data["system_of_record"] = "Citrix ADM"
        new_port.custom_field_data["last_synced_from_sor"] = datetime.today().date().isoformat()
        new_port.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Interface in Nautobot from NautobotPort object."""
        port = Interface.objects.get(self.uuid)
        if "status" in attrs:
            port.status = Status.objects.get(name=attrs["status"])
        if "description" in attrs:
            port.description = attrs["description"]
        port.custom_field_data["system_of_record"] = "Citrix ADM"
        port.custom_field_data["last_synced_from_sor"] = datetime.today().date().isoformat()
        port.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Interface in Nautobot from NautobotPort object."""
        port = Interface.objects.get(id=self.uuid)
        super().delete()
        self.adapter.job.logger.info(f"Deleting Port {port.name} for {port.device.name}.")
        self.adapter.objects_to_delete["ports"].append(port)
        return self


class NautobotSubnet(Subnet):
    """Nautobot implementation of Citrix ADM Subnet model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Prefix in Nautobot from NautobotSubnet object."""
        namespace = Namespace.objects.get_or_create(name=ids["namespace"])[0]
        if adapter.job.debug:
            adapter.job.logger.info(f"Creating Prefix {ids['prefix']}.")
        _pf = Prefix(
            prefix=ids["prefix"],
            namespace=namespace,
            status=Status.objects.get(name="Active"),
            tenant=Tenant.objects.get(name=attrs["tenant"]) if attrs.get("tenant") else None,
        )
        _pf.custom_field_data.update({"system_of_record": "Citrix ADM"})
        _pf.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _pf.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update IP Address in Nautobot from NautobotAddress object."""
        _pf = Prefix.objects.get(id=self.uuid)
        if "tenant" in attrs:
            if attrs.get("tenant"):
                _pf.tenant = Tenant.objects.get(name=attrs["tenant"])
            else:
                _pf.tenant = None
        _pf.custom_field_data.update({"system_of_record": "Citrix ADM"})
        _pf.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        _pf.validated_save()
        return super().update(attrs)

    def delete(self):  # pylint: disable=inconsistent-return-statements
        """Delete Prefix in Nautobot."""
        try:
            _pf = Prefix.objects.get(id=self.uuid)
            self.adapter.objects_to_delete["prefixes"].append(_pf)
            super().delete()
            return self
        except Prefix.DoesNotExist as err:
            if self.adapter.job.debug:
                self.adapter.job.logger.warning(f"Unable to find Prefix {self.prefix} {self.uuid} for deletion. {err}")


class NautobotAddress(Address):
    """Nautobot implementation of Citrix ADM Address model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IP Address in Nautobot from NautobotAddress object."""
        if ids.get("tenant"):
            pf_namespace = Namespace.objects.get_or_create(name=ids["tenant"])[0]
        else:
            pf_namespace = Namespace.objects.get(name="Global")
        print(f"Using namespace {pf_namespace} for {ids['host_address']}")
        new_ip = IPAddress(
            host=ids["host_address"],
            mask_length=attrs["mask_length"],
            parent=Prefix.objects.get(prefix=attrs["prefix"], namespace=pf_namespace),
            status=Status.objects.get(name="Active"),
            namespace=pf_namespace,
        )
        if ids.get("tenant"):
            new_ip.tenant = adapter.job.tenant
        if attrs.get("tags"):
            new_ip.tags.set(attrs["tags"])
            for tag in attrs["tags"]:
                new_tag = Tag.objects.get_or_create(name=tag)[0]
                new_tag.content_types.add(ContentType.objects.get_for_model(IPAddress))
        new_ip.custom_field_data["system_of_record"] = "Citrix ADM"
        new_ip.custom_field_data["last_synced_from_sor"] = datetime.today().date().isoformat()
        new_ip.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update IP Address in Nautobot from NautobotAddress object."""
        addr = IPAddress.objects.get(id=self.uuid)
        if attrs.get("mask_length"):
            addr.mask_length = attrs["mask_length"]
        if attrs.get("prefix"):
            addr.parent = Prefix.objects.get(prefix=attrs["prefix"], namespace=addr.parent.namespace)
        if "tags" in attrs:
            addr.tags.set(attrs["tags"])
            for tag in attrs["tags"]:
                new_tag = Tag.objects.get_or_create(name=tag)[0]
                new_tag.content_types.add(ContentType.objects.get_for_model(IPAddress))
        else:
            addr.tags.clear()
        addr.custom_field_data["system_of_record"] = "Citrix ADM"
        addr.custom_field_data["last_synced_from_sor"] = datetime.today().date().isoformat()
        addr.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete IP Address in Nautobot from NautobotAddress object."""
        addr = IPAddress.objects.get(id=self.uuid)
        super().delete()
        self.adapter.job.logger.info(f"Deleting IP Address {self}.")
        self.adapter.objects_to_delete["addresses"].append(addr)
        return self


class NautobotIPAddressOnInterface(IPAddressOnInterface):
    """Nautobot implementation of Citrix ADM IPAddressOnInterface model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddressToInterface in Nautobot from IPAddressOnInterface object."""
        tenant_name = adapter.job.tenant.name if adapter.job.tenant else "Global"
        new_map = IPAddressToInterface(
            ip_address=IPAddress.objects.get(host=ids["host_address"], parent__namespace__name=tenant_name),
            interface=Interface.objects.get(name=ids["port"], device__name=ids["device"]),
        )
        new_map.validated_save()
        if attrs.get("primary"):
            if new_map.ip_address.ip_version == 4:
                new_map.interface.device.primary_ip4 = new_map.ip_address
            else:
                new_map.interface.device.primary_ip6 = new_map.ip_address
            new_map.interface.device.validated_save()
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update IP Address in Nautobot from IPAddressOnInterface object."""
        ip_to_intf = IPAddressToInterface.objects.get(id=self.uuid)
        if attrs.get("primary"):
            if ip_to_intf.ip_address.ip_version == 4:
                ip_to_intf.interface.device.primary_ip4 = ip_to_intf.ip_address
            else:
                ip_to_intf.interface.device.primary_ip6 = ip_to_intf.ip_address
            ip_to_intf.interface.device.validated_save()
        ip_to_intf.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete IPAddressToInterface in Nautobot from NautobotIPAddressOnInterface object."""
        ip_to_intf = IPAddressToInterface.objects.get(id=self.uuid)
        super().delete()
        self.adapter.job.logger.info(
            f"Deleting IPAddress to Interface mapping between {self.address} and {self.device}'s {self.port} port."
        )
        ip_to_intf.delete()
        return self
