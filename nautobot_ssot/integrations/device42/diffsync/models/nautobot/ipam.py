"""DiffSyncModel IPAM subclasses for Nautobot Device42 data sync."""

import re
from django.forms import ValidationError
from nautobot.dcim.models import Interface as OrmInterface
from nautobot.extras.models import Status as OrmStatus
from nautobot.ipam.models import VLAN as OrmVLAN
from nautobot.ipam.models import VRF as OrmVRF
from nautobot.ipam.models import IPAddress as OrmIPAddress
from nautobot.ipam.models import IPAddressToInterface
from nautobot.ipam.models import Namespace as OrmNamespace
from nautobot.ipam.models import Prefix as OrmPrefix
from nautobot_ssot.integrations.device42.constant import PLUGIN_CFG
from nautobot_ssot.integrations.device42.diffsync.models.base.ipam import VLAN, IPAddress, Subnet, VRFGroup
from nautobot_ssot.integrations.device42.utils import nautobot


class NautobotVRFGroup(VRFGroup):
    """Nautobot VRFGroup model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create VRF object in Nautobot."""
        _namespace = OrmNamespace.objects.get_or_create(name=ids["name"], description=attrs["description"])[0]
        _vrf = OrmVRF(name=ids["name"], description=attrs["description"], namespace=_namespace)
        diffsync.job.logger.info(f"Creating VRF {_vrf.name}.")
        _vrf.validated_save()
        # for every VRF we want to create a Namespace to ensure duplicate subnets can function.
        if attrs.get("tags"):
            _vrf.tags.set(attrs["tags"])
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_vrf)
        _vrf.validated_save()
        diffsync.vrf_map[ids["name"]] = _vrf.id
        diffsync.namespace_map[ids["name"]] = _namespace.id
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update VRF object in Nautobot."""
        _vrf = OrmVRF.objects.get(id=self.uuid)
        self.diffsync.job.logger.info(f"Updating VRF {_vrf.name}.")
        if "description" in attrs:
            _vrf.description = attrs["description"]
        if "tags" in attrs:
            if attrs.get("tags"):
                _vrf.tags.set(attrs["tags"])
            else:
                _vrf.tags.clear()
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_vrf)
        _vrf.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete VRF object from Nautobot.

        Because VRF has a direct relationship with many other objects it can't be deleted before anything else.
        The self.diffsync.objects_to_delete dictionary stores all objects for deletion and removes them from Nautobot
        in the correct order. This is used in the Nautobot adapter sync_complete function.
        """
        if PLUGIN_CFG.get("device42_delete_on_sync"):
            super().delete()
            self.diffsync.job.logger.info(f"VRF {self.name} will be deleted.")
            vrf = OrmVRF.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["vrf"].append(vrf)  # pylint: disable=protected-access
        return self


class NautobotSubnet(Subnet):
    """Nautobot Subnet model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Prefix object in Nautobot."""
        prefix = f"{ids['network']}/{ids['mask_bits']}"
        _pf = OrmPrefix(
            prefix=prefix,
            description=attrs["description"],
            namespace_id=diffsync.namespace_map[ids["vrf"]] if ids["vrf"] in diffsync.namespace_map else "Global",
            status_id=diffsync.status_map["Active"],
        )
        _pf.validated_save()
        if ids["mask_bits"] == 0:
            _pf.type = "container"
        diffsync.job.logger.info(f"Creating Prefix {prefix} in VRF {ids['vrf']}.")
        if ids.get("vrf"):
            _pf.vrfs.add(diffsync.vrf_map[ids["vrf"]])
        if attrs.get("tags"):
            _pf.tags.set(attrs["tags"])
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_pf)
        _pf.validated_save()
        if ids["vrf"] not in diffsync.prefix_map:
            diffsync.prefix_map[ids["vrf"]] = {}
        diffsync.prefix_map[ids["vrf"]][prefix] = _pf.id
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Prefix object in Nautobot."""
        _pf = OrmPrefix.objects.get(id=self.uuid)
        self.diffsync.job.logger.info(f"Updating Prefix {_pf.prefix}.")
        if "description" in attrs:
            _pf.description = attrs["description"]
        if "tags" in attrs:
            if attrs.get("tags"):
                _pf.tags.set(attrs["tags"])
            else:
                _pf.tags.clear()
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_pf)
        _pf.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Subnet object from Nautobot.

        Because Subnet has a direct relationship with many other objects it can't be deleted before anything else.
        The self.diffsync.objects_to_delete dictionary stores all objects for deletion and removes them from Nautobot
        in the correct order. This is used in the Nautobot adapter sync_complete function.
        """
        if PLUGIN_CFG.get("device42_delete_on_sync"):
            super().delete()
            subnet = OrmPrefix.objects.get(id=self.uuid)
            self.diffsync.job.logger.info(f"Prefix {subnet.prefix} will be deleted.")
            self.diffsync.objects_to_delete["subnet"].append(subnet)  # pylint: disable=protected-access
        return self


class NautobotIPAddress(IPAddress):
    """Nautobot IP Address model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create IP Address object in Nautobot."""
        _address = ids["address"]
        try:
            prefix = OrmPrefix.objects.get(
                prefix=ids["subnet"], namespace=OrmNamespace.objects.get(name=attrs["namespace"])
            )
        except OrmPrefix.DoesNotExist:
            diffsync.job.logger.error(f"Unable to find prefix {ids['subnet']} to create IPAddress {_address} for.")
            return None
        _ip = OrmIPAddress(
            address=_address,
            parent_id=prefix.id,
            status_id=diffsync.status_map["Active"] if attrs.get("available") else diffsync.status_map["Reserved"],
            description=attrs["label"] if attrs.get("label") else "",
        )
        _ip.validated_save()
        if attrs.get("device") and attrs.get("interface"):
            try:
                diffsync.job.logger.info(f"Creating IPAddress {_address}.")
                intf = diffsync.port_map[attrs["device"]][attrs["interface"]]
                assign_ip = IPAddressToInterface.objects.create(ip_address=_ip, interface_id=intf, vm_interface=None)
                assign_ip.validated_save()
                if attrs.get("primary"):
                    if _ip.ip_version == 4:
                        assign_ip.interface.device.primary_ip4 = _ip
                    else:
                        assign_ip.interface.device.primary_ip6 = _ip
                    assign_ip.interface.device.validated_save()
            except KeyError:
                diffsync.job.logger.debug(
                    f"Unable to find Interface {attrs['interface']} for {attrs['device']}.",
                )
        if attrs.get("interface"):
            if re.search(r"[Ll]oopback", attrs["interface"]):
                _ip.role = "loopback"
        if attrs.get("tags"):
            _ip.tags.set(attrs["tags"])
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_ip)
        _ip.validated_save()
        if attrs["namespace"] not in diffsync.ipaddr_map:
            diffsync.ipaddr_map[attrs["namespace"]] = {}
        diffsync.ipaddr_map[attrs["namespace"]][_address] = _ip.id
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update IPAddress object in Nautobot."""
        try:
            _ipaddr = OrmIPAddress.objects.get(id=self.uuid)
        except OrmIPAddress.DoesNotExist:
            if self.diffsync.job.debug:
                self.diffsync.job.logger.debug(
                    "IP Address passed to update but can't be found. This shouldn't happen. Why is this happening?!?!"
                )
            return
        self.diffsync.job.logger.info(f"Updating IPAddress {_ipaddr.address}")
        if "available" in attrs:
            _ipaddr.status = (
                OrmStatus.objects.get(name="Active") if attrs["available"] else OrmStatus.objects.get(name="Reserved")
            )
        if "label" in attrs:
            _ipaddr.description = attrs["label"] if attrs.get("label") else ""
        if attrs.get("device") and attrs.get("interface"):
            _device = attrs["device"]
            try:
                intf = OrmInterface.objects.get(device__name=_device, name=attrs["interface"])
                assign_ip = IPAddressToInterface.objects.create(
                    ip_address=_ipaddr, interface_id=intf.id, vm_interface=None
                )
                assign_ip.validated_save()
                try:
                    _ipaddr.validated_save()
                except ValidationError as err:
                    self.diffsync.job.logger.warning(
                        f"Failure updating Device & Interface for {_ipaddr.address}. {err}"
                    )
            except OrmInterface.DoesNotExist as err:
                self.diffsync.job.logger.warning(
                    f"Unable to find Interface {attrs['interface']} for {attrs['device']}. {err}"
                )
        elif attrs.get("device"):
            try:
                intf = self.diffsync.port_map[attrs["device"]][self.interface]
                assign_ip = IPAddressToInterface.objects.create(
                    ip_address=_ipaddr, interface_id=intf, vm_interface=None
                )
                assign_ip.validated_save()
            except OrmInterface.DoesNotExist as err:
                self.diffsync.job.logger.debug(
                    f"Unable to find Interface {attrs['interface'] if attrs.get('interface') else self.interface} for {attrs['device']} {err}"
                )
        elif attrs.get("interface"):
            try:
                OrmInterface.objects.get(name=attrs["interface"], device__name=self.device)
            except OrmInterface.DoesNotExist:
                for port in self.diffsync.objects_to_create["ports"]:
                    if port.name == attrs["interface"] and port.device_id == self.diffsync.device_map[self.device]:
                        try:
                            port.validated_save()
                        except ValidationError as err:
                            self.diffsync.job.logger.warning(
                                f"Failure saving port {port.name} for IPAddress {_ipaddr.address}. {err}"
                            )
            try:
                if attrs.get("device") and attrs["device"] in self.diffsync.port_map:
                    intf = self.diffsync.port_map[attrs["device"]][attrs["interface"]]
                else:
                    intf = self.diffsync.port_map[self.device][attrs["interface"]]
                assign_ip = IPAddressToInterface.objects.create(
                    ip_address=_ipaddr, interface_id=intf, vm_interface=None
                )
                assign_ip.validated_save()
                try:
                    _ipaddr.validated_save()
                except ValidationError as err:
                    self.diffsync.job.logger.warning(f"Failure updating Interface for {_ipaddr.address}. {err}")
            except KeyError as err:
                self.diffsync.job.logger.debug(
                    f"Unable to find Interface {attrs['interface']} for {attrs['device'] if attrs.get('device') else self.device}. {err}"
                )
        if attrs.get("primary") or self.primary is True:
            if attrs.get("device"):
                device = attrs["device"]
            else:
                device = self.device
            if attrs.get("interface"):
                intf = attrs["interface"]
            else:
                intf = self.interface
            intf = OrmInterface.objects.get(device__name=device, name=intf)
            ip_to_intf = IPAddressToInterface.objects.filter(ip_address=_ipaddr, interface=intf).first()
            if ip_to_intf and (getattr(_ipaddr, "primary_ip4_for") or getattr(_ipaddr, "primary_ip6_for")):
                if _ipaddr.ip_version == 4:
                    ip_to_intf.interface.device.primary_ip4 = _ipaddr
                else:
                    ip_to_intf.interface.device.primary_ip6 = _ipaddr
                ip_to_intf.interface.device.validated_save()
            else:
                self.diffsync.job.logger.warning(
                    f"IPAddress {_ipaddr.address} is showing unassigned from an Interface so can't be marked primary."
                )
        if "tags" in attrs:
            if attrs.get("tags"):
                _ipaddr.tags.set(attrs["tags"])
            else:
                _ipaddr.tags.clear()
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_ipaddr)
        try:
            _ipaddr.validated_save()
            return super().update(attrs)
        except ValidationError as err:
            self.diffsync.job.logger.warning(f"Unable to update IP Address {self.address} with {attrs}. {err}")
            return None

    def delete(self):
        """Delete IPAddress object from Nautobot.

        Because IPAddress has a direct relationship with many other objects it can't be deleted before anything else.
        The self.diffsync.objects_to_delete dictionary stores all objects for deletion and removes them from Nautobot
        in the correct order. This is used in the Nautobot adapter sync_complete function.
        """
        if PLUGIN_CFG.get("device42_delete_on_sync"):
            super().delete()
            self.diffsync.job.logger.info(f"IP Address {self.address} will be deleted.")
            ipaddr = OrmIPAddress.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["ipaddr"].append(ipaddr)  # pylint: disable=protected-access
        return self


class NautobotVLAN(VLAN):
    """Nautobot VLAN model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create VLAN object in Nautobot."""
        _site_name = None
        if ids.get("building") and ids["building"] != "Unknown":
            _site_name = ids["building"]
        else:
            _site_name = "Global"
        diffsync.job.logger.info(f"Creating VLAN {ids['vlan_id']} {attrs['name']} for {_site_name}")
        new_vlan = OrmVLAN(
            name=attrs["name"],
            vid=ids["vlan_id"],
            location=(
                diffsync.site_map[_site_name] if _site_name in diffsync.site_map and _site_name != "Global" else None
            ),
            status_id=diffsync.status_map["Active"],
            description=attrs["description"],
        )
        new_vlan.validated_save()
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=new_vlan)
        if attrs.get("tags"):
            new_vlan.tags.set(attrs["tags"])
        new_vlan.validated_save()
        if _site_name not in diffsync.vlan_map:
            diffsync.vlan_map[_site_name] = {}
        diffsync.vlan_map[_site_name][ids["vlan_id"]] = new_vlan.id
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update VLAN object in Nautobot."""
        _vlan = OrmVLAN.objects.get(id=self.uuid)
        self.diffsync.job.logger.info(
            f"Updating VLAN {_vlan.name} {_vlan.vid} for {_vlan.location.name if _vlan.location else 'Global'}."
        )
        if "name" in attrs:
            _vlan.name = attrs["name"]
        if "description" in attrs:
            _vlan.description = attrs["description"] if attrs.get("description") else ""
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_vlan)
        if "tags" in attrs:
            if attrs.get("tags"):
                nautobot.update_tags(tagged_obj=_vlan, new_tags=attrs["tags"])
            else:
                _vlan.tags.clear()
        _vlan.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete VLAN object from Nautobot.

        Because VLAN has a direct relationship with many other objects it can't be deleted before anything else.
        The self.diffsync.objects_to_delete dictionary stores all objects for deletion and removes them from Nautobot
        in the correct order. This is used in the Nautobot adapter sync_complete function.
        """
        if PLUGIN_CFG.get("device42_delete_on_sync"):
            super().delete()
            self.diffsync.job.logger.info(f"VLAN {self.name} {self.vlan_id} {self.building} will be deleted.")
            vlan = OrmVLAN.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["vlan"].append(vlan)  # pylint: disable=protected-access
        return self
