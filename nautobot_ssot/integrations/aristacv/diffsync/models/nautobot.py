"""Nautobot DiffSync models for AristaCV SSoT."""
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.conf import settings
from nautobot.core.settings_funcs import is_truthy
from nautobot.dcim.models import Device as OrmDevice
from nautobot.dcim.models import Interface as OrmInterface
from nautobot.dcim.models import Platform as OrmPlatform
from nautobot.extras.models import Relationship as OrmRelationship
from nautobot.extras.models import RelationshipAssociation as OrmRelationshipAssociation
from nautobot.extras.models import Status as OrmStatus
from nautobot.ipam.models import IPAddress as OrmIPAddress
from nautobot_ssot_aristacv.constant import ARISTA_PLATFORM, CLOUDVISION_PLATFORM
from nautobot_ssot_aristacv.diffsync.models.base import Device, CustomField, IPAddress, Port
from nautobot_ssot_aristacv.utils import nautobot
import distutils

try:
    from nautobot_device_lifecycle_mgmt.models import SoftwareLCM

    LIFECYCLE_MGMT = True
except ImportError:
    print("Device Lifecycle plugin isn't installed so will revert to CustomField for OS version.")
    LIFECYCLE_MGMT = False


DEFAULT_SITE = "cloudvision_imported"
DEFAULT_DEVICE_ROLE = "network"
DEFAULT_DEVICE_ROLE_COLOR = "ff0000"
DEFAULT_DEVICE_STATUS = "cloudvision_imported"
DEFAULT_DEVICE_STATUS_COLOR = "ff0000"
DEFAULT_DELETE_DEVICES_ON_SYNC = False
APPLY_IMPORT_TAG = False
MISSING_CUSTOM_FIELDS = []


class NautobotDevice(Device):
    """Nautobot Device Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create device object in Nautobot."""
        PLUGIN_SETTINGS = settings.PLUGINS_CONFIG["nautobot_ssot_aristacv"]
        site_code, role_code = nautobot.parse_hostname(ids["name"].lower())
        site_map = PLUGIN_SETTINGS.get("site_mappings")
        role_map = PLUGIN_SETTINGS.get("role_mappings")

        if site_code and site_code in site_map:
            site = nautobot.verify_site(site_map[site_code])
        elif "CloudVision" in ids["name"]:
            if PLUGIN_SETTINGS.get("controller_site"):
                site = nautobot.verify_site(PLUGIN_SETTINGS["controller_site"])
            else:
                site = nautobot.verify_site("CloudVision")
        else:
            site = nautobot.verify_site(PLUGIN_SETTINGS.get("from_cloudvision_default_site", DEFAULT_SITE))

        if role_code and role_code in role_map:
            role = nautobot.verify_device_role_object(
                role_map[role_code],
                PLUGIN_SETTINGS.get("from_cloudvision_default_device_role_color", DEFAULT_DEVICE_ROLE_COLOR),
            )
        elif "CloudVision" in ids["name"]:
            role = nautobot.verify_device_role_object("Controller", DEFAULT_DEVICE_ROLE_COLOR)
        else:
            role = nautobot.verify_device_role_object(
                PLUGIN_SETTINGS.get("from_cloudvision_default_device_role", DEFAULT_DEVICE_ROLE),
                PLUGIN_SETTINGS.get("from_cloudvision_default_device_role_color", DEFAULT_DEVICE_ROLE_COLOR),
            )

        if PLUGIN_SETTINGS.get("create_controller") and "CloudVision" in ids["name"]:
            platform = OrmPlatform.objects.get(slug=CLOUDVISION_PLATFORM)
        else:
            platform = OrmPlatform.objects.get(slug=ARISTA_PLATFORM)

        device_type_object = nautobot.verify_device_type_object(attrs["device_model"])

        new_device = OrmDevice(
            status=OrmStatus.objects.get(slug=attrs["status"]),
            device_type=device_type_object,
            device_role=role,
            platform=platform,
            site=site,
            name=ids["name"],
            serial=attrs["serial"] if attrs.get("serial") else "",
        )
        if PLUGIN_SETTINGS.get("apply_import_tag", APPLY_IMPORT_TAG):
            import_tag = nautobot.verify_import_tag()
            new_device.tags.add(import_tag)
        try:
            new_device.validated_save()
            if LIFECYCLE_MGMT and attrs.get("version"):
                software_lcm = cls._add_software_lcm(platform=platform.slug, version=attrs["version"])
                cls._assign_version_to_device(diffsync=diffsync, device=new_device, software_lcm=software_lcm)
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)
        except ValidationError as err:
            diffsync.job.log_warning(message=f"Unable to create Device {ids['name']}. {err}")
            return None

    def update(self, attrs):
        """Update device object in Nautobot."""
        dev = OrmDevice.objects.get(id=self.uuid)
        if not dev.platform:
            if dev.name != "CloudVision":
                dev.platform = OrmPlatform.objects.get(slug="arista_eos")
            else:
                dev.platform = OrmPlatform.objects.get(slug="arista_eos_cloudvision")
        if "device_model" in attrs:
            dev.device_type = nautobot.verify_device_type_object(attrs["device_model"])
        if "serial" in attrs:
            dev.serial = attrs["serial"]
        if "version" in attrs and LIFECYCLE_MGMT:
            software_lcm = self._add_software_lcm(platform=dev.platform.slug, version=attrs["version"])
            self._assign_version_to_device(diffsync=self.diffsync, device=dev, software_lcm=software_lcm)
        try:
            dev.validated_save()
            return super().update(attrs)
        except ValidationError as err:
            self.diffsync.job.log_warning(message=f"Unable to update Device {self.name}. {err}")
            return None

    def delete(self):
        """Delete device object in Nautobot."""
        if settings.PLUGINS_CONFIG["nautobot_ssot_aristacv"].get(
            "delete_devices_on_sync", DEFAULT_DELETE_DEVICES_ON_SYNC
        ):
            self.diffsync.job.log_warning(message=f"Device {self.name} will be deleted per plugin settings.")
            device = OrmDevice.objects.get(id=self.uuid)
            device.delete()
            super().delete()
        return self

    @staticmethod
    def _add_software_lcm(platform: str, version: str):
        """Add OS Version as SoftwareLCM if Device Lifecycle Plugin found."""
        _platform = OrmPlatform.objects.get(slug=platform)
        try:
            os_ver = SoftwareLCM.objects.get(device_platform=_platform, version=version)
        except SoftwareLCM.DoesNotExist:
            os_ver = SoftwareLCM(
                device_platform=_platform,
                version=version,
            )
            os_ver.validated_save()
        return os_ver

    @staticmethod
    def _assign_version_to_device(diffsync, device, software_lcm):
        """Add Relationship between Device and SoftwareLCM."""
        software_relation = OrmRelationship.objects.get(name="Software on Device")
        relations = device.get_relationships()
        for _, relationships in relations.items():
            for relationship, queryset in relationships.items():
                if relationship == software_relation:
                    if diffsync.job.kwargs.get("debug"):
                        diffsync.job.log_warning(
                            message=f"Deleting Software Version Relationships for {device.name} to assign a new version."
                        )
                    queryset.delete()

        new_assoc = OrmRelationshipAssociation(
            relationship=software_relation,
            source_type=ContentType.objects.get_for_model(SoftwareLCM),
            source=software_lcm,
            destination_type=ContentType.objects.get_for_model(OrmDevice),
            destination=device,
        )
        new_assoc.validated_save()


class NautobotPort(Port):
    """Nautobot Port model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Interface in Nautobot."""
        device = OrmDevice.objects.get(name=ids["device"])
        new_port = OrmInterface(
            name=ids["name"],
            device=device,
            description=attrs["description"],
            enabled=is_truthy(attrs["enabled"]),
            mac_address=attrs["mac_addr"],
            mtu=attrs["mtu"],
            mode=attrs["mode"],
            status=OrmStatus.objects.get(slug=attrs["status"]),
            type=attrs["port_type"],
        )
        try:
            new_port.validated_save()
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)
        except ValidationError as err:
            diffsync.job.log_warning(message=err)
            return None

    def update(self, attrs):
        """Update Interface in Nautobot."""
        _port = OrmInterface.objects.get(id=self.uuid)
        if "description" in attrs:
            description = ""
            if attrs.get("description"):
                description = attrs["description"]
            _port.description = description
        if "mac_addr" in attrs:
            _port.mac_address = attrs["mac_addr"]
        if "mode" in attrs:
            _port.mode = attrs["mode"]
        if "enabled" in attrs:
            _port.enabled = is_truthy(attrs["enabled"])
        if "mtu" in attrs:
            _port.mtu = attrs["mtu"]
        if "status" in attrs:
            _port.status = OrmStatus.objects.get(slug=attrs["status"])
        if "port_type" in attrs:
            _port.type = attrs["port_type"]
        try:
            _port.validated_save()
            return super().update(attrs)
        except ValidationError as err:
            self.diffsync.job.log_warning(
                message=f"Unable to update port {self.name} for {self.device} with {attrs}: {err}"
            )
            return None

    def delete(self):
        """Delete Interface in Nautobot."""
        if settings.PLUGINS_CONFIG["nautobot_ssot_aristacv"].get("delete_devices_on_sync"):
            super().delete()
            if self.diffsync.job.kwargs.get("debug"):
                self.diffsync.job.log_warning(message=f"Interface {self.name} for {self.device} will be deleted.")
            _port = OrmInterface.objects.get(id=self.uuid)
            _port.delete()
        return self


class NautobotIPAddress(IPAddress):
    """Nautobot IPAddress model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create IPAddress in Nautobot."""
        dev = OrmDevice.objects.get(name=ids["device"])
        new_ip = OrmIPAddress(
            address=ids["address"],
            status=OrmStatus.objects.get(name="Active"),
        )
        if "loopback" in ids["interface"]:
            new_ip.role = "loopback"
        new_ip.validated_save()
        try:
            intf = OrmInterface.objects.get(device=dev, name=ids["interface"])
            new_ip.assigned_object_type = ContentType.objects.get(app_label="dcim", model="interface")
            new_ip.assigned_object = intf
            new_ip.validated_save()
            if "Management" in ids["interface"]:
                if ":" in ids["address"]:
                    dev.primary_ip6 = new_ip
                else:
                    dev.primary_ip4 = new_ip
                dev.validated_save()
        except OrmInterface.DoesNotExist as err:
            diffsync.job.log_warning(message=f"Unable to find Interface {ids['interface']} for {ids['device']}. {err}")
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)


class NautobotCustomField(CustomField):
    """Nautobot CustomField model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Custom Field in Nautobot."""
        try:
            attrs["value"] = bool(distutils.util.strtobool(attrs["value"]))
        except ValueError:
            # value isn't convertable to bool so continue
            pass
        device = OrmDevice.objects.get(name=ids["device_name"])
        try:
            device.custom_field_data.update({ids["name"]: attrs["value"]})
            device.validated_save()
        except ValidationError:
            if ids["name"] not in MISSING_CUSTOM_FIELDS:
                diffsync.job.log_warning(
                    message=f"Custom field {ids['name']} is not defined. You can create the custom field in the Admin UI."
                )
            MISSING_CUSTOM_FIELDS.append(ids["name"])

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Custom Field in Nautobot."""
        try:
            attrs["value"] = bool(distutils.util.strtobool(attrs["value"]))
        except ValueError:
            # value isn't convertable to bool so continue
            pass
        device = OrmDevice.objects.get(name=self.device_name)
        device.custom_field_data.update({self.name: attrs["value"]})
        device.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Custom Field in Nautobot."""
        try:
            device = OrmDevice.objects.get(name=self.device_name)
            device.custom_field_data.update({self.name: None})
            device.validated_save()
            super().delete()
            return self
        except OrmDevice.DoesNotExist:
            # Do not need to delete customfield if the device does not exist.
            return self
