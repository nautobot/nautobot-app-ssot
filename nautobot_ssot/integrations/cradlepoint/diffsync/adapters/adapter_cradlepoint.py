from diffsync import Adapter
from nautobot_ssot.integrations.cradlepoint.utilities.cradlepoint_client import (
    CradlepointClient,
)
import os
import json
from nautobot_ssot.integrations.cradlepoint.diffsync.models.cradlepoint import (
    CradlepointStatus,
    CradlepointRole,
    CradlepointDeviceType,
    CradlepointDevice,
)

DEFAULT_MAUFACTURER = "CradlePoint Inc."
DEFAULT_ROLE = "Router"
# TODO: Need to figure out how to actually get the correct location.
DEFAULT_LOCATION = "Gotham"


class CradlepointAdapter(Adapter):
    """CradlePoint Adapter."""

    status = CradlepointStatus
    role = CradlepointRole
    device_type = CradlepointDeviceType
    device = CradlepointDevice

    top_level = ("status", "role", "device_type", "device")

    def __init__(self, *args, job=None, sync=None, client, config, **kwargs):
        """Initialize Cradlepoint Adapter."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.client = client
        self.config = config

    # TODO: Implement this method
    def find_location(self, san):
        """Find the location for the router by checking against existing SANs.

        Args:
            san (str): The SAN for the device.
        """
        return DEFAULT_LOCATION

    def load_device_type(self, device_type_name):
        """Load device type from Cradlepoint into DiffSync store.

        Args:
            device_type_name (str): Device type name to load.
        """
        device_type_name = device_type_name.upper()
        device_type, _ = self.get_or_instantiate(
            self.device_type,
            ids={"model": device_type_name, "manufacturer__name": DEFAULT_MAUFACTURER},
        )

    def load_status(self, status_name):
        """Load status from Cradlepoint into DiffSync store.

        Args:
            status_name (str): Status name to load.
        """
        status_name = status_name.capitalize()
        status, _ = self.get_or_instantiate(
            self.status,
            ids={"name": status_name},
            attrs={
                "content_types": [
                    {"model": "circuit", "app_label": "circuits"},
                    {"model": "device", "app_label": "dcim"},
                    {"model": "powerfeed", "app_label": "dcim"},
                    {"model": "virtualmachine", "app_label": "virtualization"},
                    {"model": "controller", "app_label": "dcim"},
                    {"model": "module", "app_label": "dcim"},
                ]
            },
        )

    def load_prefix(self, primary_ip):
        """Deduce Prefix from Primary IP for a given device and create diffsync model.

        Args:
            primary_ip (str): Primary IP for the device.
        """
        diffsync_prefix, _ = self.get_or_instantiate(
            self.prefix,
            ids={
                "network": "0.0.0.0",  # noqa: S104
                "prefix_length": 0,
                "namespace__name": "Global",
                "status__name": "Active",
            },
            attrs={"type": "container"},
        )
        return diffsync_prefix

    def load_ip_address(
        self, diffsync_prefix, diffsync_interface, diffsync_device, ip_address
    ):
        """Load IP Address from Cradlepoint into DiffSync store.

        Args:
            diffsync_prefix (CradlepointPrefix): Prefix for the IP Address.
            diffsync_interface (CradlepointInterface): Interface for the IP Address.
            diffsync_device (CradlepointDevice): Device for the IP Address.
            ip_address (str): IP Address to load.
        """
        diffsync_ip_address, _ = self.get_or_instantiate(
            self.ip_address,
            ids={
                "host": ip_address,
                "mask_length": 32,
                "status__name": "Active",
            },
        )
        return diffsync_ip_address

    def load_router(self, record):
        """Load router from Cradlepoint into DiffSync store.

        Args:
            record (dict): Current record information from Cradlepoint.
        """
        router_information = {
            "name": record["router"]["serial_number"],
            "device_type__model": record["router"]["full_product_name"],
            "role__name": DEFAULT_ROLE,  # TODO: Replace with some logic to get the correct role
            "status__name": record["router"]["state"].capitalize(),
            "serial": record["router"]["serial_number"],
            "primary_ip4__host": record["ipv4_address"],
            "san": record["router"]["name"],
        }
        router_information["location__name"] = self.find_location(
            router_information["san"]
        )
        self.load_status(router_information["status__name"])
        self.load_device_type(router_information["device_type__model"])

        router, _ = self.get_or_instantiate(
            self.device,
            ids={"name": router_information.pop("name")},
            attrs=router_information,
        )
        return router

    def load_primary_lan(self, record, diffsync_device):
        """Load devices from Cradlepoint."""
        interface_information = {
            "device__name": diffsync_device.name,
            "name": record["hostname"],
            "type": "other",
            "status__name": "Active",
            "mac_address": record["router"]["mac"],
            "ip_addresses": [{"host": record["ipv4_address"], "mask_length": 32}],
        }
        ip_address = record["ipv4_address"]
        diffsync_prefix = self.load_prefix(ip_address)

        diffsync_interface, _ = self.get_or_instantiate(
            self.interface,
            ids={
                "name": interface_information.pop("name"),
                "device__name": interface_information.pop("device__name"),
            },
            attrs=interface_information,
        )
        diffsync_device.add_child(diffsync_interface)

        ip_address = self.load_ip_address(
            diffsync_prefix, diffsync_interface, diffsync_device, ip_address
        )

    # def load_sim1(self, record, diffsync_device):

    def load(self):
        """Entrypoint for loading data from Cradlepoint."""
        fixtures_path = os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            ),
        )
        device_files = ["tests/fixtures/cradlepoint_devices.json"]

        # TODO: Figure out which roles we will actually use
        role, _ = self.get_or_instantiate(
            self.role,
            ids={"name": DEFAULT_ROLE},
            attrs={"content_types": [{"app_label": "dcim", "model": "device"}]},
        )

        device_dict = {}
        for file_name in device_files:
            file_path = os.path.join(fixtures_path, file_name)
            with open(file_path, "r") as file:
                data = json.load(file)
                for record in data:
                    if record.get("hostname") is None or not record.get("router"):
                        # Log that record has no hostname here
                        continue
                    if record.get("router"):
                        router_data = {
                            "name": record["router"]["serial_number"],
                            "device_type__model": record["router"]["full_product_name"],
                            "role__name": DEFAULT_ROLE,
                            "status__name": record["router"]["state"].capitalize(),
                            "serial": record["router"]["serial_number"],
                            # "primary_ip4__host": record["ipv4_address"],
                            "san": record["router"]["name"],
                            "location__name": self.find_location(
                                record["router"]["name"]
                            ),
                        }

                        # Update only missing fields
                        device_dict.setdefault(
                            record["router"]["serial_number"], {}
                        ).update(
                            {
                                k: v
                                for k, v in router_data.items()
                                if k
                                not in device_dict[record["router"]["serial_number"]]
                            }
                        )

                    if "lan" in record.get("hostname", "").lower():
                        lan_information = {
                            "device__name": record["router"]["serial_number"],
                            "name": record["hostname"],
                            "type": "other",
                            "status__name": "Active",
                            # "mac_address": record["router"]["mac"],
                            "ip_addresses": [
                                {"host": record["ipv4_address"], "mask_length": 32}
                            ],
                        }

                        device_dict.setdefault(
                            record["router"]["serial_number"], {}
                        ).setdefault("interfaces", []).append(lan_information)
                        continue

                    if "SIM1" in record.get("model", ""):
                        sim1_information = {
                            "device__name": record["router"]["serial_number"],
                            "name": record["model"],
                            "type": "other",
                            "status__name": "Active",
                            # "mac_address": record["router"]["mac"],
                            "ip_addresses": [
                                {"host": record["ipv4_address"], "mask_length": 32}
                            ],
                        }

                        device_dict.setdefault(
                            record["router"]["serial_number"], {}
                        ).setdefault("interfaces", []).append(sim1_information)
                        continue

                    if "lan" not in record.get(
                        "hostname", ""
                    ).lower() and "SIM1" not in record.get("model", ""):
                        sim2_information = {
                            "device__name": record["router"]["serial_number"],
                            "name": record["model"],
                            "type": "other",
                            "status__name": "Active",
                            # "mac_address": record["router"]["mac"],
                            "ip_addresses": [
                                {"host": record["ipv4_address"], "mask_length": 32}
                            ],
                        }

                        device_dict.setdefault(
                            record["router"]["serial_number"], {}
                        ).setdefault("interfaces", []).append(sim2_information)
                        continue

        for device_name, device_data in device_dict.items():
            self.load_status(device_data["status__name"])
            self.load_device_type(device_data["device_type__model"])

            for interface in device_data.get("interfaces", []):
                if "lan" in interface.get("name").lower():
                    device_data["primary_ip4__host"] = interface["ip_addresses"][0][
                        "host"
                    ]

            device_interfaces = device_data.pop("interfaces", [])

            diffsync_device, _ = self.get_or_instantiate(
                self.device,
                ids={"name": device_data.pop("name")},
                attrs=device_data,
            )

            for interface in device_interfaces:
                if interface.get("ip_addresses")[0]["host"] is None:
                    interface.pop("ip_addresses")
                else:
                    ip_address = interface["ip_addresses"][0]["host"]
                    diffsync_prefix = self.load_prefix(ip_address)

                diffsync_interface, _ = self.get_or_instantiate(
                    self.interface,
                    ids={
                        "name": interface.pop("name"),
                        "device__name": interface.pop("device__name"),
                    },
                    attrs=interface,
                )
                diffsync_device.add_child(diffsync_interface)

                if interface.get("ip_addresses"):
                    ip_address = self.load_ip_address(
                        diffsync_prefix, diffsync_interface, diffsync_device, ip_address
                    )

    # for record in data:
    #     if record.get("hostname") is not None:
    #         if "lan" in record.get("hostname", "").lower() and record.get(
    #             "router"
    #         ):
    #             diffsync_device = self.load_router(record)
    #             self.load_primary_lan(record, diffsync_device)

    # for record in data:
    #     if record.get("hostname") is not None:
    #         if "SIM1" in record.get("hostname", ""):
    #             diffsync_device = self.load_router(record)
    #             self.load_primary_lan(record, diffsync_device)

    # if record.get("hostname"):
    #     if "lan" in record.get("hostname").lower():
    #         lan_information = {
    #             "device__name": record["router"]["serial_number"],
    #             "name": record["hostname"],
    #             "type": "other",
    #             "status__name": "Active",
    #             "mac_address": record["router"]["mac"],
    #             "ip": record["ipv4_address"],
    #         }
    #         self.load_primary_lan(lan_information, diffsync_device)
