"""DiffSyncModel DCIM subclasses for Nautobot Device42 data sync."""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from nautobot.circuits.models import CircuitTermination as OrmCT
from nautobot.core.settings_funcs import is_truthy
from nautobot.dcim.models import Cable as OrmCable
from nautobot.dcim.models import Device as OrmDevice
from nautobot.dcim.models import DeviceType as OrmDeviceType
from nautobot.dcim.models import FrontPort as OrmFrontPort
from nautobot.dcim.models import Interface as OrmInterface
from nautobot.dcim.models import Manufacturer as OrmManufacturer
from nautobot.dcim.models import Rack as OrmRack
from nautobot.dcim.models import RackGroup as OrmRackGroup
from nautobot.dcim.models import Location as OrmSite
from nautobot.dcim.models import LocationType as OrmLocationType
from nautobot.dcim.models import VirtualChassis as OrmVC
from nautobot.extras.models import RelationshipAssociation
from nautobot.extras.models import Status as OrmStatus
from nautobot_ssot.jobs.base import DataSource
from nautobot_ssot.integrations.device42.constant import DEFAULTS, INTF_SPEED_MAP, PLUGIN_CFG
from nautobot_ssot.integrations.device42.diffsync.models.base.dcim import (
    Building,
    Cluster,
    Connection,
    Device,
    Hardware,
    Port,
    Rack,
    Room,
    Vendor,
)
from nautobot_ssot.integrations.device42.utils import device42, nautobot

try:
    from nautobot_device_lifecycle_mgmt.models import SoftwareLCM

    LIFECYCLE_MGMT = True
except (ImportError, RuntimeError):
    print("Device Lifecycle app isn't installed so will revert to CustomField for OS version.")
    LIFECYCLE_MGMT = False


class NautobotBuilding(Building):
    """Nautobot Building model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Site object in Nautobot."""
        diffsync.job.logger.info(f"Creating Site {ids['name']}.")
        def_site_status = diffsync.status_map[DEFAULTS.get("site_status")]
        loc_type = OrmLocationType.objects.get_or_create(name="Site")[0]
        new_site = OrmSite(
            name=ids["name"],
            status_id=def_site_status,
            physical_address=attrs["address"] if attrs.get("address") else "",
            latitude=round(Decimal(attrs["latitude"] if attrs["latitude"] else 0.0), 6),
            longitude=round(Decimal(attrs["longitude"] if attrs["longitude"] else 0.0), 6),
            location_type=loc_type,
            contact_name=attrs["contact_name"] if attrs.get("contact_name") else "",
            contact_phone=attrs["contact_phone"] if attrs.get("contact_phone") else "",
        )
        new_site.validated_save()
        if attrs.get("tags"):
            for _tag in nautobot.get_tags(attrs["tags"]):
                new_site.tags.add(_tag)
            _facility = device42.get_facility(tags=attrs["tags"])
            if _facility:
                new_site.facility = _facility.upper()
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=new_site)
        new_site.validated_save()
        diffsync.site_map[ids["name"]] = new_site.id
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Site object in Nautobot."""
        _site = OrmSite.objects.get(id=self.uuid)
        self.diffsync.job.logger.info(f"Updating building {_site.name}.")
        if "address" in attrs:
            _site.physical_address = attrs["address"]
        if "latitude" in attrs:
            _site.latitude = round(Decimal(attrs["latitude"]), 6)
        if "longitude" in attrs:
            _site.longitude = round(Decimal(attrs["longitude"]), 6)
        if "contact_name" in attrs:
            _site.contact_name = attrs["contact_name"]
        if "contact_phone" in attrs:
            _site.contact_phone = attrs["contact_phone"]
        if "tags" in attrs:
            if attrs.get("tags"):
                nautobot.update_tags(tagged_obj=_site, new_tags=attrs["tags"])
                _facility = device42.get_facility(tags=attrs["tags"])
                if _facility:
                    _site.facility = _facility.upper()
            else:
                _site.tags.clear()
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_site)
        _site.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Site object from Nautobot.

        Because Site has a direct relationship with many other objects it can't be deleted before anything else.
        The self.diffsync.objects_to_delete dictionary stores all objects for deletion and removes them from Nautobot
        in the correct order. This is used in the Nautobot adapter sync_complete function.
        """
        if PLUGIN_CFG.get("device42_delete_on_sync"):
            super().delete()
            self.diffsync.job.logger.info(f"Site {self.name} will be deleted.")
            site = OrmSite.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["site"].append(site)  # pylint: disable=protected-access
        return self


class NautobotRoom(Room):
    """Nautobot Room model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create RackGroup object in Nautobot."""
        diffsync.job.logger.info(f"Creating RackGroup {ids['name']}.")
        new_rg = OrmRackGroup(
            name=ids["name"],
            location_id=diffsync.site_map[ids["building"]],
            description=attrs["notes"] if attrs.get("notes") else "",
        )
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=new_rg)
        new_rg.validated_save()
        if ids["building"] not in diffsync.room_map:
            diffsync.room_map[ids["building"]] = {}
        diffsync.room_map[ids["building"]][ids["name"]] = new_rg.id
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update RackGroup object in Nautobot."""
        _rg = OrmRackGroup.objects.get(id=self.uuid)
        self.diffsync.job.logger.info(f"Updating RackGroup {_rg.name}.")
        if "notes" in attrs:
            _rg.description = attrs["notes"]
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_rg)
        _rg.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete RackGroup object from Nautobot."""
        if PLUGIN_CFG.get("device42_delete_on_sync"):
            super().delete()
            self.diffsync.job.logger.info(f"RackGroup {self.name} will be deleted.")
            rackgroup = OrmRackGroup.objects.get(id=self.uuid)
            rackgroup.delete()
        return self


class NautobotRack(Rack):
    """Nautobot Rack model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Rack object in Nautobot."""
        diffsync.job.logger.info(f"Creating Rack {ids['name']}.")
        _site = diffsync.site_map[ids["building"]]
        _rg = diffsync.room_map[ids["building"]][ids["room"]]
        new_rack = OrmRack(
            name=ids["name"],
            location_id=_site,
            rack_group_id=_rg,
            status_id=diffsync.status_map[DEFAULTS.get("rack_status")],
            u_height=attrs["height"] if attrs.get("height") else 1,
            desc_units=not (is_truthy(attrs["numbering_start_from_bottom"])),
        )
        if attrs.get("tags"):
            for _tag in nautobot.get_tags(attrs["tags"]):
                new_rack.tags.add(_tag)
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=new_rack)
        new_rack.validated_save()
        if ids["building"] not in diffsync.rack_map:
            diffsync.rack_map[ids["building"]] = {}
        if ids["room"] not in diffsync.rack_map[ids["building"]]:
            diffsync.rack_map[ids["building"]][ids["room"]] = {}
        diffsync.rack_map[ids["building"]][ids["room"]][ids["name"]] = new_rack.id
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Rack object in Nautobot."""
        _rack = OrmRack.objects.get(id=self.uuid)
        self.diffsync.job.logger.info(f"Updating Rack {_rack.name}.")
        if "height" in attrs:
            _rack.u_height = attrs["height"]
        if "numbering_start_from_bottom" in attrs:
            _rack.desc_units = not (is_truthy(attrs["numbering_start_from_bottom"]))
        if "tags" in attrs:
            if attrs.get("tags"):
                nautobot.update_tags(tagged_obj=_rack, new_tags=attrs["tags"])
            else:
                _rack.tags.clear()
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_rack)
        _rack.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Rack object from Nautobot.

        Because Rack has a direct relationship with Devices it can't be deleted before they are.
        The self.diffsync.objects_to_delete dictionary stores all objects for deletion and removes them from Nautobot
        in the correct order. This is used in the Nautobot adapter sync_complete function.
        """
        if PLUGIN_CFG.get("device42_delete_on_sync"):
            super().delete()
            self.diffsync.job.logger.info(f"Rack {self.name} will be deleted.")
            rack = OrmRack.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["rack"].append(rack)  # pylint: disable=protected-access
        return self


class NautobotVendor(Vendor):
    """Nautobot Vendor model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Manufacturer object in Nautobot."""
        diffsync.job.logger.info(f"Creating Manufacturer {ids['name']}.")
        try:
            diffsync.vendor_map[ids["name"]]
        except KeyError:
            new_manu = OrmManufacturer(
                name=ids["name"],
            )
            if attrs.get("custom_fields"):
                nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=new_manu)
            new_manu.validated_save()
            diffsync.vendor_map[ids["name"]] = new_manu.id
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Manufacturer object in Nautobot."""
        _manu = OrmManufacturer.objects.get(id=self.uuid)
        self.diffsync.job.logger.info(f"Updating Manufacturer {_manu.name}.")
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_manu)
        _manu.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Manufacturer object from Nautobot.

        Because Manufacturer has a direct relationship with DeviceTypes and other objects it can't be deleted before them.
        The self.diffsync.objects_to_delete dictionary stores all objects for deletion and removes them from Nautobot
        in the correct order. This is used in the Nautobot adapter sync_complete function.
        """
        if PLUGIN_CFG.get("device42_delete_on_sync"):
            super().delete()
            self.diffsync.job.logger.info(f"Manufacturer {self.name} will be deleted.")
            _manu = OrmManufacturer.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["manufacturer"].append(_manu)  # pylint: disable=protected-access
        return self


class NautobotHardware(Hardware):
    """Nautobot Hardware model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create DeviceType object in Nautobot."""
        diffsync.job.logger.info(f"Creating DeviceType {ids['name']}.")
        try:
            diffsync.devicetype_map[ids["name"]]
        except KeyError:
            new_dt = OrmDeviceType(
                model=ids["name"],
                manufacturer_id=diffsync.vendor_map[attrs["manufacturer"]],
                part_number=attrs["part_number"] if attrs.get("part_number") else "",
                u_height=int(attrs["size"]) if attrs.get("size") else 1,
                is_full_depth=bool(attrs.get("depth") == "Full Depth"),
            )
            if attrs.get("custom_fields"):
                nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=new_dt)
            new_dt.validated_save()
            diffsync.devicetype_map[ids["name"]] = new_dt.id
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update DeviceType object in Nautobot."""
        _dt = OrmDeviceType.objects.get(id=self.uuid)
        self.diffsync.job.logger.debug(f"Updating DeviceType {_dt.model}.")
        if "manufacturer" in attrs:
            _dt.manufacturer = OrmManufacturer.objects.get(name=attrs["manufacturer"])
        if "part_number" in attrs:
            if attrs["part_number"] is not None:
                _dt.part_number = attrs["part_number"]
            else:
                _dt.part_number = ""
        if "size" in attrs:
            _dt.u_height = int(attrs["size"])
        if "depth" in attrs:
            _dt.is_full_depth = bool(attrs["depth"] == "Full Depth")
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_dt)
        _dt.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete DeviceType object from Nautobot.

        Because DeviceType has a direct relationship with Devices it can't be deleted before all Devices are.
        The self.diffsync.objects_to_delete dictionary stores all objects for deletion and removes them from Nautobot
        in the correct order. This is used in the Nautobot adapter sync_complete function.
        """
        if PLUGIN_CFG.get("device42_delete_on_sync"):
            super().delete()
            self.diffsync.job.logger.info(f"DeviceType {self.name} will be deleted.")
            _dt = OrmDeviceType.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["device_type"].append(_dt)  # pylint: disable=protected-access
        return self


class NautobotCluster(Cluster):
    """Nautobot Cluster model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Virtual Chassis object in Nautobot.

        As the master node of the VC needs to be a regular Device, we'll create that and then the VC.
        Member devices will be added to VC at Device creation.
        """
        diffsync.job.logger.debug(f"Creating VirtualChassis {ids['name']}.")
        new_vc = OrmVC(
            name=ids["name"],
        )
        new_vc.validated_save()
        if attrs.get("tags"):
            for _tag in nautobot.get_tags(attrs["tags"]):
                new_vc.tags.add(_tag)
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=new_vc)
        new_vc.validated_save()
        diffsync.cluster_map[ids["name"]] = new_vc.id
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Virtual Chassis object in Nautobot."""
        _vc = OrmVC.objects.get(id=self.uuid)
        self.diffsync.job.logger.debug(f"Updating VirtualChassis {_vc.name}.")
        if "tags" in attrs:
            if attrs.get("tags"):
                nautobot.update_tags(tagged_obj=_vc, new_tags=attrs["tags"])
            else:
                _vc.tags.clear()
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_vc)
        _vc.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Virtual Chassis object from Nautobot.

        Because Virtual Chassis has a direct relationship with Devices it can't be deleted before they are.
        The self.diffsync.objects_to_delete dictionary stores all objects for deletion and removes them from Nautobot
        in the correct order. This is used in the Nautobot adapter sync_complete function.
        """
        if PLUGIN_CFG.get("device42_delete_on_sync"):
            super().delete()
            self.diffsync.job.logger.info(f"Virtual Chassis {self.name} will be deleted.")
            _cluster = OrmVC.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["cluster"].append(_cluster)  # pylint: disable=protected-access
        return self


class NautobotDevice(Device):
    """Nautobot Device model."""

    @staticmethod
    def _get_site(diffsync, building: str):
        """Get Site ID from Building name."""
        try:
            _site = diffsync.site_map[building]
            return _site
        except KeyError:
            diffsync.job.logger.warning(f"Unable to find Site {building}.")
        return None

    @classmethod
    def create(cls, diffsync, ids, attrs):  # pylint: disable=inconsistent-return-statements
        """Create Device object in Nautobot."""
        diffsync.job.logger.info(f"Creating Device {ids['name']}.")
        if attrs["in_service"]:
            _status = diffsync.status_map["Active"]
        else:
            _status = diffsync.status_map["Offline"]
        if attrs.get("tags") and len(attrs["tags"]) > 0:
            _role = nautobot.verify_device_role(
                diffsync=diffsync, role_name=device42.find_device_role_from_tags(tag_list=attrs["tags"])
            )
        else:
            _role = nautobot.verify_device_role(diffsync=diffsync, role_name=DEFAULTS.get("device_role"))
        try:
            _dt = diffsync.devicetype_map[attrs["hardware"]]
        except KeyError:
            diffsync.job.logger.warning(f"Unable to find DeviceType {attrs['hardware']}.")
            return None
        _site = cls._get_site(diffsync, building=attrs["building"])
        if not _site:
            diffsync.job.logger.warning(f"Can't create {ids['name']} as unable to determine Site.")
            return None
        new_device = OrmDevice(
            name=ids["name"][:64],
            status_id=_status,
            location_id=_site,
            device_type_id=_dt,
            role_id=_role,
            serial=attrs["serial_no"] if attrs.get("serial_no") else "",
        )
        new_device.validated_save()
        if attrs.get("rack"):
            new_device.rack_id = diffsync.rack_map[attrs["building"]][attrs["room"]][attrs["rack"]]
            new_device.position = int(attrs["rack_position"]) if attrs["rack_position"] else None
            new_device.face = attrs["rack_orientation"] if attrs["rack_orientation"] else "front"
        if attrs.get("os"):
            devicetype = diffsync.get(NautobotHardware, attrs["hardware"])
            new_device.platform_id = nautobot.verify_platform(
                diffsync=diffsync,
                platform_name=attrs["os"],
                manu=diffsync.vendor_map[devicetype.manufacturer],
            )
        if attrs.get("os_version"):
            if LIFECYCLE_MGMT and attrs.get("os"):
                manu_id = new_device.device_type.manufacturer.id
                if manu_id:
                    soft_lcm = cls._add_software_lcm(
                        diffsync=diffsync, os=attrs["os"], version=attrs["os_version"], manufacturer=manu_id
                    )
                    cls._assign_version_to_device(diffsync=diffsync, device=new_device.id, software_lcm=soft_lcm)
            else:
                attrs["custom_fields"].append({"key": "OS Version", "value": attrs["os_version"]})
        if attrs.get("cluster_host"):
            try:
                _vc = diffsync.cluster_map[attrs["cluster_host"]]
                new_device.virtual_chassis_id = _vc
                new_device.vc_position = attrs["vc_position"]
                new_device.validated_save()
                if attrs.get("master_device") and attrs["master_device"]:
                    new_device.virtual_chassis.master = new_device
                    new_device.validated_save()
            except KeyError:
                diffsync.job.logger.warning(f"Unable to find Virtual Chassis {attrs['cluster_host']}")
        if attrs.get("tags"):
            new_device.tags.set(attrs["tags"])
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=new_device)
        new_device.validated_save()
        diffsync.device_map[ids["name"]] = new_device.id
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Device object in Nautobot."""
        _dev = OrmDevice.objects.get(id=self.uuid)
        self.diffsync.job.logger.info(f"Updating Device {self.name} in {_dev.location.name} with {attrs}")
        if "building" in attrs:
            location_id = None
            try:
                location_id = OrmSite.objects.get(name=attrs["building"])
            except OrmSite.DoesNotExist:
                for site in self.diffsync.objects_to_create["sites"]:
                    if site.name == attrs["building"]:
                        location_id = self._get_site(diffsync=self.diffsync, building=attrs["building"])
            if location_id:
                _dev.location_id = location_id
        if "rack_position" in attrs:
            _dev.position = int(attrs["rack_position"]) if attrs["rack_position"] else None
        if "rack_orientation" in attrs:
            _dev.face = attrs["rack_orientation"]
        if "rack" in attrs:
            try:
                _dev.rack = OrmRack.objects.get(name=attrs["rack"], group__name=self.room)
            except OrmRack.DoesNotExist as err:
                self.diffsync.job.logger.warning(f"Unable to find rack {attrs['rack']} in {self.room} {err}")
        if "rack" in attrs and "room" in attrs:
            try:
                _dev.rack = OrmRack.objects.get(name=attrs["rack"], group__name=attrs["room"])
                _dev.location = _dev.rack.location
            except OrmRack.DoesNotExist as err:
                if self.diffsync.job.debug:
                    self.diffsync.job.logger.warning(f"Unable to find rack {attrs['rack']} in {attrs['room']} {err}")
        if "hardware" in attrs:
            for new_dt in self.diffsync.objects_to_create["devicetypes"]:
                if new_dt.model == attrs["hardware"]:
                    new_dt.validated_save()
                    self.diffsync.objects_to_create["devicetypes"].remove(new_dt)
            _dev.device_type_id = self.diffsync.devicetype_map[attrs["hardware"]]
        if "os" in attrs:
            if attrs.get("hardware"):
                _hardware = self.diffsync.get(NautobotHardware, attrs["hardware"])
            else:
                _hardware = self.diffsync.get(NautobotHardware, self.hardware)
            _dev.platform_id = nautobot.verify_platform(
                diffsync=self.diffsync,
                platform_name=attrs["os"],
                manu=self.diffsync.vendor_map[_hardware.manufacturer],
            )
        if "os_version" in attrs:
            if attrs.get("os"):
                _os = attrs["os"]
            else:
                _os = self.os
            if attrs.get("os_version"):
                if LIFECYCLE_MGMT:
                    soft_lcm = self._add_software_lcm(
                        diffsync=self.diffsync,
                        os=_os,
                        version=attrs["os_version"],
                        manufacturer=_dev.device_type.manufacturer.id,
                    )
                    self._assign_version_to_device(diffsync=self.diffsync, device=_dev.id, software_lcm=soft_lcm)
                else:
                    attrs["custom_fields"].append(
                        {
                            "key": "OS Version",
                            "value": attrs["os_version"] if attrs.get("os_version") else self.os_version,
                        }
                    )
        if "in_service" in attrs:
            if attrs["in_service"]:
                _status = self.diffsync.status_map["Active"]
            else:
                _status = self.diffsync.status_map["Offline"]
            _dev.status_id = _status
        if "serial_no" in attrs:
            _dev.serial = attrs["serial_no"]
        if _dev.role.name == "Unknown" and self.tags:
            _dev.role_id = nautobot.verify_device_role(
                diffsync=self.diffsync, role_name=device42.find_device_role_from_tags(tag_list=self.tags)
            )
        if "tags" in attrs:
            if attrs.get("tags"):
                _dev.role_id = nautobot.verify_device_role(
                    diffsync=self.diffsync, role_name=device42.find_device_role_from_tags(tag_list=attrs["tags"])
                )
            else:
                _dev.role_id = nautobot.verify_device_role(
                    diffsync=self.diffsync, role_name=DEFAULTS.get("device_role")
                )
            _dev.tags.set(attrs["tags"])
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_dev)
        # ensure that VC Master Device is set to that
        if "cluster_host" in attrs or "master_device" in attrs:
            if attrs.get("cluster_host"):
                _clus_host = attrs["cluster_host"]
            else:
                _clus_host = self.cluster_host
            try:
                _vc = self.diffsync.cluster_map[_clus_host]
                _dev.virtual_chassis_id = _vc
                _dev.vc_position = self.vc_position
                _dev.validated_save()
                if attrs.get("master_device"):
                    vc = OrmVC.objects.get(id=_vc)
                    vc.master = _dev
                    vc.validated_save()
            except KeyError:
                self.diffsync.job.logger.warning(f"Unable to find Virtual Chassis {_clus_host}")
        if "vc_position" in attrs:
            # need to ensure the new position isn't already taken
            try:
                if attrs.get("cluster_host"):
                    vc = OrmVC.objects.get(name=attrs["cluster_host"])
                else:
                    vc = OrmVC.objects.get(name=self.cluster_host)
                try:
                    dev = OrmDevice.objects.get(virtual_chassis=vc, vc_position=attrs["vc_position"])
                    dev.vc_position = None
                    dev.virtual_chassis = None
                    dev.validated_save()
                except OrmDevice.DoesNotExist:
                    self.diffsync.job.logger.info(f"Didn't find Device in VC position: {attrs['vc_position']}.")
            except OrmVC.DoesNotExist as err:
                self.diffsync.job.logger.warning(
                    f"Unable to find Virtual Chassis {attrs['cluster_host'] if attrs.get('cluster_host') else self.cluster_host}. {err}"
                )
            _dev.vc_position = attrs["vc_position"]
        try:
            _dev.validated_save()
            return super().update(attrs)
        except ValidationError as err:
            self.diffsync.job.logger.warning(f"Error updating Device {self.name} with {attrs}. {err}")
            return None

    def delete(self):
        """Delete Device object from Nautobot.

        Because Device has a direct relationship with Ports and IP Addresses it can't be deleted before they are.
        The self.diffsync.objects_to_delete dictionary stores all objects for deletion and removes them from Nautobot
        in the correct order. This is used in the Nautobot adapter sync_complete function.
        """
        if PLUGIN_CFG.get("device42_delete_on_sync"):
            super().delete()
            self.diffsync.job.logger.info(f"Device {self.name} will be deleted.")
            _dev = OrmDevice.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["device"].append(_dev)  # pylint: disable=protected-access
        return self

    @staticmethod
    def _add_software_lcm(diffsync: DataSource, os: str, version: str, manufacturer: UUID):
        """Add OS Version as SoftwareLCM if Device Lifecycle App found."""
        _platform = nautobot.verify_platform(diffsync=diffsync, platform_name=os, manu=manufacturer)
        try:
            os_ver = diffsync.softwarelcm_map[os][version]
        except KeyError:
            os_ver = SoftwareLCM(
                device_platform_id=_platform,
                version=version,
            )
            try:
                os_ver.validated_save()
            except ValidationError as err:
                diffsync.job.logger.warning(f"Error trying to create SoftwareLCM: {err}.")
                return None
            if os not in diffsync.softwarelcm_map:
                diffsync.softwarelcm_map[os] = {}
            diffsync.softwarelcm_map[os][version] = os_ver.id
            os_ver = os_ver.id
        return os_ver

    @staticmethod
    def _assign_version_to_device(diffsync, device: UUID, software_lcm: UUID):
        """Add Relationship between Device and SoftwareLCM."""
        try:
            dev = OrmDevice.objects.get(id=device)
            relations = dev.get_relationships()
            software_relation_id = diffsync.relationship_map["Software on Device"]
            for _, relationships in relations.items():
                for relationship, queryset in relationships.items():
                    if relationship.id == software_relation_id:
                        if diffsync.job.debug:
                            diffsync.job.logger.warning(
                                f"Deleting Software Version Relationships for {dev.name} to assign a new version."
                            )
                        queryset.delete()
        except OrmDevice.DoesNotExist:
            diffsync.job.logger.warning(f"Unable to find Device {device} to assign software to.")
        new_assoc = RelationshipAssociation(
            relationship_id=diffsync.relationship_map["Software on Device"],
            source_type=ContentType.objects.get_for_model(SoftwareLCM),
            source_id=software_lcm,
            destination_type=ContentType.objects.get_for_model(OrmDevice),
            destination_id=device,
        )
        new_assoc.validated_save()


class NautobotPort(Port):
    """Nautobot Port model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):  # pylint: disable=inconsistent-return-statements
        """Create Interface object in Nautobot."""
        try:
            _dev = diffsync.device_map[ids["device"]]
        except KeyError:
            diffsync.job.logger.warning(
                f"Attempting to create Interface {ids['name']} for {ids['device']} failed as {ids['device']} doesn't exist."
            )
            return None
        new_intf = OrmInterface(
            name=ids["name"],
            device_id=_dev,
            enabled=is_truthy(attrs["enabled"]),
            mtu=attrs["mtu"] if attrs.get("mtu") else 1500,
            description=attrs["description"],
            type=attrs["type"],
            mac_address=attrs["mac_addr"][:12] if attrs.get("mac_addr") else None,
            mode=attrs["mode"],
            status_id=diffsync.status_map[attrs["status"]],
        )
        new_intf.validated_save()
        if attrs.get("tags"):
            for _tag in nautobot.get_tags(attrs["tags"]):
                new_intf.tags.add(_tag)
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=new_intf)
        if attrs.get("vlans"):
            nautobot.apply_vlans_to_port(
                diffsync=diffsync, device_name=ids["device"], mode=attrs["mode"], vlans=attrs["vlans"], port=new_intf
            )
        new_intf.validated_save()
        if ids["device"] not in diffsync.port_map:
            diffsync.port_map[ids["device"]] = {}
        diffsync.port_map[ids["device"]][ids["name"]] = new_intf.id
        if attrs.get("mac_addr"):
            diffsync.port_map[attrs["mac_addr"][:12]] = new_intf.id
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Interface object in Nautobot."""
        _port = OrmInterface.objects.get(id=self.uuid)
        self.diffsync.job.logger.info(f"Updating Port {_port.name} on {_port.device.name} with {attrs}")
        if "enabled" in attrs:
            _port.enabled = is_truthy(attrs["enabled"])
        if "mtu" in attrs:
            _port.mtu = attrs["mtu"]
        if "description" in attrs:
            _port.description = attrs["description"]
        if "mac_addr" in attrs:
            _port.mac_address = attrs["mac_addr"][:12] if attrs.get("mac_addr") else None
        if "type" in attrs:
            _port.type = attrs["type"]
        if "mode" in attrs:
            _port.mode = attrs["mode"]
        if attrs.get("status"):
            _port.status_id = self.diffsync.status_map[attrs["status"]]
        if "tags" in attrs:
            if attrs.get("tags"):
                nautobot.update_tags(tagged_obj=_port, new_tags=attrs["tags"])
            else:
                _port.tags.clear()
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_port)
        if "vlans" in attrs:
            if attrs.get("mode"):
                _mode = attrs["mode"]
            else:
                _mode = self.mode
            if attrs.get("device"):
                _device = attrs["device"]
            else:
                _device = self.device
            nautobot.apply_vlans_to_port(
                diffsync=self.diffsync, device_name=_device, mode=_mode, vlans=attrs["vlans"], port=_port
            )
        try:
            _port.validated_save()
            return super().update(attrs)
        except ValidationError as err:
            self.diffsync.job.logger.warning(
                f"Validation error for updating Port {_port.name} for {_port.device.name}: {err}"
            )
            return None

    def delete(self):
        """Delete Interface object from Nautobot."""
        if PLUGIN_CFG.get("device42_delete_on_sync"):
            super().delete()
            self.diffsync.job.logger.info(f"Interface {self.name} for {self.device} will be deleted.")
            _intf = OrmInterface.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["port"].append(_intf)  # pylint: disable=protected-access
        return self


class NautobotConnection(Connection):
    """Nautobot Connection model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):  # pylint: disable=inconsistent-return-statements
        """Create Cable object in Nautobot."""
        diffsync.job.logger.info(
            f"Creating Cable between {ids['src_device']}'s {ids['src_port']} port to {ids['dst_device']} {ids['dst_port']} port."
        )
        new_cable = None
        if attrs["src_type"] == "circuit" or attrs["dst_type"] == "circuit":
            new_cable = cls.get_circuit_connections(cls, diffsync=diffsync, ids=ids, attrs=attrs)
        elif attrs["src_type"] == "interface" and attrs["dst_type"] == "interface":
            new_cable = cls.get_device_connections(cls, diffsync=diffsync, ids=ids)
        if new_cable:
            new_cable.validated_save()
            if ids["src_device"] not in diffsync.cable_map:
                diffsync.cable_map[ids["src_device"]] = {}
            if ids["dst_device"] not in diffsync.cable_map:
                diffsync.cable_map[ids["dst_device"]] = {}
            diffsync.cable_map[ids["src_device"]][ids["src_port"]] = new_cable.id
            diffsync.cable_map[ids["dst_device"]][ids["dst_port"]] = new_cable.id
            return super().create(diffsync=diffsync, ids=ids, attrs=attrs)
        else:
            return None

    def get_circuit_connections(self, diffsync, ids, attrs) -> Optional[OrmCable]:
        """Method to create a Cable between a Circuit and a Device.

        Args:
            diffsync (obj): DiffSync job used for logging.
            ids (dict): Identifying attributes for the object.
            attrs (dict): Non-identifying attributes for the object.

        Returns:
            Optional[OrmCable]: If the Interfaces are found and a cable is created, returns Cable else None.
        """
        _intf, circuit = None, None
        if attrs["src_type"] == "interface":
            try:
                circuit = diffsync.circuit_map[ids["dst_device"]]
            except KeyError:
                if diffsync.job.debug:
                    diffsync.job.logger.warning(
                        f"Unable to find Circuit for {ids['src_device']}: {ids['src_port']} to connect to Circuit {ids['dst_device']}"
                    )
                return None
            try:
                _intf = diffsync.port_map[ids["src_port_mac"]]
            except KeyError:
                try:
                    _intf = diffsync.port_map[ids["src_device"]][ids["src_port"]]
                except KeyError:
                    if diffsync.job.debug:
                        diffsync.job.logger.warning(
                            f"Unable to find source port for {ids['src_device']}: {ids['src_port']} to connect to Circuit {ids['dst_device']}"
                        )
                    return None
        elif attrs["src_type"] == "patch panel":
            try:
                _intf = OrmFrontPort.objects.get(device__name=ids["src_device"], name=ids["src_port"])
                circuit = diffsync.circuit_map[ids["dst_device"]]
            except KeyError:
                if diffsync.job.debug:
                    diffsync.job.logger.warning(
                        f"Unable to find patch panel port for {ids['src_device']}: {ids['src_port']} to connect to Circuit {ids['dst_device']}"
                    )
                return None
        if attrs["dst_type"] == "interface":
            try:
                circuit = diffsync.circuit_map[ids["src_device"]]
            except KeyError:
                if diffsync.job.debug:
                    diffsync.job.logger.warning(
                        f"Unable to find Circuit for {ids['src_device']}: {ids['src_port']} to connect to Circuit {ids['dst_device']}"
                    )
                return None
            try:
                _intf = diffsync.port_map[ids["dst_port_mac"]]
            except KeyError:
                try:
                    _intf = diffsync.port_map[ids["dst_device"]][ids["dst_port"]]
                except KeyError:
                    if diffsync.job.debug:
                        diffsync.job.logger.warning(
                            f"Unable to find destination port for {ids['dst_device']}: {ids['dst_port']} to connect to Circuit {ids['src_device']}"
                        )
                    return None
        elif attrs["dst_type"] == "patch panel":
            try:
                circuit = diffsync.circuit_map[ids["src_device"]]
            except KeyError as err:
                if diffsync.job.debug:
                    diffsync.job.logger.warning(f"Unable to find Circuit {ids['dst_device']} {err}")
                return None
            try:
                _intf = OrmFrontPort.objects.get(device__name=ids["dst_device"], name=ids["dst_port"])
            except OrmFrontPort.DoesNotExist as err:
                if diffsync.job.debug:
                    diffsync.job.logger.warning(
                        f"Unable to find destination port for {ids['dst_device']}: {ids['dst_port']} to connect to Circuit {ids['src_device']} {err}"
                    )
                return None
        if circuit and _intf:
            _ct = {
                "circuit_id": circuit,
                "site": _intf.device.location,
            }
        else:
            if diffsync.job.debug:
                diffsync.job.logger.warning(f"Unable to find Circuit and Interface {ids}")
            return None
        if attrs["src_type"] == "circuit":
            _ct["term_side"] = "Z"
        if attrs["dst_type"] == "circuit":
            _ct["term_side"] = "A"
        try:
            circuit_term = OrmCT.objects.get(**_ct)
        except OrmCT.DoesNotExist:
            circuit_term = OrmCT(**_ct)
            circuit_term.port_speed = INTF_SPEED_MAP[_intf.type] if isinstance(_intf, OrmInterface) else None
            circuit_term.validated_save()
        if _intf and not _intf.cable and not circuit_term.cable:
            new_cable = OrmCable(
                termination_a_type=(
                    ContentType.objects.get(app_label="dcim", model="interface")
                    if attrs["src_type"] == "interface"
                    else ContentType.objects.get(app_label="dcim", model="frontport")
                ),
                termination_a_id=_intf,
                termination_b_type=ContentType.objects.get(app_label="circuits", model="circuittermination"),
                termination_b_id=circuit_term.id,
                status=OrmStatus.objects.get(name="Connected"),
                color=nautobot.get_random_color(),
            )
            return new_cable
        else:
            return None

    def get_device_connections(self, diffsync, ids) -> Optional[OrmCable]:
        """Method to create a Cable between two Devices.

        Args:
            diffsync (obj): DiffSync job used for logging.
            ids (dict): Identifying attributes for the object.

        Returns:
            Optional[OrmCable]: If the Interfaces are found and a cable is created, returns Cable else None.
        """
        _src_port, _dst_port = None, None
        try:
            _src_port = diffsync.port_map[ids["src_port_mac"]]
        except KeyError:
            try:
                _src_port = diffsync.port_map[ids["src_device"]][ids["src_port"]]
            except KeyError:
                if diffsync.job.debug:
                    diffsync.job.logger.warning(
                        f"Unable to find source port for {ids['src_device']}: {ids['src_port']} {ids['src_port_mac']}"
                    )
                return None
        try:
            _dst_port = diffsync.port_map[ids["dst_port_mac"]]
        except KeyError:
            try:
                _dst_port = diffsync.port_map[ids["dst_device"]][ids["dst_port"]]
            except KeyError:
                if diffsync.job.debug:
                    diffsync.job.logger.warning(
                        f"Unable to find destination port for {ids['dst_device']}: {ids['dst_port']} {ids['dst_port_mac']}"
                    )
                return None
        if _src_port and _dst_port:
            new_cable = OrmCable(
                termination_a_type=ContentType.objects.get(app_label="dcim", model="interface"),
                termination_a_id=_src_port,
                termination_b_type=ContentType.objects.get(app_label="dcim", model="interface"),
                termination_b_id=_dst_port,
                status_id=diffsync.status_map["connected"],
                color=nautobot.get_random_color(),
            )
            return new_cable
        else:
            return None

    def delete(self):
        """Delete Cable object from Nautobot."""
        if PLUGIN_CFG.get("device42_delete_on_sync"):
            super().delete()
            self.diffsync.job.logger.info(
                f"Deleting Cable between {self.src_device}'s {self.src_port} port to {self.dst_device} {self.dst_port} port."
            )
            _conn = OrmCable.objects.get(id=self.uuid)
            _conn.delete()
        return self
