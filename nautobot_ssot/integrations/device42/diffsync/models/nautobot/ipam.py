"""DiffSyncModel IPAM subclasses for Nautobot Device42 data sync."""

import re
from django.contrib.contenttypes.models import ContentType
from django.forms import ValidationError
from django.utils.text import slugify
from nautobot.dcim.models import Interface as OrmInterface
from nautobot.extras.models import Status as OrmStatus
from nautobot.ipam.models import VLAN as OrmVLAN
from nautobot.ipam.models import VRF as OrmVRF
from nautobot.ipam.models import IPAddress as OrmIPAddress
from nautobot.ipam.models import Prefix as OrmPrefix
from nautobot_ssot.integrations.device42.constant import PLUGIN_CFG
from nautobot_ssot.integrations.device42.diffsync.models.base.ipam import VLAN, IPAddress, Subnet, VRFGroup
from nautobot_ssot.integrations.device42.utils import nautobot


class NautobotVRFGroup(VRFGroup):
    """Nautobot VRFGroup model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create VRF object in Nautobot."""
        _vrf = OrmVRF(name=ids["name"], description=attrs["description"])
        diffsync.job.log_info(message=f"Creating VRF {_vrf.name}.")
        if attrs.get("tags"):
            for _tag in nautobot.get_tags(attrs["tags"]):
                _vrf.tags.add(_tag)
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_vrf)
        diffsync.objects_to_create["vrfs"].append(_vrf)
        diffsync.vrf_map[ids["name"]] = _vrf.id
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update VRF object in Nautobot."""
        _vrf = OrmVRF.objects.get(id=self.uuid)
        self.diffsync.job.log_info(message=f"Updating VRF {_vrf.name}.")
        if "description" in attrs:
            _vrf.description = attrs["description"]
        if "tags" in attrs:
            if attrs.get("tags"):
                nautobot.update_tags(tagged_obj=_vrf, new_tags=attrs["tags"])
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
        if PLUGIN_CFG.get("delete_on_sync"):
            super().delete()
            self.diffsync.job.log_info(message=f"VRF {self.name} will be deleted.")
            vrf = OrmVRF.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["vrf"].append(vrf)  # pylint: disable=protected-access
        return self


class NautobotSubnet(Subnet):
    """Nautobot Subnet model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Prefix object in Nautobot."""
        if ids.get("vrf"):
            vrf_name = ids["vrf"]
        else:
            vrf_name = "unknown"
        prefix = f"{ids['network']}/{ids['mask_bits']}"
        diffsync.job.log_info(message=f"Creating Prefix {prefix} in VRF {vrf_name}.")
        _pf = OrmPrefix(
            prefix=prefix,
            vrf_id=diffsync.vrf_map[vrf_name],
            description=attrs["description"],
            status_id=diffsync.status_map["active"],
        )
        if attrs.get("tags"):
            for _tag in nautobot.get_tags(attrs["tags"]):
                _pf.tags.add(_tag)
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_pf)
        diffsync.objects_to_create["prefixes"].append(_pf)
        if vrf_name not in diffsync.prefix_map:
            diffsync.prefix_map[vrf_name] = {}
        diffsync.prefix_map[vrf_name][f"{ids['network']}/{ids['mask_bits']}"] = _pf.id
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Prefix object in Nautobot."""
        _pf = OrmPrefix.objects.get(id=self.uuid)
        self.diffsync.job.log_info(message=f"Updating Prefix {_pf.prefix}.")
        if "description" in attrs:
            _pf.description = attrs["description"]
        if "tags" in attrs:
            if attrs.get("tags"):
                nautobot.update_tags(tagged_obj=_pf, new_tags=attrs["tags"])
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
        if PLUGIN_CFG.get("delete_on_sync"):
            super().delete()
            subnet = OrmPrefix.objects.get(id=self.uuid)
            self.diffsync.job.log_info(message=f"Prefix {subnet.prefix} will be deleted.")
            self.diffsync.objects_to_delete["subnet"].append(subnet)  # pylint: disable=protected-access
        return self


class NautobotIPAddress(IPAddress):
    """Nautobot IP Address model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create IP Address object in Nautobot."""
        # if "/32" in ids["address"] and attrs.get("primary"):
        #     _pf = OrmPrefix.objects.net_contains(ids["address"])
        #     # the last Prefix is the most specific and is assumed the one the IP address resides in
        #     if len(_pf) > 1:
        #         _range = _pf[len(_pf) - 1]
        #         _netmask = _range.prefix_length
        #     else:
        #         # for the edge case where the DNS answer doesn't reside in a pre-existing Prefix
        #         _netmask = "32"
        #     _address = re.sub(r"\/32", f"/{_netmask}", ids["address"])
        # else:

        # Define regex match for Management interface (ex Management/Mgmt/mgmt/management)
        # mgmt = r"^[mM]anagement|^[mM]gmt"

        _address = ids["address"]
        _ip = OrmIPAddress(
            address=_address,
            vrf_id=diffsync.vrf_map[ids["vrf"]] if ids.get("vrf") else None,
            status_id=diffsync.status_map["active"] if not attrs.get("available") else diffsync.status_map["reserved"],
            description=attrs["label"] if attrs.get("label") else "",
        )
        if attrs.get("device") and attrs.get("interface"):
            try:
                diffsync.job.log_info(message=f"Creating IPAddress {_address}.")
                intf = diffsync.port_map[attrs["device"]][attrs["interface"]]
                _ip.assigned_object_type = ContentType.objects.get(app_label="dcim", model="interface")
                _ip.assigned_object_id = intf

                if attrs.get("primary"):
                    diffsync.objects_to_create["device_primary_ip"].append(
                        (diffsync.device_map[attrs["device"]], _ip.id)
                    )
            except KeyError:
                diffsync.job.log_debug(
                    message=f"Unable to find Interface {attrs['interface']} for {attrs['device']}.",
                )
        if attrs.get("interface"):
            if re.search(r"[Ll]oopback", attrs["interface"]):
                _ip.role = "loopback"
        if attrs.get("tags"):
            nautobot.update_tags(tagged_obj=_ip, new_tags=attrs["tags"])
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_ip)
        diffsync.objects_to_create["ipaddrs"].append(_ip)
        if ids.get("vrf"):
            vrf_name = ids["vrf"]
        else:
            vrf_name = "global"
        if vrf_name not in diffsync.ipaddr_map:
            diffsync.ipaddr_map[vrf_name] = {}
        diffsync.ipaddr_map[vrf_name][_address] = _ip.id
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update IPAddress object in Nautobot."""
        try:
            _ipaddr = OrmIPAddress.objects.get(id=self.uuid)
        except OrmIPAddress.DoesNotExist:
            if self.diffsync.job.kwargs.get("debug"):
                self.diffsync.job.log_debug(
                    message="IP Address passed to update but can't be found. This shouldn't happen. Why is this happening?!?!"
                )
            return
        self.diffsync.job.log_info(
            message=f"Updating IPAddress {_ipaddr.address} for {_ipaddr.vrf.name if _ipaddr.vrf else ''}"
        )
        if "available" in attrs:
            _ipaddr.status = (
                OrmStatus.objects.get(name="Active")
                if not attrs["available"]
                else OrmStatus.objects.get(name="Reserved")
            )
        if "label" in attrs:
            _ipaddr.description = attrs["label"] if attrs.get("label") else ""
        if attrs.get("device") and attrs.get("interface"):
            _device = attrs["device"]
            if self.primary:
                nautobot.unassign_primary(_ipaddr)
            try:
                intf = OrmInterface.objects.get(device__name=_device, name=attrs["interface"])
                _ipaddr.assigned_object_type = ContentType.objects.get(app_label="dcim", model="interface")
                _ipaddr.assigned_object_id = intf.id
                try:
                    _ipaddr.validated_save()
                except ValidationError as err:
                    self.diffsync.job.log_warning(
                        message=f"Failure updating Device & Interface for {_ipaddr.address}. {err}"
                    )
            except OrmInterface.DoesNotExist as err:
                self.diffsync.job.log_warning(
                    message=f"Unable to find Interface {attrs['interface']} for {attrs['device']}. {err}"
                )
        elif attrs.get("device"):
            try:
                intf = OrmInterface.objects.get(device__name=attrs["device"], name=self.interface)
                _ipaddr.assigned_object_type = ContentType.objects.get(app_label="dcim", model="interface")
                _ipaddr.assigned_object_id = intf.id
                nautobot.unassign_primary(_ipaddr)
            except OrmInterface.DoesNotExist as err:
                self.diffsync.job.log_debug(
                    message=f"Unable to find Interface {attrs['interface'] if attrs.get('interface') else self.interface} for {attrs['device']} {err}"
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
                            self.diffsync.job.log_warning(
                                message=f"Failure saving port {port.name} for IPAddress {_ipaddr.address}. {err}"
                            )
            try:
                if attrs.get("device") and attrs["device"] in self.diffsync.port_map:
                    intf = self.diffsync.port_map[attrs["device"]][attrs["interface"]]
                else:
                    intf = self.diffsync.port_map[self.device][attrs["interface"]]
                _ipaddr.assigned_object_type = ContentType.objects.get(app_label="dcim", model="interface")
                _ipaddr.assigned_object_id = intf
                try:
                    _ipaddr.validated_save()
                except ValidationError as err:
                    self.diffsync.job.log_warning(message=f"Failure updating Interface for {_ipaddr.address}. {err}")
            except KeyError as err:
                self.diffsync.job.log_debug(
                    message=f"Unable to find Interface {attrs['interface']} for {attrs['device'] if attrs.get('device') else self.device}. {err}"
                )
        if attrs.get("primary") or self.primary is True:
            if getattr(_ipaddr, "assigned_object"):
                if _ipaddr.family == 4:
                    _ipaddr.assigned_object.device.primary_ip4 = _ipaddr
                else:
                    _ipaddr.assigned_object.device.primary_ip6 = _ipaddr
                _ipaddr.assigned_object.device.validated_save()
            else:
                self.diffsync.job.log_warning(
                    message=f"IPAddress {_ipaddr.address} is showing unassigned from an Interface so can't be marked primary."
                )
        if "tags" in attrs:
            if attrs.get("tags"):
                nautobot.update_tags(tagged_obj=_ipaddr, new_tags=attrs["tags"])
            else:
                _ipaddr.tags.clear()
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=_ipaddr)
        try:
            _ipaddr.validated_save()
            return super().update(attrs)
        except ValidationError as err:
            self.diffsync.job.log_warning(message=f"Unable to update IP Address {self.address} with {attrs}. {err}")
            return None

    def delete(self):
        """Delete IPAddress object from Nautobot.

        Because IPAddress has a direct relationship with many other objects it can't be deleted before anything else.
        The self.diffsync.objects_to_delete dictionary stores all objects for deletion and removes them from Nautobot
        in the correct order. This is used in the Nautobot adapter sync_complete function.
        """
        if PLUGIN_CFG.get("delete_on_sync"):
            super().delete()
            self.diffsync.job.log_info(message=f"IP Address {self.address} will be deleted.")
            ipaddr = OrmIPAddress.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["ipaddr"].append(ipaddr)  # pylint: disable=protected-access
        return self


class NautobotVLAN(VLAN):
    """Nautobot VLAN model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create VLAN object in Nautobot."""
        _site_name = None, None
        if ids["building"] != "Unknown":
            _site_name = slugify(ids["building"])
        else:
            _site_name = "global"
        diffsync.job.log_info(message=f"Creating VLAN {ids['vlan_id']} {attrs['name']} for {_site_name}")
        new_vlan = OrmVLAN(
            name=attrs["name"],
            vid=ids["vlan_id"],
            site_id=diffsync.site_map[_site_name] if _site_name != "global" else None,
            status_id=diffsync.status_map["active"],
            description=attrs["description"],
        )
        if attrs.get("custom_fields"):
            nautobot.update_custom_fields(new_cfields=attrs["custom_fields"], update_obj=new_vlan)
        if attrs.get("tags"):
            nautobot.update_tags(tagged_obj=new_vlan, new_tags=attrs["tags"])
        diffsync.objects_to_create["vlans"].append(new_vlan)
        if _site_name not in diffsync.vlan_map:
            diffsync.vlan_map[_site_name] = {}
        diffsync.vlan_map[_site_name][ids["vlan_id"]] = new_vlan.id
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update VLAN object in Nautobot."""
        _vlan = OrmVLAN.objects.get(id=self.uuid)
        self.diffsync.job.log_info(
            message=f"Updating VLAN {_vlan.name} {_vlan.vid} for {_vlan.site.name if _vlan.site else 'global'}."
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
        if PLUGIN_CFG.get("delete_on_sync"):
            super().delete()
            self.diffsync.job.log_info(message=f"VLAN {self.name} {self.vlan_id} {self.building} will be deleted.")
            vlan = OrmVLAN.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["vlan"].append(vlan)  # pylint: disable=protected-access
        return self
