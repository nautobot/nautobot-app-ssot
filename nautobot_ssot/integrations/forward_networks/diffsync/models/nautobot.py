"""Nautobot DiffSync models for Forward Networks integration."""

import ipaddress

from nautobot.dcim.models import (
    Device as NautobotDeviceModel,
)
from nautobot.dcim.models import (
    DeviceRole,
    DeviceType,
    LocationType,
)
from nautobot.dcim.models import (
    Interface as NautobotInterfaceModel,
)
from nautobot.dcim.models import (
    Location as NautobotLocationModel,
)
from nautobot.ipam.models import (
    VLAN as NautobotVLANModel,
)
from nautobot.ipam.models import (
    IPAddress as NautobotIPAddressModel,
)
from nautobot.ipam.models import (
    Namespace,
    VLANGroup,
)
from nautobot.ipam.models import (
    Prefix as NautobotPrefixModel,
)

from nautobot_ssot.integrations.forward_networks.diffsync.models.base import (
    VLAN,
    Device,
    Interface,
    IPAddress,
    Location,
    Network,
    Prefix,
)
from nautobot_ssot.integrations.forward_networks.utils import (
    create_forward_networks_tag,
    get_or_create_manufacturer,
    get_or_create_platform,
    get_or_create_tag,
    normalize_device_name,
    normalize_interface_name,
    parse_forward_networks_device_role,
    sanitize_custom_fields,
    validate_mac_address,
)


class NautobotNetwork(Network):
    """Nautobot implementation of Network model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Location in Nautobot to represent the network."""
        try:
            location_type = LocationType.objects.get(name="Site")
        except LocationType.DoesNotExist:
            location_type = LocationType.objects.create(name="Site", description="Site location type")

        location = NautobotLocationModel(
            name=ids["name"],
            location_type=location_type,
            status=diffsync.status_active,
            description=attrs.get("description", ""),
        )

        # Set custom fields
        if attrs.get("custom_fields"):
            custom_fields = sanitize_custom_fields(attrs["custom_fields"])
            for key, value in custom_fields.items():
                setattr(location.cf, key, value)

        location.validated_save()

        # Add tags
        if attrs.get("tags"):
            for tag_name in attrs["tags"]:
                tag = get_or_create_tag(tag_name)
                location.tags.add(tag)

        # Add sync tag
        sync_tag = create_forward_networks_tag()
        location.tags.add(sync_tag)

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Location in Nautobot."""
        try:
            location = NautobotLocationModel.objects.get(name=self.name)

            if "description" in attrs:
                location.description = attrs["description"]

            # Update custom fields
            if attrs.get("custom_fields"):
                custom_fields = sanitize_custom_fields(attrs["custom_fields"])
                for key, value in custom_fields.items():
                    setattr(location.cf, key, value)

            location.validated_save()

            # Update tags
            if "tags" in attrs:
                location.tags.clear()
                for tag_name in attrs["tags"]:
                    tag = get_or_create_tag(tag_name)
                    location.tags.add(tag)

                # Re-add sync tag
                sync_tag = create_forward_networks_tag()
                location.tags.add(sync_tag)

        except NautobotLocationModel.DoesNotExist:
            self.diffsync.job.logger.warning(f"Location {self.name} not found for update")

        return super().update(attrs)

    def delete(self):
        """Delete Location from Nautobot."""
        try:
            location = NautobotLocationModel.objects.get(name=self.name)
            location.delete()
        except NautobotLocationModel.DoesNotExist:
            pass

        return super().delete()


class NautobotLocation(Location):
    """Nautobot implementation of Location model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Location in Nautobot."""
        try:
            location_type = LocationType.objects.get(name=attrs.get("location_type", "Site"))
        except LocationType.DoesNotExist:
            location_type = LocationType.objects.create(
                name=attrs.get("location_type", "Site"),
                description=f"{attrs.get('location_type', 'Site')} location type",
            )

        # Try to find parent location (network)
        parent_location = None
        try:
            parent_location = NautobotLocationModel.objects.get(name=ids["network"])
        except NautobotLocationModel.DoesNotExist:
            pass

        location = NautobotLocationModel(
            name=ids["name"],
            location_type=location_type,
            parent=parent_location,
            status=diffsync.status_active,
            description=attrs.get("description", ""),
            latitude=attrs.get("latitude"),
            longitude=attrs.get("longitude"),
        )

        # Set custom fields
        if attrs.get("custom_fields"):
            custom_fields = sanitize_custom_fields(attrs["custom_fields"])
            for key, value in custom_fields.items():
                setattr(location.cf, key, value)

        location.validated_save()

        # Add tags
        if attrs.get("tags"):
            for tag_name in attrs["tags"]:
                tag = get_or_create_tag(tag_name)
                location.tags.add(tag)

        # Add sync tag
        sync_tag = create_forward_networks_tag()
        location.tags.add(sync_tag)

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Location in Nautobot."""
        try:
            location = NautobotLocationModel.objects.get(name=self.name)

            if "description" in attrs:
                location.description = attrs["description"]
            if "latitude" in attrs:
                location.latitude = attrs["latitude"]
            if "longitude" in attrs:
                location.longitude = attrs["longitude"]

            # Update custom fields
            if attrs.get("custom_fields"):
                custom_fields = sanitize_custom_fields(attrs["custom_fields"])
                for key, value in custom_fields.items():
                    setattr(location.cf, key, value)

            location.validated_save()

            # Update tags
            if "tags" in attrs:
                location.tags.clear()
                for tag_name in attrs["tags"]:
                    tag = get_or_create_tag(tag_name)
                    location.tags.add(tag)

                # Re-add sync tag
                sync_tag = create_forward_networks_tag()
                location.tags.add(sync_tag)

        except NautobotLocationModel.DoesNotExist:
            self.diffsync.job.logger.warning(f"Location {self.name} not found for update")

        return super().update(attrs)

    def delete(self):
        """Delete Location from Nautobot."""
        try:
            location = NautobotLocationModel.objects.get(name=self.name)
            location.delete()
        except NautobotLocationModel.DoesNotExist:
            pass

        return super().delete()


class NautobotDevice(Device):
    """Nautobot implementation of Device model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Device in Nautobot."""
        # Get or create manufacturer
        manufacturer = get_or_create_manufacturer(attrs.get("manufacturer", "Unknown"))

        # Get or create device type
        device_type, created = DeviceType.objects.get_or_create(
            model=attrs.get("model", "Unknown"),
            manufacturer=manufacturer,
            defaults={
                "description": "Device type imported from Forward Networks",
                "u_height": 1,
            },
        )

        # Get or create platform
        platform = None
        if attrs.get("platform"):
            platform = get_or_create_platform(attrs["platform"])

        # Get or create device role
        role_name = parse_forward_networks_device_role(attrs.get("device_type", ""), ids["name"])

        device_role, created = DeviceRole.objects.get_or_create(
            name=role_name, defaults={"description": f"Device role for {role_name} devices", "color": "9e9e9e"}
        )

        # Find location
        location = None
        if attrs.get("location"):
            try:
                location = NautobotLocationModel.objects.get(name=attrs["location"])
            except NautobotLocationModel.DoesNotExist:
                pass

        device_name = normalize_device_name(ids["name"])

        device = NautobotDeviceModel(
            name=device_name,
            device_type=device_type,
            device_role=device_role,
            platform=platform,
            location=location,
            status=diffsync.status_active,
            serial=attrs.get("serial_number", ""),
        )

        # Set custom fields
        if attrs.get("custom_fields"):
            custom_fields = sanitize_custom_fields(attrs["custom_fields"])
            for key, value in custom_fields.items():
                setattr(device.cf, key, value)

        device.validated_save()

        # Add tags
        if attrs.get("tags"):
            for tag_name in attrs["tags"]:
                tag = get_or_create_tag(tag_name)
                device.tags.add(tag)

        # Add sync tag
        sync_tag = create_forward_networks_tag()
        device.tags.add(sync_tag)

        # Set primary IP if provided
        if attrs.get("primary_ip"):
            try:
                ip_str = attrs["primary_ip"].split("/")[0]  # Remove CIDR if present
                ip_addr = ipaddress.ip_address(ip_str)

                # Try to find existing IP address
                try:
                    primary_ip = NautobotIPAddressModel.objects.get(
                        address=f"{ip_addr}/{32 if ip_addr.version == 4 else 128}"
                    )
                except NautobotIPAddressModel.DoesNotExist:
                    # Create the IP address
                    namespace = Namespace.objects.get_or_create(name="Global")[0]
                    primary_ip = NautobotIPAddressModel.objects.create(
                        address=f"{ip_addr}/{32 if ip_addr.version == 4 else 128}",
                        status=diffsync.status_active,
                        namespace=namespace,
                    )

                if ip_addr.version == 4:
                    device.primary_ip4 = primary_ip
                else:
                    device.primary_ip6 = primary_ip

                device.validated_save()

            except (ValueError, ipaddress.AddressValueError):
                diffsync.job.logger.warning(f"Invalid primary IP {attrs['primary_ip']} for device {device_name}")

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Device in Nautobot."""
        try:
            device = NautobotDeviceModel.objects.get(name=normalize_device_name(self.name))

            # Update device type if manufacturer or model changed
            if "manufacturer" in attrs or "model" in attrs:
                manufacturer = get_or_create_manufacturer(
                    attrs.get("manufacturer", device.device_type.manufacturer.name)
                )
                device_type, created = DeviceType.objects.get_or_create(
                    model=attrs.get("model", device.device_type.model),
                    manufacturer=manufacturer,
                    defaults={
                        "description": "Device type imported from Forward Networks",
                        "u_height": 1,
                    },
                )
                device.device_type = device_type

            # Update platform
            if "platform" in attrs and attrs["platform"]:
                platform = get_or_create_platform(attrs["platform"])
                device.platform = platform

            # Update serial number
            if "serial_number" in attrs:
                device.serial = attrs["serial_number"] or ""

            # Update location
            if "location" in attrs:
                try:
                    location = NautobotLocationModel.objects.get(name=attrs["location"])
                    device.location = location
                except NautobotLocationModel.DoesNotExist:
                    pass

            # Update custom fields
            if attrs.get("custom_fields"):
                custom_fields = sanitize_custom_fields(attrs["custom_fields"])
                for key, value in custom_fields.items():
                    setattr(device.cf, key, value)

            device.validated_save()

            # Update tags
            if "tags" in attrs:
                device.tags.clear()
                for tag_name in attrs["tags"]:
                    tag = get_or_create_tag(tag_name)
                    device.tags.add(tag)

                # Re-add sync tag
                sync_tag = create_forward_networks_tag()
                device.tags.add(sync_tag)

        except NautobotDeviceModel.DoesNotExist:
            self.diffsync.job.logger.warning(f"Device {self.name} not found for update")

        return super().update(attrs)

    def delete(self):
        """Delete Device from Nautobot."""
        try:
            device = NautobotDeviceModel.objects.get(name=normalize_device_name(self.name))
            device.delete()
        except NautobotDeviceModel.DoesNotExist:
            pass

        return super().delete()


class NautobotInterface(Interface):
    """Nautobot implementation of Interface model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Interface in Nautobot."""
        try:
            device = NautobotDeviceModel.objects.get(name=normalize_device_name(ids["device"]))
        except NautobotDeviceModel.DoesNotExist:
            diffsync.job.logger.warning(f"Device {ids['device']} not found for interface {ids['name']}")
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        interface_name = normalize_interface_name(ids["name"])

        interface = NautobotInterfaceModel(
            name=interface_name,
            device=device,
            description=attrs.get("description", ""),
            type=attrs.get("interface_type", "other"),
            enabled=attrs.get("enabled", True),
            mtu=attrs.get("mtu"),
            speed=attrs.get("speed"),
            duplex=attrs.get("duplex"),
            status=diffsync.status_active,
        )

        # Set MAC address if valid
        if attrs.get("mac_address"):
            mac = validate_mac_address(attrs["mac_address"])
            if mac:
                interface.mac_address = mac

        # Set custom fields
        if attrs.get("custom_fields"):
            custom_fields = sanitize_custom_fields(attrs["custom_fields"])
            for key, value in custom_fields.items():
                setattr(interface.cf, key, value)

        interface.validated_save()

        # Add tags
        if attrs.get("tags"):
            for tag_name in attrs["tags"]:
                tag = get_or_create_tag(tag_name)
                interface.tags.add(tag)

        # Add sync tag
        sync_tag = create_forward_networks_tag()
        interface.tags.add(sync_tag)

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Interface in Nautobot."""
        try:
            device = NautobotDeviceModel.objects.get(name=normalize_device_name(self.device))
            interface = NautobotInterfaceModel.objects.get(name=normalize_interface_name(self.name), device=device)

            if "description" in attrs:
                interface.description = attrs["description"] or ""
            if "interface_type" in attrs:
                interface.type = attrs["interface_type"]
            if "enabled" in attrs:
                interface.enabled = attrs["enabled"]
            if "mtu" in attrs:
                interface.mtu = attrs["mtu"]
            if "speed" in attrs:
                interface.speed = attrs["speed"]
            if "duplex" in attrs:
                interface.duplex = attrs["duplex"]

            # Update MAC address
            if "mac_address" in attrs:
                mac = validate_mac_address(attrs["mac_address"])
                interface.mac_address = mac

            # Update custom fields
            if attrs.get("custom_fields"):
                custom_fields = sanitize_custom_fields(attrs["custom_fields"])
                for key, value in custom_fields.items():
                    setattr(interface.cf, key, value)

            interface.validated_save()

            # Update tags
            if "tags" in attrs:
                interface.tags.clear()
                for tag_name in attrs["tags"]:
                    tag = get_or_create_tag(tag_name)
                    interface.tags.add(tag)

                # Re-add sync tag
                sync_tag = create_forward_networks_tag()
                interface.tags.add(sync_tag)

        except (NautobotDevice.DoesNotExist, NautobotInterface.DoesNotExist):
            self.diffsync.job.logger.warning(f"Interface {self.name} on device {self.device} not found for update")

        return super().update(attrs)

    def delete(self):
        """Delete Interface from Nautobot."""
        try:
            device = NautobotDeviceModel.objects.get(name=normalize_device_name(self.device))
            interface = NautobotInterfaceModel.objects.get(name=normalize_interface_name(self.name), device=device)
            interface.delete()
        except (NautobotDevice.DoesNotExist, NautobotInterface.DoesNotExist):
            pass

        return super().delete()


class NautobotIPAddress(IPAddress):
    """Nautobot implementation of IPAddress model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create IP Address in Nautobot."""
        namespace = Namespace.objects.get_or_create(name="Global")[0]

        ip_address = NautobotIPAddressModel(
            address=ids["address"],
            status=diffsync.status_active,
            namespace=namespace,
            description=attrs.get("description", ""),
        )

        # Set custom fields
        if attrs.get("custom_fields"):
            custom_fields = sanitize_custom_fields(attrs["custom_fields"])
            for key, value in custom_fields.items():
                setattr(ip_address.cf, key, value)

        ip_address.validated_save()

        # Add tags
        if attrs.get("tags"):
            for tag_name in attrs["tags"]:
                tag = get_or_create_tag(tag_name)
                ip_address.tags.add(tag)

        # Add sync tag
        sync_tag = create_forward_networks_tag()
        ip_address.tags.add(sync_tag)

        # Assign to interface if specified
        if attrs.get("device") and attrs.get("interface"):
            try:
                device = NautobotDeviceModel.objects.get(name=normalize_device_name(attrs["device"]))
                interface = NautobotInterfaceModel.objects.get(
                    name=normalize_interface_name(attrs["interface"]), device=device
                )
                ip_address.assigned_object = interface
                ip_address.validated_save()
            except (NautobotDevice.DoesNotExist, NautobotInterface.DoesNotExist):
                pass

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update IP Address in Nautobot."""
        try:
            ip_address = NautobotIPAddressModel.objects.get(address=self.address)

            if "description" in attrs:
                ip_address.description = attrs["description"] or ""

            # Update custom fields
            if attrs.get("custom_fields"):
                custom_fields = sanitize_custom_fields(attrs["custom_fields"])
                for key, value in custom_fields.items():
                    setattr(ip_address.cf, key, value)

            ip_address.validated_save()

            # Update tags
            if "tags" in attrs:
                ip_address.tags.clear()
                for tag_name in attrs["tags"]:
                    tag = get_or_create_tag(tag_name)
                    ip_address.tags.add(tag)

                # Re-add sync tag
                sync_tag = create_forward_networks_tag()
                ip_address.tags.add(sync_tag)

        except NautobotIPAddressModel.DoesNotExist:
            self.diffsync.job.logger.warning(f"IP Address {self.address} not found for update")

        return super().update(attrs)

    def delete(self):
        """Delete IP Address from Nautobot."""
        try:
            ip_address = NautobotIPAddressModel.objects.get(address=self.address)
            ip_address.delete()
        except NautobotIPAddressModel.DoesNotExist:
            pass

        return super().delete()


class NautobotPrefix(Prefix):
    """Nautobot implementation of Prefix model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Prefix in Nautobot."""
        namespace = Namespace.objects.get_or_create(name="Global")[0]

        prefix = NautobotPrefixModel(
            prefix=ids["prefix"],
            status=diffsync.status_active,
            namespace=namespace,
            description=attrs.get("description", ""),
            type=attrs.get("prefix_type", "network"),
        )

        # Set custom fields
        if attrs.get("custom_fields"):
            custom_fields = sanitize_custom_fields(attrs["custom_fields"])
            for key, value in custom_fields.items():
                setattr(prefix.cf, key, value)

        prefix.validated_save()

        # Add tags
        if attrs.get("tags"):
            for tag_name in attrs["tags"]:
                tag = get_or_create_tag(tag_name)
                prefix.tags.add(tag)

        # Add sync tag
        sync_tag = create_forward_networks_tag()
        prefix.tags.add(sync_tag)

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Prefix in Nautobot."""
        try:
            prefix = NautobotPrefixModel.objects.get(prefix=self.prefix)

            if "description" in attrs:
                prefix.description = attrs["description"] or ""
            if "prefix_type" in attrs:
                prefix.type = attrs["prefix_type"]

            # Update custom fields
            if attrs.get("custom_fields"):
                custom_fields = sanitize_custom_fields(attrs["custom_fields"])
                for key, value in custom_fields.items():
                    setattr(prefix.cf, key, value)

            prefix.validated_save()

            # Update tags
            if "tags" in attrs:
                prefix.tags.clear()
                for tag_name in attrs["tags"]:
                    tag = get_or_create_tag(tag_name)
                    prefix.tags.add(tag)

                # Re-add sync tag
                sync_tag = create_forward_networks_tag()
                prefix.tags.add(sync_tag)

        except NautobotPrefixModel.DoesNotExist:
            self.diffsync.job.logger.warning(f"Prefix {self.prefix} not found for update")

        return super().update(attrs)

    def delete(self):
        """Delete Prefix from Nautobot."""
        try:
            prefix = NautobotPrefixModel.objects.get(prefix=self.prefix)
            prefix.delete()
        except NautobotPrefixModel.DoesNotExist:
            pass

        return super().delete()


class NautobotVLAN(VLAN):
    """Nautobot implementation of VLAN model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create VLAN in Nautobot."""
        # Get or create VLAN group for Forward Networks
        vlan_group, created = VLANGroup.objects.get_or_create(
            name="Forward Networks", defaults={"description": "VLANs imported from Forward Networks"}
        )

        vlan = NautobotVLANModel(
            vid=ids["vid"],
            name=attrs.get("name", f"VLAN-{ids['vid']}"),
            vlan_group=vlan_group,
            status=diffsync.status_active,
            description=attrs.get("description", ""),
        )

        # Set custom fields
        if attrs.get("custom_fields"):
            custom_fields = sanitize_custom_fields(attrs["custom_fields"])
            for key, value in custom_fields.items():
                setattr(vlan.cf, key, value)

        vlan.validated_save()

        # Add tags
        if attrs.get("tags"):
            for tag_name in attrs["tags"]:
                tag = get_or_create_tag(tag_name)
                vlan.tags.add(tag)

        # Add sync tag
        sync_tag = create_forward_networks_tag()
        vlan.tags.add(sync_tag)

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update VLAN in Nautobot."""
        try:
            vlan = NautobotVLANModel.objects.get(vid=self.vid, vlan_group__name="Forward Networks")

            if "name" in attrs:
                vlan.name = attrs["name"] or f"VLAN-{self.vid}"
            if "description" in attrs:
                vlan.description = attrs["description"] or ""

            # Update custom fields
            if attrs.get("custom_fields"):
                custom_fields = sanitize_custom_fields(attrs["custom_fields"])
                for key, value in custom_fields.items():
                    setattr(vlan.cf, key, value)

            vlan.validated_save()

            # Update tags
            if "tags" in attrs:
                vlan.tags.clear()
                for tag_name in attrs["tags"]:
                    tag = get_or_create_tag(tag_name)
                    vlan.tags.add(tag)

                # Re-add sync tag
                sync_tag = create_forward_networks_tag()
                vlan.tags.add(sync_tag)

        except NautobotVLANModel.DoesNotExist:
            self.diffsync.job.logger.warning(f"VLAN {self.vid} not found for update")

        return super().update(attrs)

    def delete(self):
        """Delete VLAN from Nautobot."""
        try:
            vlan = NautobotVLANModel.objects.get(vid=self.vid, vlan_group__name="Forward Networks")
            vlan.delete()
        except NautobotVLANModel.DoesNotExist:
            pass

        return super().delete()
