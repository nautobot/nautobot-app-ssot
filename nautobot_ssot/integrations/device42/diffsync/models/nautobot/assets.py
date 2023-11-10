"""DiffSyncModel Asset subclasses for Nautobot Device42 data sync."""

from django.core.exceptions import ValidationError
from nautobot.dcim.models import Device, DeviceType, FrontPort, RearPort, Location
from nautobot_ssot.integrations.device42.constant import PLUGIN_CFG
from nautobot_ssot.integrations.device42.diffsync.models.base.assets import (
    PatchPanel,
    PatchPanelRearPort,
    PatchPanelFrontPort,
)
from nautobot_ssot.integrations.device42.diffsync.models.nautobot.dcim import NautobotRack
from nautobot_ssot.integrations.device42.utils import nautobot


def find_site(diffsync, attrs):
    """Method to determine Site for Patch Panel based upon object attributes."""
    pp_site = False
    try:
        if attrs.get("building"):
            pp_site = diffsync.site_map[attrs["building"]]
        elif attrs.get("room") and attrs.get("rack"):
            rack = diffsync.get(NautobotRack, {"name": attrs["rack"], "group": attrs["room"]})
            site_name = rack.building
            pp_site = diffsync.site_map[site_name]
    except KeyError:
        diffsync.job.logger.warning(f"Unable to find Site {attrs.get('building')}.")
    return pp_site


class NautobotPatchPanel(PatchPanel):
    """Nautobot Patch Panel model."""

    def find_rack(self, diffsync, building: str, room: str, rack: str):
        """Method to determine Site for Patch Panel based upon object attributes."""
        pp_rack = False
        try:
            if building is not None and room is not None and rack is not None:
                pp_rack = diffsync.rack_map[building][room][rack]
            elif rack is not None:
                for new_rack in diffsync.objects_to_create["racks"]:
                    if new_rack.name is rack:
                        pp_rack = new_rack.id
        except KeyError:
            if diffsync.job.debug:
                diffsync.job.logger.warning(f"Unable to find Rack using Room {room} & Rack {rack}.")
        return pp_rack

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Patch Panel Device in Nautobot."""
        diffsync.job.logger.info(f"Creating Patch Panel {ids['name']} Device.")
        try:
            diffsync.device_map[ids["name"]]
        except KeyError:
            pp_site = find_site(diffsync=diffsync, attrs=attrs)
            pp_rack = cls.find_rack(
                cls, diffsync=diffsync, building=attrs.get("building"), room=attrs.get("room"), rack=attrs.get("rack")
            )
            pp_role = nautobot.verify_device_role(diffsync=diffsync, role_name="patch panel")
            if attrs.get("in_service"):
                pp_status = diffsync.status_map["Active"]
            else:
                pp_status = diffsync.status_map["Offline"]
            patch_panel = Device(
                name=ids["name"],
                status_id=pp_status,
                location_id=pp_site,
                device_type_id=diffsync.devicetype_map[attrs["model"]],
                role_id=pp_role,
                serial=attrs["serial_no"],
            )
            if pp_rack is not False and attrs.get("position") and attrs.get("orientation"):
                patch_panel.rack_id = pp_rack
                patch_panel.position = int(attrs["position"])
                patch_panel.face = attrs["orientation"]
            try:
                patch_panel.validated_save()
                diffsync.device_map[ids["name"]] = patch_panel.id
                return super().create(diffsync, ids=ids, attrs=attrs)
            except ValidationError as err:
                if diffsync.job.debug:
                    diffsync.job.logger.warning(f"Unable to create {ids['name']} patch panel. {err}")
                return None
            except Location.DoesNotExist as err:
                diffsync.job.logger.warning(f"Building {pp_site} can't be found for {ids['name']}. {err}")

    def update(self, attrs):
        """Update Patch Panel object in Nautobot."""
        ppanel = Device.objects.get(id=self.uuid)
        self.diffsync.job.logger.info(f"Updating Patch Panel {ppanel.name} Device.")
        if "in_service" in attrs:
            if attrs["in_service"] is True:
                ppanel.status_id = self.diffsync.status_map["Active"]
            else:
                ppanel.status_id = self.diffsync.status_map["Offline"]
        if "vendor" in attrs and "model" in attrs:
            ppanel.device_type = DeviceType.objects.get(model=attrs["model"])
        if "orientation" in attrs:
            ppanel.face = attrs["orientation"]
        if "position" in attrs:
            ppanel.position = attrs["position"]
        if "building" in attrs:
            pp_site = find_site(diffsync=self.diffsync, attrs=attrs)
            if pp_site:
                ppanel.location_id = pp_site
        if "room" in attrs or "rack" in attrs:
            if attrs.get("building"):
                _building = attrs["building"]
            else:
                _building = self.building
            if "room" in attrs:
                _room = attrs["room"]
            else:
                _room = self.room
            if "rack" in attrs:
                _rack = attrs["rack"]
            else:
                _rack = self.rack
            pp_rack = self.find_rack(diffsync=self.diffsync, building=_building, room=_room, rack=_rack)
            if pp_rack:
                ppanel.rack_id = pp_rack
                ppanel.face = attrs["orientation"] if attrs.get("orientation") else self.orientation
        if "serial_no" in attrs:
            ppanel.serial = attrs["serial_no"]
        try:
            ppanel.validated_save()
            return super().update(attrs)
        except ValidationError as err:
            self.diffsync.job.logger.warning(f"Unable to update {self.name} patch panel. {err}")
            return None

    def delete(self):
        """Delete Patch Panel Device object from Nautobot.

        Because a Patch Panel Device has a direct relationship with Ports it can't be deleted before they are.
        The self.diffsync.objects_to_delete dictionary stores all objects for deletion and removes them from Nautobot
        in the correct order. This is used in the Nautobot adapter sync_complete function.
        """
        if PLUGIN_CFG.get("device42_delete_on_sync"):
            super().delete()
            self.diffsync.job.logger.info(f"Patch panel {self.name} will be deleted.")
            _pp = Device.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["patchpanel"].append(_pp)  # pylint: disable=protected-access
        return self


class NautobotPatchPanelRearPort(PatchPanelRearPort):
    """Nautobot Patch Panel RearPort model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Patch Panel Port in Nautobot."""
        diffsync.job.logger.info(f"Creating patch panel port {ids['name']} for {ids['patchpanel']}.")
        try:
            diffsync.rp_map[ids["patchpanel"]][ids["name"]]
        except KeyError:
            rear_port = RearPort(
                name=ids["name"],
                device_id=diffsync.device_map[ids["patchpanel"]],
                type=attrs["port_type"],
                positions=ids["name"],
            )
            try:
                rear_port.validated_save()
                if ids["patchpanel"] not in diffsync.rp_map:
                    diffsync.rp_map[ids["patchpanel"]] = {}
                diffsync.rp_map[ids["patchpanel"]][ids["name"]] = rear_port.id
                return super().create(diffsync, ids=ids, attrs=attrs)
            except ValidationError as err:
                if diffsync.job.debug:
                    diffsync.job.logger.debug(f"Unable to create patch panel {ids['name']}. {err}")
                return None

    def update(self, attrs):
        """Update RearPort object in Nautobot."""
        port = RearPort.objects.get(id=self.uuid)
        self.diffsync.job.logger.info(f"Updating patch panel port {port.name} for {self.patchpanel}.")
        if "type" in attrs:
            port.type = attrs["type"]
        try:
            port.validated_save()
            return super().update(attrs)
        except ValidationError as err:
            self.diffsync.job.logger.warning(f"Unable to update {self.name} RearPort. {err}")
            return None

    def delete(self):
        """Delete RearPort object from Nautobot."""
        if PLUGIN_CFG.get("device42_delete_on_sync"):
            super().delete()
            self.diffsync.job.logger.info(f"RearPort {self.name} for {self.patchpanel} will be deleted.")
            port = RearPort.objects.get(id=self.uuid)
            port.delete()
        return self


class NautobotPatchPanelFrontPort(PatchPanelFrontPort):
    """Nautobot Patch Panel FrontPort model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Patch Panel FrontPort in Nautobot."""
        diffsync.job.logger.info(f"Creating patch panel front port {ids['name']} for {ids['patchpanel']}.")
        try:
            diffsync.fp_map[ids["patchpanel"]][ids["name"]]
        except KeyError:
            front_port = FrontPort(
                name=ids["name"],
                device_id=diffsync.device_map[ids["patchpanel"]],
                type=attrs["port_type"],
                rear_port_id=diffsync.rp_map[ids["patchpanel"]][ids["name"]],
                rear_port_position=ids["name"],
            )
            try:
                front_port.validated_save()
                if ids["patchpanel"] not in diffsync.fp_map:
                    diffsync.fp_map[ids["patchpanel"]] = {}
                diffsync.fp_map[ids["patchpanel"]][ids["name"]] = front_port.id
                return super().create(diffsync, ids=ids, attrs=attrs)
            except ValidationError as err:
                diffsync.job.logger.debug(f"Unable to create patch panel front port {ids['name']}. {err}")
                return None

    def update(self, attrs):
        """Update FrontPort object in Nautobot."""
        port = FrontPort.objects.get(id=self.uuid)
        self.diffsync.job.logger.info(f"Updating patch panel front port {self.name} for {self.patchpanel}.")
        if "type" in attrs:
            port.type = attrs["type"]
        try:
            port.validated_save()
            return super().update(attrs)
        except ValidationError as err:
            self.diffsync.job.logger.warning(f"Unable to update {self.name} FrontPort. {err}")
            return None

    def delete(self):
        """Delete FrontPort object from Nautobot."""
        if PLUGIN_CFG.get("device42_delete_on_sync"):
            super().delete()
            self.diffsync.job.logger.info(f"FrontPort {self.name} for {self.patchpanel} will be deleted.")
            port = FrontPort.objects.get(id=self.uuid)
            port.delete()
        return self
