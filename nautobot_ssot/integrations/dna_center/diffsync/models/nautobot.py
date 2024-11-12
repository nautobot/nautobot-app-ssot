"""Nautobot DiffSync models for DNA Center SSoT."""

from datetime import datetime

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from nautobot.dcim.models import (
    Device,
    DeviceType,
    Interface,
    Location,
    Manufacturer,
)
from nautobot.extras.models import Role
from nautobot.ipam.models import IPAddress, IPAddressToInterface, Namespace, Prefix

from nautobot_ssot.integrations.dna_center.diffsync.models import base
from nautobot_ssot.integrations.dna_center.utils.nautobot import (
    add_software_lcm,
    assign_version_to_device,
    verify_platform,
)

try:
    from nautobot_device_lifecycle_mgmt import SoftwareLCM  # noqa: F401

    LIFECYCLE_MGMT = True
except ImportError:
    LIFECYCLE_MGMT = False

try:
    from nautobot.dcim.models import SoftwareImageFile, SoftwareVersion  # noqa: F401

    SOFTWARE_VERSION_FOUND_IN_CORE = True
except ImportError:
    SOFTWARE_VERSION_FOUND_IN_CORE = False


class NautobotArea(base.Area):
    """Nautobot implementation of Area DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Region in Nautobot from Area object."""
        if adapter.job.debug:
            adapter.job.logger.info(f"Creating {adapter.job.area_loctype.name} {ids['name']} in {ids['parent']}.")
        new_area = Location(
            name=ids["name"],
            location_type=adapter.job.area_loctype,
            status_id=adapter.status_map["Active"],
        )
        if ids.get("parent"):
            try:
                parents_parent = "Global"
                if ids["parent"] == "Global":
                    parents_parent = None
                new_area.parent_id = adapter.region_map[parents_parent][ids["parent"]]
            except KeyError:
                adapter.job.logger.warning(
                    f"Unable to find {adapter.job.area_loctype.name} {ids['parent']} for {ids['name']}."
                )
        new_area.validated_save()
        if ids["parent"] not in adapter.region_map:
            adapter.region_map[ids["parent"]] = {}
        adapter.region_map[ids["parent"]][ids["name"]] = new_area.id
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def delete(self):
        """Delete Region in Nautobot from Area object."""
        if not settings.PLUGINS_CONFIG["nautobot_ssot"].get("dna_center_delete_locations"):
            self.adapter.job.logger.warning(
                f"`dna_center_delete_locations` setting is disabled so will skip deleting {self.name}."
            )
            return None
        area = Location.objects.get(id=self.uuid)
        if self.adapter.job.debug:
            self.adapter.job.logger.info(f"Deleting {self.job.area_loctype.name} {area.name}.")
        self.adapter.objects_to_delete["regions"].append(area)
        return self


class NautobotBuilding(base.Building):
    """Nautobot implementation of Building DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Site in Nautobot from Building object."""
        if adapter.job.debug:
            adapter.job.logger.info(f"Creating Site {ids['name']}.")
        new_building = Location(
            name=ids["name"],
            location_type=adapter.job.building_loctype,
            parent_id=adapter.region_map[attrs["area_parent"]][ids["area"]],
            physical_address=attrs["address"] if attrs.get("address") else "",
            status_id=adapter.status_map["Active"],
            latitude=attrs["latitude"],
            longitude=attrs["longitude"],
        )
        if attrs.get("tenant"):
            new_building.tenant_id = adapter.tenant_map[attrs["tenant"]]
        new_building.validated_save()
        adapter.site_map[ids["name"]] = new_building.id
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Site in Nautobot from Building object."""
        if not settings.PLUGINS_CONFIG["nautobot_ssot"].get("dna_center_update_locations"):
            self.adapter.job.logger.warning(
                f"`dna_center_update_locations` setting is disabled so will skip updating {self.name}."
            )
            return super().update(attrs)
        site = Location.objects.get(id=self.uuid)
        if self.adapter.job.debug:
            self.adapter.job.logger.info(f"Updating Site {site.name}.")
        if "address" in attrs:
            site.physical_address = attrs["address"]
        if "area" in attrs:
            site.parent_id = self.adapter.region_map[attrs["area_parent"]][attrs["area"]]
        if "latitude" in attrs:
            site.latitude = attrs["latitude"]
        if "longitude" in attrs:
            site.longitude = attrs["longitude"]
        if "tenant" in attrs:
            if attrs.get("tenant"):
                site.tenant_id = self.adapter.tenant_map[attrs["tenant"]]
            else:
                site.tenant = None
        site.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Site in Nautobot from Building object."""
        if not settings.PLUGINS_CONFIG["nautobot_ssot"].get("dna_center_delete_locations"):
            self.adapter.job.logger.warning(
                f"`dna_center_delete_locations` setting is disabled so will skip deleting {self.name}."
            )
            return None
        site = Location.objects.get(id=self.uuid)
        if self.adapter.job.debug:
            self.adapter.job.logger.info(f"Deleting {self.adapter.job.building_loctype.name} {site.name}.")
        self.adapter.objects_to_delete["sites"].append(site)
        return self


class NautobotFloor(base.Floor):
    """Nautobot implementation of Floor DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create LocationType: Floor in Nautobot from Floor object."""
        if adapter.job.debug:
            adapter.job.logger.info(f"Creating {adapter.job.floor_loctype.name} {ids['name']}.")
        new_floor = Location(
            name=ids["name"],
            status_id=adapter.status_map["Active"],
            parent_id=adapter.site_map[ids["building"]],
            location_type=adapter.job.floor_loctype,
        )
        if attrs.get("tenant"):
            new_floor.tenant_id = adapter.tenant_map[attrs["tenant"]]
        new_floor.validated_save()
        adapter.floor_map[ids["name"]] = new_floor.id
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update LocationType: Floor in Nautobot from Floor object."""
        floor = Location.objects.get(name=self.name, location_type=self.adapter.job.floor_loctype)
        if self.adapter.job.debug:
            self.adapter.job.logger.info(f"Updating {self.adapter.job.floor_loctype.name} {floor.name} with {attrs}")
        if "tenant" in attrs:
            if attrs.get("tenant"):
                floor.tenant_id = self.adapter.tenant_map[attrs["tenant"]]
            else:
                floor.tenant = None
        floor.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete LocationType: Floor in Nautobot from Floor object."""
        if not settings.PLUGINS_CONFIG["nautobot_ssot"].get("dna_center_delete_locations"):
            self.adapter.job.logger.warning(
                f"`dna_center_delete_locations` setting is disabled so will skip deleting {self.name}."
            )
            return None
        floor = Location.objects.get(id=self.uuid)
        if self.adapter.job.debug:
            self.adapter.job.logger.info(
                f"Deleting {self.adapter.job.floor_loctype.name} {floor.name} in {floor.parent.name}."
            )
        self.adapter.objects_to_delete["floors"].append(floor)
        return self


class NautobotDevice(base.Device):
    """Nautobot implementation of DNA Center Device model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Device in Nautobot from NautobotDevice object."""
        if adapter.job.debug:
            adapter.job.logger.info(f"Creating Device {ids['name']}.")
        manufacturer, _ = Manufacturer.objects.get_or_create(name=attrs["vendor"])
        device_role, created = Role.objects.get_or_create(name=attrs["role"])
        if created:
            device_role.content_types.add(ContentType.objects.get_for_model(Device))
            device_role.validated_save()
        device_type, _ = DeviceType.objects.get_or_create(model=attrs["model"], manufacturer=manufacturer)
        platform = verify_platform(platform_name=attrs["platform"], manu=manufacturer.id)
        new_device = Device(
            name=ids["name"],
            status_id=adapter.status_map[attrs["status"]],
            role=device_role,
            location_id=adapter.site_map[attrs["site"]],
            device_type=device_type,
            serial=attrs["serial"],
            platform_id=platform.id,
            controller_managed_device_group=adapter.job.controller_group,
        )
        if attrs.get("floor"):
            new_device.location_id = adapter.floor_map[attrs["floor"]]
        if attrs.get("tenant"):
            new_device.tenant_id = adapter.tenant_map[attrs["tenant"]]
        if attrs.get("version"):
            if LIFECYCLE_MGMT:
                lcm_obj = add_software_lcm(adapter=adapter, platform=platform.network_driver, version=attrs["version"])
                assign_version_to_device(adapter=adapter, device=new_device, software_lcm=lcm_obj)
            if SOFTWARE_VERSION_FOUND_IN_CORE:
                soft_version = SoftwareVersion.objects.get_or_create(
                    version=attrs["version"], platform=platform, defaults={"status_id": adapter.status_map["Active"]}
                )[0]
                image, _ = SoftwareImageFile.objects.get_or_create(
                    image_file_name=f"{platform.name}-{attrs['version']}-dnac-ssot-placeholder",
                    software_version=soft_version,
                    status_id=adapter.status_map["Active"],
                )
                image.device_types.add(device_type)
                new_device.software_version = soft_version
        new_device.custom_field_data.update({"system_of_record": "DNA Center"})
        new_device.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        adapter.objects_to_create["devices"].append(new_device)
        adapter.device_map[ids["name"]] = new_device.id
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Device in Nautobot from NautobotDevice object."""
        device = Device.objects.get(id=self.uuid)
        if self.adapter.job.debug:
            self.adapter.job.logger.info(f"Updating Device {device.name} with {attrs}")
        if "status" in attrs:
            device.status_id = self.adapter.status_map[attrs["status"]]
        if "role" in attrs:
            dev_role, created = Role.objects.get_or_create(name=attrs["role"])
            device.role = dev_role
            if created:
                dev_role.content_types.add(ContentType.objects.get_for_model(Device))
        if attrs.get("site"):
            device.location_id = self.adapter.site_map[attrs["site"]]
        if attrs.get("floor"):
            device.location_id = self.adapter.floor_map[attrs["floor"]]
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
                device.tenant_id = self.adapter.tenant_map[attrs["tenant"]]
            else:
                device.tenant = None
        if "controller_group" in attrs:
            device.controller_managed_device_group = self.adapter.job.controller_group
        if "version" in attrs:
            if LIFECYCLE_MGMT:
                platform_network_driver = attrs["platform"] if attrs.get("platform") else self.platform
                lcm_obj = add_software_lcm(
                    adapter=self.adapter, platform=platform_network_driver, version=attrs["version"]
                )
                assign_version_to_device(adapter=self.adapter, device=device, software_lcm=lcm_obj)
            if SOFTWARE_VERSION_FOUND_IN_CORE:
                if attrs.get("platform"):
                    platform = attrs["platform"]
                else:
                    platform = self.platform
                device.software_version = SoftwareVersion.objects.get_or_create(
                    version=attrs["version"],
                    platform__name=platform,
                    defaults={"status_id": self.adapter.status_map["Active"]},
                )[0]
        device.custom_field_data.update({"system_of_record": "DNA Center"})
        device.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        device.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Device in Nautobot from NautobotDevice object."""
        dev = Device.objects.get(id=self.uuid)
        if self.adapter.job.debug:
            self.adapter.job.logger.info(f"Deleting Device: {dev.name}.")
        super().delete()
        self.adapter.objects_to_delete["devices"].append(dev)
        return self


class NautobotPort(base.Port):
    """Nautobot implementation of Port DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Interface in Nautobot from Port object."""
        if adapter.job.debug:
            adapter.job.logger.info(f"Creating Port {ids['name']} for Device {ids['device']}.")
        new_port = Interface(
            name=ids["name"],
            device_id=adapter.device_map[ids["device"]],
            description=attrs["description"],
            enabled=attrs["enabled"],
            type=attrs["port_type"],
            mode=attrs["port_mode"],
            mac_address=attrs["mac_addr"],
            mtu=attrs["mtu"],
            status_id=adapter.status_map[attrs["status"]],
            mgmt_only=True if "Management" in ids["name"] else False,
        )
        new_port.custom_field_data.update({"system_of_record": "DNA Center"})
        new_port.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        adapter.objects_to_create["interfaces"].append(new_port)
        if ids["device"] not in adapter.port_map:
            adapter.port_map[ids["device"]] = {}
        adapter.port_map[ids["device"]][ids["name"]] = new_port.id
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Interface in Nautobot from Port object."""
        port = Interface.objects.get(id=self.uuid)
        if self.adapter.job.debug:
            self.adapter.job.logger.info(f"Updating Port {port.name} for Device {port.device.name}.")
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
            port.status_id = self.adapter.status_map[attrs["status"]]
        if "enabled" in attrs:
            port.enabled = attrs["enabled"]
        port.custom_field_data.update({"system_of_record": "DNA Center"})
        port.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        port.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Interface in Nautobot from Port object."""
        if self.adapter.job.debug:
            self.adapter.job.logger.info(f"Deleting Interface {self.name} for {self.device}.")
        port = Interface.objects.get(id=self.uuid)
        super().delete()
        self.adapter.objects_to_delete["ports"].append(port)
        return self


class NautobotPrefix(base.Prefix):
    """Nautobot implemention of Prefix DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Prefix in Nautobot from NautobotManagementPrefix objects."""
        if ids["namespace"] in adapter.namespace_map:
            namespace = adapter.namespace_map[ids["namespace"]]
        else:
            namespace = Namespace.objects.get_or_create(name=ids["namespace"])[0].id
        if adapter.job.debug:
            adapter.job.logger.info(f"Creating Prefix {ids['prefix']}.")
        new_prefix = Prefix(
            prefix=ids["prefix"],
            namespace_id=namespace,
            status_id=adapter.status_map["Active"],
        )
        if ids["prefix"] == "0.0.0.0/0":
            new_prefix.type = "container"
            new_prefix.description = "Catch-all Prefix from DNA Center SSoT."
        if attrs.get("tenant"):
            new_prefix.tenant_id = adapter.tenant_map[attrs["tenant"]]
        new_prefix.custom_field_data.update({"system_of_record": "DNA Center"})
        new_prefix.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        new_prefix.validated_save()
        adapter.prefix_map[ids["prefix"]] = new_prefix.id
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Prefix in Nautobot from Prefix object."""
        prefix = Prefix.objects.get(id=self.uuid)
        if "tenant" in attrs:
            if attrs.get("tenant"):
                prefix.tenant_id = self.adapter.tenant_map[attrs["tenant"]]
            else:
                prefix.tenant = None
        prefix.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Prefix in Nautobot from Prefix object."""
        try:
            prefix = Prefix.objects.get(id=self.uuid)
            self.adapter.objects_to_delete["prefixes"].append(prefix)
            super().delete()
            return self
        except Prefix.DoesNotExist as err:
            self.adapter.job.logger.warning(f"Unable to find Prefix {self.prefix} {self.uuid} for deletion. {err}")


class NautobotIPAddress(base.IPAddress):
    """Nautobot implementation of the IPAddress DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddress in Nautobot from IPAddress object."""
        new_ip = IPAddress(
            address=f"{ids['host']}/{attrs['mask_length']}",
            namespace=adapter.namespace_map[ids["namespace"]],
            status_id=adapter.status_map["Active"],
        )
        if attrs.get("tenant"):
            new_ip.tenant_id = adapter.tenant_map[attrs["tenant"]]
        new_ip.custom_field_data.update({"system_of_record": "DNA Center"})
        new_ip.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        new_ip.validated_save()
        adapter.ipaddr_map[ids["host"]] = new_ip.id
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update IPAddress in Nautobot from IPAddress object."""
        ipaddr = IPAddress.objects.get(id=self.uuid)
        if "mask_length" in attrs:
            ipaddr.mask_length = attrs["mask_length"]
        if "tenant" in attrs:
            if attrs.get("tenant"):
                ipaddr.tenant_id = self.adapter.tenant_map[attrs["tenant"]]
            else:
                ipaddr.tenant = None
        ipaddr.custom_field_data.update({"system_of_record": "DNA Center"})
        ipaddr.custom_field_data.update({"last_synced_from_sor": datetime.today().date().isoformat()})
        try:
            ipaddr.validated_save()
        except ValidationError as err:
            self.adapter.job.logger.warning(f"Unable to update {ipaddr}: {err}")
        return super().update(attrs)

    def delete(self):
        """Delete IPAddress in Nautobot from IPAddress object."""
        ipaddr = IPAddress.objects.get(id=self.uuid)
        super().delete()
        self.adapter.objects_to_delete["ipaddresses"].append(ipaddr)
        return self


class NautobotIPAddressOnInterface(base.IPAddressOnInterface):
    """Nautobot implementation of DNA Center IPAddressOnInterface model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddressToInterface in Nautobot from IPAddressOnInterface object."""
        new_map = IPAddressToInterface(
            ip_address_id=adapter.ipaddr_map[ids["host"]],
            interface_id=adapter.port_map[ids["device"]][ids["port"]],
        )
        adapter.objects_to_create["mappings"].append(new_map)
        if attrs.get("primary"):
            if ":" in ids["host"]:
                adapter.objects_to_create["primary_ip6"].append(
                    (adapter.device_map[ids["device"]], adapter.ipaddr_map[ids["host"]])
                )
            else:
                adapter.objects_to_create["primary_ip4"].append(
                    (adapter.device_map[ids["device"]], adapter.ipaddr_map[ids["host"]])
                )
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

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
        self.adapter.job.logger.info(
            f"Deleting IPAddress to Interface mapping between {self.host} and {self.device}'s {self.port} port."
        )
        mapping.delete()
        return self
