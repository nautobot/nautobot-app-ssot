"""Nautobot DiffSync models for Meraki SSoT."""

from datetime import datetime

from nautobot.dcim.models import Device as NewDevice
from nautobot.dcim.models import DeviceType, Interface, Location, SoftwareVersion
from nautobot.extras.models import Note, Role
from nautobot.ipam.models import IPAddress as OrmIPAddress
from nautobot.ipam.models import IPAddressToInterface, PrefixLocationAssignment
from nautobot.ipam.models import Prefix as OrmPrefix

from nautobot_ssot.integrations.meraki.diffsync.models.base import (
    Device,
    Hardware,
    IPAddress,
    IPAssignment,
    Network,
    OSVersion,
    Port,
    Prefix,
    PrefixLocation,
)


class NautobotNetwork(Network):
    """Nautobot implementation of Network DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Site in Nautobot from NautobotNetwork object."""
        new_site = Location(
            name=ids["name"],
            location_type=adapter.job.network_loctype,
            parent_id=adapter.region_map[ids["parent"]] if ids.get("parent") else None,
            status_id=adapter.status_map["Active"],
            time_zone=attrs["timezone"],
        )
        if attrs.get("notes"):
            new_note = Note(
                note=attrs["notes"],
                user=adapter.job.user,
                assigned_object_type_id=adapter.contenttype_map["location"],
                assigned_object_id=new_site.id,
            )
            adapter.objects_to_create["notes"].append(new_note)
        if attrs.get("tags"):
            new_site.tags.set(attrs["tags"])
            for tag in new_site.tags.all():
                tag.content_types.add(adapter.contenttype_map["location"])
        if attrs.get("tenant"):
            new_site.tenant_id = adapter.tenant_map[attrs["tenant"]]
        new_site.validated_save()
        adapter.site_map[ids["name"]] = new_site
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Site in Nautobot from NautobotNetwork object."""
        site = Location.objects.get(id=self.uuid)
        if "timezone" in attrs:
            site.time_zone = attrs["timezone"]
        if attrs.get("notes"):
            new_note = Note(
                note=attrs["notes"],
                user=self.adapter.job.user,
                assigned_object_type_id=self.adapter.contenttype_map["location"],
                assigned_object_id=site.id,
            )
            new_note.validated_save()
        if "tags" in attrs:
            site.tags.set(attrs["tags"])
            for tag in site.tags.all():
                tag.content_types.add(self.adapter.contenttype_map["location"])
        if "tenant" in attrs:
            if attrs.get("tenant"):
                site.tenant_id = self.adapter.tenant_map[attrs["tenant"]]
            else:
                site.tenant = None
        site.validated_save()
        return super().update(attrs)


class NautobotHardware(Hardware):
    """Nautobot implementation of Hardware DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create DeviceType in Nautobot from NautobotHardware object."""
        new_dt = DeviceType(model=ids["model"], manufacturer_id=adapter.manufacturer_map["Cisco Meraki"])
        adapter.objects_to_create["devicetypes"].append(new_dt)
        adapter.devicetype_map[ids["model"]] = new_dt.id
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def delete(self):
        """Delete DeviceType in Nautobot from NautobotHardware object."""
        super().delete()
        devicetype = DeviceType.objects.get(id=self.uuid)
        self.adapter.objects_to_delete["devicetypes"].append(devicetype)
        return self


class NautobotOSVersion(OSVersion):
    """Nautobot implementation of Hardware DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create SoftwareVersion in Nautobot from NautobotOSVersion object."""
        new_ver = SoftwareVersion(
            version=ids["version"],
            status_id=adapter.status_map["Active"],
            platform_id=adapter.platform_map["Cisco Meraki"],
        )
        new_ver.validated_save()
        adapter.version_map[ids["version"]] = new_ver.id
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def delete(self):
        """Delete SoftwareVersion in Nautobot from NautobotOSVersion object."""
        osversion = SoftwareVersion.objects.get(id=self.uuid)
        if hasattr(osversion, "validatedsoftwarelcm_set"):
            if osversion.validatedsoftwarelcm_set.count() != 0:
                self.adapter.job.logger.warning(
                    f"SoftwareVersion {osversion.version} for {osversion.platform.name} is used with a ValidatedSoftware so won't be deleted."
                )
        else:
            super().delete()
            osversion.delete()
        return self


class NautobotDevice(Device):
    """Nautobot implementation of Meraki Device model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Device in Nautobot from NautobotDevice object."""
        dev_role, created = Role.objects.get_or_create(name=attrs["role"])
        if created:
            dev_role.content_types.add(adapter.contenttype_map["device"])
            adapter.devicerole_map[attrs["role"]] = dev_role.id
        new_device = NewDevice(
            name=ids["name"],
            platform_id=adapter.platform_map["Cisco Meraki"],
            serial=attrs["serial"],
            status_id=adapter.status_map[attrs["status"]],
            role_id=adapter.devicerole_map[attrs["role"]],
            device_type_id=adapter.devicetype_map[attrs["model"]],
            location=adapter.site_map[attrs["network"]],
            controller_managed_device_group=adapter.job.instance.controller_managed_device_groups.first(),
        )
        if attrs.get("notes"):
            new_note = Note(
                note=attrs["notes"],
                user=adapter.job.user,
                assigned_object_type_id=adapter.contenttype_map["device"],
                assigned_object_id=new_device.id,
            )
            adapter.objects_to_create["notes"].append(new_note)
        if attrs.get("tags"):
            new_device.tags.set(attrs["tags"])
            for tag in new_device.tags.all():
                tag.content_types.add(adapter.contenttype_map["device"])
        if "tenant" in attrs:
            if attrs.get("tenant"):
                new_device.tenant_id = adapter.tenant_map[attrs["tenant"]]
            else:
                new_device.tenant = None
        if attrs.get("version"):
            new_device.software_version_id = adapter.version_map[attrs["version"]]
        new_device.custom_field_data["system_of_record"] = "Meraki SSoT"
        new_device.custom_field_data["last_synced_from_sor"] = datetime.today().date().isoformat()
        adapter.objects_to_create["devices"].append(new_device)
        adapter.device_map[new_device.name] = new_device.id
        adapter.port_map[new_device.name] = {}
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):  # pylint: disable=too-many-branches
        """Update Device in Nautobot from NautobotDevice object."""
        device = NewDevice.objects.get(id=self.uuid)
        if "controller_group" in attrs:
            device.controller_managed_device_group = self.adapter.job.instance.controller_managed_device_groups.first()
        if "serial" in attrs:
            device.serial = attrs["serial"]
        if "status" in attrs:
            device.status_id = self.adapter.status_map[attrs["status"]]
        if "role" in attrs:
            device.role_id = self.adapter.devicerole_map[attrs["role"]]
        if "model" in attrs:
            device.device_type_id = self.adapter.devicetype_map[attrs["model"]]
        if "network" in attrs:
            device.location = self.adapter.site_map[attrs["network"]]
        if attrs.get("notes"):
            new_note = Note(
                note=attrs["notes"],
                user=self.adapter.job.user,
                assigned_object_type_id=self.adapter.contenttype_map["device"],
                assigned_object_id=device.id,
            )
            new_note.validated_save()
        if "tags" in attrs:
            device.tags.set(attrs["tags"])
            for tag in device.tags.all():
                tag.content_types.add(self.adapter.contenttype_map["device"])
        if "tenant" in attrs:
            if attrs.get("tenant"):
                device.tenant_id = self.adapter.tenant_map[attrs["tenant"]]
            else:
                device.tenant = None
        if "version" in attrs:
            device.software_version_id = self.adapter.version_map[attrs["version"]]
        device.custom_field_data["system_of_record"] = "Meraki SSoT"
        device.custom_field_data["last_synced_from_sor"] = datetime.today().date().isoformat()
        device.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Device in Nautobot from NautobotDevice object."""
        dev = NewDevice.objects.get(id=self.uuid)
        super().delete()
        self.adapter.objects_to_delete["devices"].append(dev)
        return self


class NautobotPort(Port):
    """Nautobot implementation of Meraki Port model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Interface in Nautobot from NautobotDevice object."""
        new_port = Interface(
            name=ids["name"],
            device_id=adapter.device_map[ids["device"]],
            enabled=attrs["enabled"],
            mode="access" if not attrs["tagging"] else "tagged",
            mgmt_only=attrs["management"],
            type=attrs["port_type"],
            status_id=adapter.status_map[attrs["port_status"]],
        )
        new_port.custom_field_data["system_of_record"] = "Meraki SSoT"
        new_port.custom_field_data["last_synced_from_sor"] = datetime.today().date().isoformat()
        adapter.objects_to_create["ports"].append(new_port)
        adapter.port_map[ids["device"]][ids["name"]] = new_port.id
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Interface in Nautobot from NautobotDevice object."""
        port = Interface.objects.get(id=self.uuid)
        if "enabled" in attrs:
            port.enabled = attrs["enabled"]
        if "tagging" in attrs:
            port.mode = "access" if not attrs["tagging"] else "tagged"
        if "management" in attrs:
            port.mgmt_only = attrs["management"]
        if "port_type" in attrs:
            port.type = attrs["port_type"]
        if "port_status" in attrs:
            port.status_id = self.adapter.status_map[attrs["port_status"]]
        port.custom_field_data["system_of_record"] = "Meraki SSoT"
        port.custom_field_data["last_synced_from_sor"] = datetime.today().date().isoformat()
        port.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Interface in Nautobot from NautobotDevice object."""
        port = Interface.objects.get(id=self.uuid)
        super().delete()
        self.adapter.objects_to_delete["ports"].append(port)
        return self


class NautobotPrefix(Prefix):
    """Nautobot implementation of Meraki Prefix model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Prefix in Nautobot from NautobotPrefix object."""
        new_pf = OrmPrefix(
            prefix=ids["prefix"],
            namespace_id=adapter.namespace_map[ids["namespace"]],
            status_id=adapter.status_map["Active"],
            tenant_id=adapter.tenant_map[attrs["tenant"]] if attrs.get("tenant") else None,
        )
        new_pf.custom_field_data["system_of_record"] = "Meraki SSoT"
        new_pf.custom_field_data["last_synced_from_sor"] = datetime.today().date().isoformat()
        adapter.objects_to_create["prefixes"].append(new_pf)
        adapter.prefix_map[ids["prefix"]] = new_pf.id
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Prefix in Nautobot from NautobotPrefix object."""
        prefix = OrmPrefix.objects.get(id=self.uuid)
        if "tenant" in attrs:
            if attrs.get("tenant"):
                prefix.tenant_id = self.adapter.tenant_map[attrs["tenant"]]
            else:
                prefix.tenant = None
        prefix.custom_field_data["system_of_record"] = "Meraki SSoT"
        prefix.custom_field_data["last_synced_from_sor"] = datetime.today().date().isoformat()
        prefix.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Prefix in Nautobot from NautobotPrefix object."""
        del_pf = OrmPrefix.objects.get(id=self.uuid)
        super().delete()
        self.adapter.objects_to_delete["prefixes"].append(del_pf)
        return self


class NautobotPrefixLocation(PrefixLocation):
    """Nautobot implementation of Meraki PrefixLocation model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create PrefixLocationAssignment in Nautobot from NautobotPrefixLocation object."""
        new_assignment = PrefixLocationAssignment(
            prefix_id=adapter.prefix_map[ids["prefix"]], location=adapter.site_map[ids["location"]]
        )
        adapter.objects_to_create["prefix_locs"].append(new_assignment)
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def delete(self):
        """Delete Prefix in Nautobot from NautobotPrefix object."""
        del_pf = PrefixLocationAssignment.objects.get(id=self.uuid)
        super().delete()
        del_pf.delete()
        return self


class NautobotIPAddress(IPAddress):
    """Nautobot implementation of Meraki Port model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddress in Nautobot from NautobotIPAddress object."""
        namespace = ids["tenant"] if ids.get("tenant") else "Global"
        new_ip = OrmIPAddress(
            address=f"{ids['host']}/{attrs['mask_length']}",
            namespace=adapter.namespace_map[namespace],
            status_id=adapter.status_map["Active"],
            tenant_id=adapter.tenant_map[ids["tenant"]] if ids.get("tenant") else None,
        )
        adapter.objects_to_create["ipaddrs-to-prefixes"].append((new_ip, adapter.prefix_map[attrs["prefix"]]))
        new_ip.custom_field_data["system_of_record"] = "Meraki SSoT"
        new_ip.custom_field_data["last_synced_from_sor"] = datetime.today().date().isoformat()
        adapter.objects_to_create["ipaddrs"].append(new_ip)
        if namespace not in adapter.ipaddr_map:
            adapter.ipaddr_map[namespace] = {}
        adapter.ipaddr_map[namespace][ids["host"]] = new_ip.id
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update IPAddress in Nautobot from NautobotIPAddress object."""
        ipaddr = OrmIPAddress.objects.get(id=self.uuid)
        if self.adapter.job.debug:
            self.adapter.job.logger.debug(f"Updating IPAddress {ipaddr.address} in Nautobot with {attrs}.")
        if attrs.get("mask_length"):
            ipaddr.mask_length = attrs["mask_length"]
        if attrs.get("prefix"):
            old_pf = None
            if attrs["prefix"] not in self.adapter.prefix_map:
                self.adapter.job.logger.error(f"Prefix {attrs['prefix']} not found in Nautobot.")
                return None
            if ipaddr.parent.prefix_length == 32 and ipaddr.ip_version == 4:
                old_pf = ipaddr.parent
            try:
                new_parent = OrmPrefix.objects.get(id=self.adapter.prefix_map[attrs["prefix"]])
            except OrmPrefix.DoesNotExist:
                for pfx in self.adapter.objects_to_create["prefixes"]:
                    if str(pfx.prefix) == attrs["prefix"]:
                        new_parent = pfx
                        self.adapter.objects_to_create["prefixes"].remove(pfx)
                        break
                else:
                    self.adapter.job.logger.error(f"New parent Prefix {attrs['prefix']} not found.")
                    return None
            if new_parent.type != "pool":
                new_parent.type = "pool"
                new_parent.validated_save()
            ipaddr.parent = new_parent
            if old_pf:
                old_pf.delete()
        ipaddr.custom_field_data["system_of_record"] = "Meraki SSoT"
        ipaddr.custom_field_data["last_synced_from_sor"] = datetime.today().date().isoformat()
        ipaddr.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete IPAddress in Nautobot from NautobotIPAddress object."""
        ipaddr = OrmIPAddress.objects.get(id=self.uuid)
        super().delete()
        self.adapter.objects_to_delete["ipaddrs"].append(ipaddr)
        return self


class NautobotIPAssignment(IPAssignment):
    """Nautobot implementation of Citrix ADM IPAddressOnInterface model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddressToInterface in Nautobot from IPAddressOnInterface object."""
        new_map = IPAddressToInterface(
            ip_address_id=adapter.ipaddr_map[ids["namespace"]][ids["address"]],
            interface_id=adapter.port_map[ids["device"]][ids["port"]],
        )
        adapter.objects_to_create["ipaddrs-to-intfs"].append(new_map)
        if attrs.get("primary"):
            if ":" in ids["address"]:
                adapter.objects_to_create["device_primary_ip6"].append(
                    (adapter.device_map[ids["device"]], adapter.ipaddr_map[ids["namespace"]][ids["address"]])
                )
            else:
                adapter.objects_to_create["device_primary_ip4"].append(
                    (adapter.device_map[ids["device"]], adapter.ipaddr_map[ids["namespace"]][ids["address"]])
                )
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update IP Address in Nautobot from IPAddressOnInterface object."""
        mapping = IPAddressToInterface.objects.get(id=self.uuid)
        if attrs.get("primary"):
            if mapping.ip_address.ip_version == 4:
                self.adapter.objects_to_create["device_primary_ip4"].append(
                    (mapping.interface.device.id, mapping.ip_address.id)
                )
            else:
                self.adapter.objects_to_create["device_primary_ip6"].append(
                    (mapping.interface.device.id, mapping.ip_address.id)
                )
            mapping.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete IPAddressToInterface in Nautobot from NautobotIPAddressOnInterface object."""
        mapping = IPAddressToInterface.objects.get(id=self.uuid)
        super().delete()
        self.adapter.job.logger.info(
            f"Deleting IPAddress to Interface mapping between {self.address} and {self.device}'s {self.port} port."
        )
        mapping.delete()
        return self
