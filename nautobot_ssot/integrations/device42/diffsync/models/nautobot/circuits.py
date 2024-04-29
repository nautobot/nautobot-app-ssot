"""DiffSyncModel Circuit subclasses for Nautobot Device42 data sync."""

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from nautobot.circuits.models import Circuit as OrmCircuit
from nautobot.circuits.models import CircuitTermination as OrmCT
from nautobot.circuits.models import Provider as OrmProvider
from nautobot.dcim.models import Cable as OrmCable
from nautobot_ssot.integrations.device42.constant import INTF_SPEED_MAP, PLUGIN_CFG
from nautobot_ssot.integrations.device42.diffsync.models.base.circuits import Circuit, Provider
from nautobot_ssot.integrations.device42.diffsync.models.nautobot.dcim import NautobotDevice
from nautobot_ssot.integrations.device42.utils import nautobot


class NautobotProvider(Provider):
    """Nautobot Provider model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Provider object in Nautobot."""
        diffsync.job.logger.info(f"Creating Provider {ids['name']}.")
        try:
            _provider = diffsync.provider_map[ids["name"]]
        except KeyError:
            _provider = OrmProvider(
                name=ids["name"],
                account=attrs["vendor_acct"] if attrs.get("vendor_acct") else "",
                portal_url=attrs["vendor_url"] if attrs.get("vendor_url") else "",
                noc_contact=attrs["vendor_contact1"] if attrs.get("vendor_contact1") else "",
                admin_contact=attrs["vendor_contact2"] if attrs.get("vendor_contact2") else "",
                comments=attrs["notes"] if attrs.get("notes") else "",
            )
            _provider.validated_save()
            if attrs.get("tags"):
                for _tag in nautobot.get_tags(attrs["tags"]):
                    _provider.tags.add(_tag)
            try:
                _provider.validated_save()
                diffsync.provider_map[ids["name"]] = _provider.id
                return super().create(diffsync, ids=ids, attrs=attrs)
            except ValidationError as err:
                if diffsync.job.debug:
                    diffsync.job.logger.warning(f"Unable to create {ids['name']} provider. {err}")
        return None

    def update(self, attrs):
        """Update Provider object in Nautobot."""
        _prov = OrmProvider.objects.get(id=self.uuid)
        self.diffsync.job.logger.info(f"Updating Provider {_prov.name}.")
        if "notes" in attrs:
            _prov.comments = attrs["notes"]
        if "vendor_url" in attrs:
            _prov.portal_url = attrs["vendor_url"]
        if "vendor_acct" in attrs:
            _prov.account = attrs["vendor_acct"]
        if "vendor_contact1" in attrs:
            _prov.noc_contact = attrs["vendor_contact1"]
        if "vendor_contact2" in attrs:
            _prov.admin_contact = attrs["vendor_contact2"]
        if "tags" in attrs:
            nautobot.update_tags(tagged_obj=_prov, new_tags=attrs["tags"])
        _prov.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Provider object from Nautobot.

        Because Provider has a direct relationship with Circuits it can't be deleted before them.
        The self.diffsync.objects_to_delete dictionary stores all objects for deletion and removes them from Nautobot
        in the correct order. This is used in the Nautobot adapter sync_complete function.
        """
        if PLUGIN_CFG.get("device42_delete_on_sync"):
            self.diffsync.job.logger.info(f"Provider {self.name} will be deleted.")
            super().delete()
            provider = OrmProvider.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["provider"].append(provider)  # pylint: disable=protected-access
        return self


class NautobotCircuit(Circuit):
    """Nautobot TelcoCircuit model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Circuit object in Nautobot."""
        diffsync.job.logger.info(f"Creating Circuit {ids['circuit_id']}.")
        try:
            diffsync.circuit_map[ids["circuit_id"]]
        except KeyError:
            _circuit = OrmCircuit(
                cid=ids["circuit_id"],
                provider_id=diffsync.provider_map[ids["provider"]],
                circuit_type=nautobot.verify_circuit_type(attrs["type"]),
                status_id=diffsync.status_map[attrs["status"]],
                install_date=attrs["install_date"] if attrs.get("install_date") else None,
                commit_rate=attrs["bandwidth"] if attrs.get("bandwidth") else None,
                comments=attrs["notes"] if attrs.get("notes") else "",
            )
            _circuit.validated_save()
            if attrs.get("tags"):
                for _tag in nautobot.get_tags(attrs["tags"]):
                    _circuit.tags.add(_tag)
            if attrs.get("origin_int") and attrs.get("origin_dev"):
                if attrs["origin_dev"] not in diffsync.circuit_map:
                    diffsync.circuit_map[attrs["origin_dev"]] = {}
                diffsync.circuit_map[attrs["origin_dev"]][attrs["origin_int"]] = _circuit.id
                cls.connect_circuit_to_device(
                    diffsync=diffsync,
                    intf=attrs["origin_int"],
                    dev=attrs["origin_dev"],
                    term_side="A",
                    circuit=_circuit,
                )
            if attrs.get("endpoint_int") and attrs.get("endpoint_dev"):
                if attrs["endpoint_dev"] not in diffsync.circuit_map:
                    diffsync.circuit_map[attrs["endpoint_dev"]] = {}
                diffsync.circuit_map[attrs["endpoint_dev"]][attrs["endpoint_int"]] = _circuit.id
                cls.connect_circuit_to_device(
                    diffsync=diffsync,
                    intf=attrs["endpoint_int"],
                    dev=attrs["endpoint_dev"],
                    term_side="Z",
                    circuit=_circuit,
                )
        return super().create(diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Circuit object in Nautobot."""
        _circuit = OrmCircuit.objects.get(id=self.uuid)
        self.diffsync.job.logger.info(f"Updating Circuit {_circuit.cid}.")
        if "notes" in attrs:
            _circuit.comments = attrs["notes"]
        if "type" in attrs:
            _circuit.circuit_type = nautobot.verify_circuit_type(attrs["type"])
        if "status" in attrs:
            _circuit.status_id = self.diffsync.status_map[attrs["status"]]
        if "install_date" in attrs:
            _circuit.install_date = attrs["install_date"]
        if "bandwidth" in attrs:
            _circuit.commit_rate = attrs["bandwidth"]
        if "origin_int" in attrs and "origin_dev" in attrs:
            self.connect_circuit_to_device(
                diffsync=self.diffsync,
                intf=attrs["origin_int"],
                dev=attrs["origin_dev"],
                term_side="A",
                circuit=_circuit,
            )
        if "endpoint_int" in attrs and "endpoint_dev" in attrs:
            self.connect_circuit_to_device(
                diffsync=self.diffsync,
                intf=attrs["endpoint_int"],
                dev=attrs["endpoint_dev"],
                term_side="Z",
                circuit=_circuit,
            )
        if "tags" in attrs:
            nautobot.update_tags(tagged_obj=_circuit, new_tags=attrs["tags"])
        _circuit.validated_save()
        return super().update(attrs)

    @staticmethod
    def connect_circuit_to_device(diffsync, intf: str, dev: str, term_side: str, circuit: OrmCircuit):
        """Method to handle Circuit Termination to a Device.

        Args:
            diffsync (obj): DiffSync Job for maps.
            intf (str): Interface of Device to connect Circuit Termination.
            dev (str): Device with respective interface to connect Circuit to.
            term_side (str): Which side of the CircuitTermination this connection is on, A or Z.
            circuit (OrmCircuit): The actual Circuit object that the CircuitTermination is connecting to.
        """
        try:
            _intf = diffsync.port_map[dev][intf]
            try:
                _term = diffsync.circuit_map[dev][intf]
            except KeyError:
                _site = diffsync.get(NautobotDevice, dev)
                _site = diffsync.site_map[_site.name]
                _term = OrmCT(
                    circuit_id=circuit,
                    term_side=term_side,
                    location_id=_site,
                    port_speed=INTF_SPEED_MAP[_intf.type],
                )
                _term.validated_save()
            if _intf and _term:
                new_cable = OrmCable(
                    termination_a_type=ContentType.objects.get(app_label="dcim", model="interface"),
                    termination_a_id=_intf,
                    termination_b_type=ContentType.objects.get(app_label="circuits", model="circuittermination"),
                    termination_b_id=_term,
                    status_id=diffsync.status_map["Connected"],
                    color=nautobot.get_random_color(),
                )
                new_cable.validated_save()
                if dev not in diffsync.cable_map:
                    diffsync.cable_map[dev] = {}
                diffsync.cable_map[dev][intf] = new_cable.id
        except KeyError:
            diffsync.job.logger.warning(f"Unable to find {dev} in port_map.")

    def delete(self):
        """Delete Provider object from Nautobot.

        Because Provider has a direct relationship with Circuits it can't be deleted before them.
        The self.diffsync.objects_to_delete dictionary stores all objects for deletion and removes them from Nautobot
        in the correct order. This is used in the Nautobot adapter sync_complete function.
        """
        if PLUGIN_CFG.get("device42_delete_on_sync"):
            self.diffsync.job.logger.info(f"Circuit {self.circuit_id} will be deleted.")
            super().delete()
            circuit = OrmCircuit.objects.get(id=self.uuid)
            self.diffsync.objects_to_delete["circuit"].append(circuit)  # pylint: disable=protected-access
        return self
