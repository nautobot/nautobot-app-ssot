"""Nautobot DiffSync models for AristaCV SSoT."""

import logging
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from nautobot.core.settings_funcs import is_truthy
from nautobot.dcim.models import Device as OrmDevice
from nautobot.dcim.models import Interface as OrmInterface
from nautobot.dcim.models import Platform as OrmPlatform
from nautobot.extras.models import Relationship as OrmRelationship
from nautobot.extras.models import RelationshipAssociation as OrmRelationshipAssociation
from nautobot.extras.models import Status as OrmStatus
from nautobot.ipam.models import IPAddress as OrmIPAddress
from nautobot.ipam.models import Prefix as OrmPrefix
from nautobot.ipam.models import Namespace as OrmNamespace
from nautobot.ipam.models import IPAddressToInterface
import distutils

from nautobot_ssot.integrations.aristacv.constants import (
    ARISTA_PLATFORM,
    CLOUDVISION_PLATFORM,
    DEFAULT_DEVICE_ROLE_COLOR,
)
from nautobot_ssot.integrations.aristacv.diffsync.models.base import (
    Device,
    CustomField,
    IPAddress,
    IPAssignment,
    Namespace,
    Port,
    Prefix,
)
from nautobot_ssot.integrations.aristacv.types import CloudVisionAppConfig
from nautobot_ssot.integrations.aristacv.utils import nautobot

logger = logging.getLogger(__name__)

try:
    from nautobot_device_lifecycle_mgmt.models import SoftwareLCM  # noqa: F401 # pylint: disable=unused-import

    LIFECYCLE_MGMT = True
except ImportError:
    logger.info("Device Lifecycle app isn't installed so will revert to CustomField for OS version.")
    LIFECYCLE_MGMT = False
except RuntimeError:
    logger.warning(
        "nautobot-device-lifecycle-mgmt is installed but not enabled. Did you forget to add it to your settings.PLUGINS?"
    )
    LIFECYCLE_MGMT = False

MISSING_CUSTOM_FIELDS = []


class NautobotDevice(Device):
    """Nautobot Device Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create device object in Nautobot."""
        config: CloudVisionAppConfig = diffsync.job.app_config  # type: ignore
        site_code, role_code = nautobot.parse_hostname(ids["name"].lower(), config.hostname_patterns)
        site_map = config.site_mappings
        role_map = config.role_mappings

        if site_code and site_code in site_map:
            site = nautobot.verify_site(site_map[site_code])
        elif "CloudVision" in ids["name"]:
            if config.controller_site:
                site = nautobot.verify_site(config.controller_site)
            else:
                site = nautobot.verify_site("CloudVision")
        else:
            site = nautobot.verify_site(config.from_cloudvision_default_site)

        if role_code and role_code in role_map:
            role = nautobot.verify_device_role_object(
                role_map[role_code],
                config.from_cloudvision_default_device_role_color,
            )
        elif "CloudVision" in ids["name"]:
            role = nautobot.verify_device_role_object("Controller", DEFAULT_DEVICE_ROLE_COLOR)
        else:
            role = nautobot.verify_device_role_object(
                config.from_cloudvision_default_device_role,
                config.from_cloudvision_default_device_role_color,
            )

        if config.create_controller and "CloudVision" in ids["name"]:
            platform = OrmPlatform.objects.get(name=CLOUDVISION_PLATFORM)
        else:
            platform = OrmPlatform.objects.get(name=ARISTA_PLATFORM)

        device_type_object = nautobot.verify_device_type_object(attrs["device_model"])

        new_device = OrmDevice(
            status=OrmStatus.objects.get(name=attrs["status"]),
            device_type=device_type_object,
            role=role,
            platform=platform,
            location=site,
            name=ids["name"],
            serial=attrs["serial"] if attrs.get("serial") else "",
        )

        if config.apply_import_tag:
            import_tag = nautobot.verify_import_tag()
            new_device.tags.add(import_tag)
        try:
            new_device.validated_save()
            if LIFECYCLE_MGMT and attrs.get("version"):
                software_lcm = cls._add_software_lcm(platform=platform.name, version=attrs["version"])
                cls._assign_version_to_device(diffsync=diffsync, device=new_device, software_lcm=software_lcm)
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)
        except ValidationError as err:
            diffsync.job.logger.warning(f"Unable to create Device {ids['name']}. {err}")
            return None

    def update(self, attrs):
        """Update device object in Nautobot."""
        dev = OrmDevice.objects.get(id=self.uuid)
        if not dev.platform:
            if dev.name != "CloudVision":
                dev.platform = OrmPlatform.objects.get(name=ARISTA_PLATFORM)
            else:
                dev.platform = OrmPlatform.objects.get(name=CLOUDVISION_PLATFORM)
        if "device_model" in attrs:
            dev.device_type = nautobot.verify_device_type_object(attrs["device_model"])
        if "serial" in attrs:
            dev.serial = attrs["serial"]
        if "version" in attrs and LIFECYCLE_MGMT:
            software_lcm = self._add_software_lcm(platform=dev.platform.name, version=attrs["version"])
            self._assign_version_to_device(diffsync=self.diffsync, device=dev, software_lcm=software_lcm)
        try:
            dev.validated_save()
            return super().update(attrs)
        except ValidationError as err:
            self.diffsync.job.logger.warning(f"Unable to update Device {self.name}. {err}")
            return None

    def delete(self):
        """Delete device object in Nautobot."""
        config: CloudVisionAppConfig = self.diffsync.job.app_config  # type: ignore
        if config.delete_devices_on_sync:
            self.diffsync.job.logger.warning(f"Device {self.name} will be deleted per app settings.")
            device = OrmDevice.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["devices"].append(device)
            super().delete()
        return self

    @staticmethod
    def _add_software_lcm(platform: str, version: str):
        """Add OS Version as SoftwareLCM if Device Lifecycle App found."""
        _platform = OrmPlatform.objects.get(name=platform)
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
        software_relation = OrmRelationship.objects.get(label="Software on Device")
        relations = device.get_relationships()
        for _, relationships in relations.items():
            for relationship, queryset in relationships.items():
                if relationship == software_relation:
                    if diffsync.job.debug:
                        diffsync.job.logger.warning(
                            f"Deleting Software Version Relationships for {device.name} to assign a new version."
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
            status=OrmStatus.objects.get(name=attrs["status"]),
            type=attrs["port_type"],
        )
        try:
            new_port.validated_save()
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)
        except ValidationError as err:
            diffsync.job.logger.warning(err)
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
            _port.status = OrmStatus.objects.get(name=attrs["status"])
        if "port_type" in attrs:
            _port.type = attrs["port_type"]
        try:
            _port.validated_save()
            return super().update(attrs)
        except ValidationError as err:
            self.diffsync.job.logger.warning(f"Unable to update port {self.name} for {self.device} with {attrs}: {err}")
            return None

    def delete(self):
        """Delete Interface in Nautobot."""
        config: CloudVisionAppConfig = self.diffsync.job.app_config  # type: ignore
        if config.delete_devices_on_sync:
            super().delete()
            if self.diffsync.job.debug:
                self.diffsync.job.logger.warning(f"Interface {self.name} for {self.device} will be deleted.")
            _port = OrmInterface.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["interfaces"].append(_port)
        return self


class NautobotNamespace(Namespace):
    """Nautobot Prefix model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Prefix in Nautobot from NautobotPrefix objects."""
        if diffsync.job.debug:
            diffsync.job.logger.info(f"Creating Namespace {ids['name']}.")
        _ns = OrmNamespace(
            name=ids["name"],
        )
        _ns.validated_save()
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def delete(self):
        """Delete Namespace in Nautobot."""
        super().delete()
        _ns = OrmNamespace.objects.get(id=self.uuid)
        self.diffsync.objects_to_delete["namespaces"].append(_ns)
        return self


class NautobotPrefix(Prefix):
    """Nautobot Prefix model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Prefix in Nautobot from NautobotPrefix objects."""
        if diffsync.job.debug:
            diffsync.job.logger.info(f"Creating Prefix {ids['prefix']}.")
        _pf = OrmPrefix(
            prefix=ids["prefix"],
            namespace=OrmNamespace.objects.get(name=ids["namespace"]),
            status=OrmStatus.objects.get(name="Active"),
        )
        _pf.validated_save()
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def delete(self):
        """Delete Prefix in Nautobot."""
        super().delete()
        _pf = OrmPrefix.objects.get(id=self.uuid)
        self.diffsync.objects_to_delete["prefixes"].append(_pf)
        return self


class NautobotIPAddress(IPAddress):
    """Nautobot IPAddress model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create IPAddress in Nautobot."""
        new_ip = OrmIPAddress(
            address=ids["address"],
            parent=OrmPrefix.objects.get(
                prefix=ids["prefix"], namespace=OrmNamespace.objects.get(name=ids["namespace"])
            ),
            status=OrmStatus.objects.get(name="Active"),
        )
        new_ip.validated_save()
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def delete(self):
        """Delete IPAddress in Nautobot."""
        super().delete()
        ipaddr = OrmIPAddress.objects.get(id=self.uuid)
        self.diffsync.objects_to_delete["ipaddresses"].append(ipaddr)
        return self


class NautobotIPAssignment(IPAssignment):
    """Nautobot IPAssignment model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create IPAddressToInterface in Nautobot."""
        try:
            ipaddr = OrmIPAddress.objects.get(
                address=ids["address"], parent__namespace=OrmNamespace.objects.get(name=ids["namespace"])
            )
            intf = OrmInterface.objects.get(name=ids["interface"], device__name=ids["device"])
            new_map = IPAddressToInterface(ip_address=ipaddr, interface=intf)
            if "loopback" in ids["interface"]:
                ipaddr.role = "loopback"
                ipaddr.validated_save()
            new_map.validated_save()
            if attrs.get("primary"):
                if ":" in ids["address"]:
                    intf.device.primary_ip6 = ipaddr
                else:
                    intf.device.primary_ip4 = ipaddr
                intf.device.validated_save()
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)
        except OrmInterface.DoesNotExist as err:
            diffsync.job.logger.warning(f"Unable to find Interface {ids['interface']} for {ids['device']}. {err}")

    def update(self, attrs):
        """Update IPAddressToInterface in Nautobot."""
        map = IPAddressToInterface.objects.get(id=self.uuid)
        if attrs.get("primary"):
            if ":" in map.ip_address.address:
                map.interface.device.primary_ip6 = map.ip_address
            else:
                map.interface.device.primary_ip4 = map.ip_address
            map.interface.device.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete IPAddressToInterface in Nautobot."""
        super().delete()
        mapping = IPAddressToInterface.objects.get(id=self.uuid)
        mapping.delete()
        return self


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
                diffsync.job.logger.warning(
                    f"Custom field {ids['name']} is not defined. You can create the custom field in the Admin UI."
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
