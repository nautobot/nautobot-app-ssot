"""Nautobot DiffSync models for DNA Center SSoT."""

from datetime import datetime
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from nautobot.dcim.models import (
    Device,
    DeviceType,
    Interface,
    Manufacturer,
    Location,
    LocationType,
)
from nautobot.extras.models import Role
from nautobot.ipam.models import IPAddress, IPAddressToInterface, Prefix, Namespace
from nautobot_ssot_dna_center.diffsync.models import base
from nautobot_ssot_dna_center.utils.nautobot import add_software_lcm, assign_version_to_device, verify_platform

try:
    import nautobot_device_lifecycle_mgmt  # noqa: F401

    LIFECYCLE_MGMT = True
except ImportError:
    LIFECYCLE_MGMT = False


class NautobotArea(base.Area):
    """Nautobot implementation of Area DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Region in Nautobot from Area object."""
        try:
            diffsync.region_map[ids["name"]]
            diffsync.job.logger.warning(f"Region {ids['name']} already exists so won't be created.")
        except KeyError:
            if diffsync.job.debug:
                diffsync.job.logger.info(f"Creating Region {ids['name']}.")
            new_region = Location(
                name=ids["name"],
                location_type_id=diffsync.locationtype_map["Region"],
                status_id=diffsync.status_map["Active"],
            )
            if ids.get("parent"):
                try:
                    new_region.parent_id = diffsync.region_map[ids["parent"]]
                except KeyError:
                    diffsync.job.logger.warning(f"Unable to find Region {ids['parent']} for {ids['name']}.")
            new_region.validated_save()
            diffsync.region_map[ids["name"]] = new_region.id
            return super().create(diffsync=diffsync, ids=ids, attrs=attrs)


class NautobotBuilding(base.Building):
    """Nautobot implementation of Building DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Site in Nautobot from Building object."""
        if diffsync.job.debug:
            diffsync.job.logger.info(f"Creating Site {ids['name']}.")
        new_site = Location(
            name=ids["name"],
            location_type_id=diffsync.locationtype_map["Site"],
            parent_id=diffsync.region_map[attrs["area"]],
            physical_address=attrs["address"] if attrs.get("address") else "",
            status_id=diffsync.status_map["Active"],
            latitude=attrs["latitude"],
            longitude=attrs["longitude"],
        )
        if attrs.get("tenant"):
            new_site.tenant_id = diffsync.tenant_map[attrs["tenant"]]
        new_site.validated_save()
        diffsync.site_map[ids["name"]] = new_site.id
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Site in Nautobot from Building object."""
        if not settings.PLUGINS_CONFIG["nautobot_ssot_dna_center"].get("update_locations"):
            self.diffsync.job.logger.warning(
                f"`update_locations` setting is disabled so will skip updating {self.name}."
            )
            return super().update(attrs)
        site = Location.objects.get(id=self.uuid)
        if self.diffsync.job.debug:
            self.diffsync.job.logger.info(f"Updating Site {site.name}.")
        if "address" in attrs:
            site.physical_address = attrs["address"]
        if "area" in attrs:
            site.parent_id = self.diffsync.region_map[attrs["area"]]
        if "latitude" in attrs:
            site.latitude = attrs["latitude"]
        if "longitude" in attrs:
            site.longitude = attrs["longitude"]
        if "tenant" in attrs:
            if attrs.get("tenant"):
                site.tenant_id = self.diffsync.tenant_map[attrs["tenant"]]
            else:
                site.tenant = None
        site.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Site in Nautobot from Building object."""
        if not settings.PLUGINS_CONFIG["nautobot_ssot_dna_center"].get("update_locations"):
            self.diffsync.job.logger.warning(
                f"`update_locations` setting is disabled so will skip deleting {self.name}."
            )
            return None
        site = Location.objects.get(id=self.uuid)
        if self.diffsync.job.debug:
            self.diffsync.job.logger.info(f"Deleting Site {site.name}.")
        self.diffsync.objects_to_delete["sites"].append(site)
        return self


class NautobotFloor(base.Floor):
    """Nautobot implementation of Floor DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create LocationType: Floor in Nautobot from Floor object."""
        if diffsync.job.debug:
            diffsync.job.logger.info(f"Creating Floor {ids['name']}.")
        new_floor = Location(
            name=ids["name"],
            status_id=diffsync.status_map["Active"],
            parent_id=diffsync.site_map[ids["building"]],
            location_type_id=diffsync.locationtype_map["Floor"],
        )
        if attrs.get("tenant"):
            new_floor.tenant_id = diffsync.tenant_map[attrs["tenant"]]
        new_floor.validated_save()
        diffsync.floor_map[ids["name"]] = new_floor.id
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update LocationType: Floor in Nautobot from Floor object."""
        floor = Location.objects.get(name=self.name, location_type=LocationType.objects.get(name="Floor"))
        if self.diffsync.job.debug:
            self.diffsync.job.logger.info(f"Updating Floor {floor.name} with {attrs}")
        if "tenant" in attrs:
            if attrs.get("tenant"):
                floor.tenant_id = self.diffsync.tenant_map[attrs["tenant"]]
            else:
                floor.tenant = None
        floor.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete LocationType: Floor in Nautobot from Floor object."""
        floor = Location.objects.get(id=self.uuid)
        if self.diffsync.job.debug:
            self.diffsync.job.logger.info(f"Deleting Floor {floor.name} in {floor.parent.name}.")
        self.diffsync.objects_to_delete["floors"].append(floor)
        return self


class NautobotDevice(base.Device):
    """Nautobot implementation of DNA Center Device model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Device in Nautobot from NautobotDevice object."""
        if diffsync.job.debug:
            diffsync.job.logger.info(f"Creating Device {ids['name']}.")
        manufacturer, _ = Manufacturer.objects.get_or_create(name=attrs["vendor"])
        device_role, created = Role.objects.get_or_create(name=attrs["role"])
        if created:
            device_role.content_types.add(ContentType.objects.get_for_model(Device))
            device_role.validated_save()
        device_type, _ = DeviceType.objects.get_or_create(model=attrs["model"], manufacturer=manufacturer)
        platform = verify_platform(platform_name=attrs["platform"], manu=manufacturer.id)
        new_device = Device(
            name=ids["name"],
            status_id=diffsync.status_map[attrs["status"]],
            role=device_role,
            location_id=diffsync.site_map[attrs["site"]],
            device_type=device_type,
            serial=attrs["serial"],
            platform_id=platform.id,
        )
        if attrs.get("floor"):
            new_device.location_id = diffsync.floor_map[attrs["floor"]]
        if attrs.get("tenant"):
            new_device.tenant_id = diffsync.tenant_map[attrs["tenant"]]
        if attrs.get("version"):
            new_device.custom_field_data.update({"os_version": attrs["version"]})
            if LIFECYCLE_MGMT:
                lcm_obj = add_software_lcm(
                    diffsync=diffsync, platform=platform.network_driver, version=attrs["version"]
                )
                assign_version_to_device(diffsync=diffsync, device=new_device, software_lcm=lcm_obj)
        new_device.custom_field_data.update({"system_of_record": "DNA Center"})
        new_device.custom_field_data.update({"ssot_last_synchronized": datetime.today().date().isoformat()})
        diffsync.objects_to_create["devices"].append(new_device)
        diffsync.device_map[ids["name"]] = new_device.id
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Device in Nautobot from NautobotDevice object."""
        device = Device.objects.get(id=self.uuid)
        if self.diffsync.job.debug:
            self.diffsync.job.logger.info(f"Updating Device {device.name} with {attrs}")
        if "status" in attrs:
            device.status_id = self.diffsync.status_map[attrs["status"]]
        if "role" in attrs:
            dev_role, created = Role.objects.get_or_create(name=attrs["role"])
            device.role = dev_role
            if created:
                dev_role.content_types.add(ContentType.objects.get_for_model(Device))
        if attrs.get("site"):
            device.location_id = self.diffsync.site_map[attrs["site"]]
        if attrs.get("floor"):
            device.location_id = self.diffsync.floor_map[attrs["floor"]]
        if "model" in attrs:
            if attrs.get("vendor"):
                vendor = Manufacturer.objects.get_or_create(name=attrs["vendor"])[0]
            else:
                vendor = Manufacturer.objects.get_or_create(name=self.vendor)[0]
            device.device_type = DeviceType.objects.get_or_create(model=attrs["model"], manufacturer=vendor)[0]
        if "serial" in attrs:
            device.serial = attrs["serial"]
        if "platform" in attrs:
            vendor = attrs["vendor"] if attrs.get("vendor") else self.vendor
            manufacturer = Manufacturer.objects.get(name=vendor)
            device.platform = verify_platform(platform_name=attrs["platform"], manu=manufacturer.id)
        if "tenant" in attrs:
            if attrs.get("tenant"):
                device.tenant_id = self.diffsync.tenant_map[attrs["tenant"]]
            else:
                device.tenant = None
        if "version" in attrs:
            device.custom_field_data.update({"os_version": attrs["version"]})
            if LIFECYCLE_MGMT:
                platform_network_driver = attrs["platform"] if attrs.get("platform") else self.platform
                lcm_obj = add_software_lcm(
                    diffsync=self.diffsync, platform=platform_network_driver, version=attrs["version"]
                )
                assign_version_to_device(diffsync=self.diffsync, device=device, software_lcm=lcm_obj)
        device.custom_field_data.update({"system_of_record": "DNA Center"})
        device.custom_field_data.update({"ssot_last_synchronized": datetime.today().date().isoformat()})
        device.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Device in Nautobot from NautobotDevice object."""
        dev = Device.objects.get(id=self.uuid)
        if self.diffsync.job.debug:
            self.diffsync.job.logger.info(f"Deleting Device: {dev.name}.")
        super().delete()
        self.diffsync.objects_to_delete["devices"].append(dev)
        return self


class NautobotPort(base.Port):
    """Nautobot implementation of Port DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Interface in Nautobot from Port object."""
        if diffsync.job.debug:
            diffsync.job.logger.info(f"Creating Port {ids['name']} for Device {ids['device']}.")
        new_port = Interface(
            name=ids["name"],
            device_id=diffsync.device_map[ids["device"]],
            description=attrs["description"],
            enabled=attrs["enabled"],
            type=attrs["port_type"],
            mode=attrs["port_mode"],
            mac_address=attrs["mac_addr"],
            mtu=attrs["mtu"],
            status_id=diffsync.status_map[attrs["status"]],
            mgmt_only=True if "Management" in ids["name"] else False,
        )
        new_port.custom_field_data.update({"system_of_record": "DNA Center"})
        new_port.custom_field_data.update({"ssot_last_synchronized": datetime.today().date().isoformat()})
        diffsync.objects_to_create["interfaces"].append(new_port)
        if ids["device"] not in diffsync.port_map:
            diffsync.port_map[ids["device"]] = {}
        diffsync.port_map[ids["device"]][ids["name"]] = new_port.id
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Interface in Nautobot from Port object."""
        port = Interface.objects.get(id=self.uuid)
        if self.diffsync.job.debug:
            self.diffsync.job.logger.info(f"Updating Port {port.name} for Device {port.device.name}.")
        if "description" in attrs:
            port.description = attrs["description"]
        if "mac_addr" in attrs:
            port.mac_address = attrs["mac_addr"]
        if "port_type" in attrs:
            port.type = attrs["port_type"]
        if "port_mode" in attrs:
            port.mode = attrs["port_mode"]
        if "mtu" in attrs:
            port.mtu = attrs["mtu"]
        if "status" in attrs:
            port.status_id = self.diffsync.status_map[attrs["status"]]
        if "enabled" in attrs:
            port.enabled = attrs["enabled"]
        port.custom_field_data.update({"system_of_record": "DNA Center"})
        port.custom_field_data.update({"ssot_last_synchronized": datetime.today().date().isoformat()})
        port.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Interface in Nautobot from Port object."""
        if self.diffsync.job.debug:
            self.diffsync.job.logger.info(f"Deleting Interface {self.name} for {self.device}.")
        port = Interface.objects.get(id=self.uuid)
        super().delete()
        self.diffsync.objects_to_delete["ports"].append(port)
        return self


class NautobotPrefix(base.Prefix):
    """Nautobot implemention of Prefix DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Prefix in Nautobot from NautobotManagementPrefix objects."""
        if ids["namespace"] in diffsync.namespace_map:
            namespace = diffsync.namespace_map[ids["namespace"]]
        else:
            namespace = Namespace.objects.get_or_create(name=ids["namespace"])[0].id
        if diffsync.job.debug:
            diffsync.job.logger.info(f"Creating Prefix {ids['prefix']}.")
        new_prefix = Prefix(
            prefix=ids["prefix"],
            namespace_id=namespace,
            status_id=diffsync.status_map["Active"],
        )
        if ids["prefix"] == "0.0.0.0/0":
            new_prefix.type = "container"
            new_prefix.description = "Catch-all Prefix from DNA Center SSoT."
        if attrs.get("tenant"):
            new_prefix.tenant_id = diffsync.tenant_map[attrs["tenant"]]
        new_prefix.custom_field_data.update({"system_of_record": "DNA Center"})
        new_prefix.custom_field_data.update({"ssot_last_synchronized": datetime.today().date().isoformat()})
        new_prefix.validated_save()
        diffsync.prefix_map[ids["prefix"]] = new_prefix.id
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Prefix in Nautobot from Prefix object."""
        prefix = Prefix.objects.get(id=self.uuid)
        if "tenant" in attrs:
            if attrs.get("tenant"):
                prefix.tenant_id = self.diffsync.tenant_map[attrs["tenant"]]
            else:
                prefix.tenant = None
        prefix.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Prefix in Nautobot from Prefix object."""
        try:
            prefix = Prefix.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["prefixes"].append(prefix)
            super().delete()
            return self
        except Prefix.DoesNotExist as err:
            self.diffsync.job.logger.warning(f"Unable to find Prefix {self.prefix} {self.uuid} for deletion. {err}")


class NautobotIPAddress(base.IPAddress):
    """Nautobot implementation of the IPAddress DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create IPAddress in Nautobot from IPAddress object."""
        new_ip = IPAddress(
            address=f"{ids['host']}/{attrs['mask_length']}",
            namespace=diffsync.namespace_map[ids["namespace"]],
            status_id=diffsync.status_map["Active"],
        )
        if attrs.get("tenant"):
            new_ip.tenant_id = diffsync.tenant_map[attrs["tenant"]]
        new_ip.custom_field_data.update({"system_of_record": "DNA Center"})
        new_ip.custom_field_data.update({"ssot_last_synchronized": datetime.today().date().isoformat()})
        new_ip.validated_save()
        diffsync.ipaddr_map[ids["host"]] = new_ip.id
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update IPAddress in Nautobot from IPAddress object."""
        ipaddr = IPAddress.objects.get(id=self.uuid)
        if "tenant" in attrs:
            if attrs.get("tenant"):
                ipaddr.tenant_id = self.diffsync.tenant_map[attrs["tenant"]]
            else:
                ipaddr.tenant = None
        ipaddr.custom_field_data.update({"system_of_record": "DNA Center"})
        ipaddr.custom_field_data.update({"ssot_last_synchronized": datetime.today().date().isoformat()})
        try:
            ipaddr.validated_save()
        except ValidationError as err:
            self.diffsync.job.logger.warning(f"Unable to update {ipaddr}: {err}")
        return super().update(attrs)

    def delete(self):
        """Delete IPAddress in Nautobot from IPAddress object."""
        ipaddr = IPAddress.objects.get(id=self.uuid)
        super().delete()
        self.diffsync.objects_to_delete["ipaddresses"].append(ipaddr)
        return self


class NautobotIPAddressOnInterface(base.IPAddressOnInterface):
    """Nautobot implementation of DNA Center IPAddressOnInterface model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create IPAddressToInterface in Nautobot from IPAddressOnInterface object."""
        new_map = IPAddressToInterface(
            ip_address_id=diffsync.ipaddr_map[ids["host"]],
            interface_id=diffsync.port_map[ids["device"]][ids["port"]],
        )
        diffsync.objects_to_create["mappings"].append(new_map)
        if attrs.get("primary"):
            if ":" in ids["host"]:
                diffsync.objects_to_create["primary_ip6"].append(
                    (diffsync.device_map[ids["device"]], diffsync.ipaddr_map[ids["host"]])
                )
            else:
                diffsync.objects_to_create["primary_ip4"].append(
                    (diffsync.device_map[ids["device"]], diffsync.ipaddr_map[ids["host"]])
                )
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update IP Address in Nautobot from IPAddressOnInterface object."""
        mapping = IPAddressToInterface.objects.get(id=self.uuid)
        if attrs.get("primary"):
            if mapping.ip_address.ip_version == 4:
                mapping.interface.device.primary_ip4 = mapping.ip_address
            else:
                mapping.interface.device.primary_ip6 = mapping.ip_address
            mapping.interface.device.validated_save()
        mapping.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete IPAddressToInterface in Nautobot from NautobotIPAddressOnInterface object."""
        mapping = IPAddressToInterface.objects.get(id=self.uuid)
        super().delete()
        self.diffsync.job.logger.info(
            f"Deleting IPAddress to Interface mapping between {self.host} and {self.device}'s {self.port} port."
        )
        mapping.delete()
        return self
