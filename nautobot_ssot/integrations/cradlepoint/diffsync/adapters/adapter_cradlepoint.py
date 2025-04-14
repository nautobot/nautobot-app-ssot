"""Cradlepoint Adapter for DiffSync."""

import time
from itertools import islice

from diffsync import Adapter

from nautobot_ssot.integrations.cradlepoint.constants import (
    DEFAULT_API_DEVICE_LIMIT,
    DEFAULT_LOCATION,
    DEFAULT_MANUFACTURER,
)
from nautobot_ssot.integrations.cradlepoint.diffsync.models.cradlepoint import (
    CradlepointDevice,
    CradlepointDeviceType,
    CradlepointRole,
    CradlepointStatus,
)


class CradlepointAdapter(Adapter):
    """Cradlepoint Adapter."""

    status = CradlepointStatus
    device_role = CradlepointRole
    device_type = CradlepointDeviceType
    device = CradlepointDevice

    top_level = ("status", "device_role", "device_type", "device")

    def __init__(self, *args, job=None, sync=None, client, config, starting_offset, **kwargs):
        """Initialize Cradlepoint Adapter."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.client = client
        self.config = config
        self.starting_offset = starting_offset
        self.routers = {}
        self.product_mappings = {}

    def find_location(self, san):
        """Find the location for the router by checking against existing SANs.

        Args:
            san (str): The SAN for the device.
        """
        return DEFAULT_LOCATION

    def load_device_role(self, device_role_name):
        """Load device role from Cradlepoint into DiffSync store.

        Args:
            device_role_name (str): Device role name to load.
        """
        device_role, _ = self.get_or_instantiate(
            self.device_role,
            ids={"name": device_role_name},
            attrs={
                "content_types": [
                    {"model": "device", "app_label": "dcim"},
                ]
            },
        )

    def load_device_type(self, device_type_name):
        """Load device type from Cradlepoint into DiffSync store.

        Args:
            device_type_name (str): Device type name to load.
        """
        device_type_name = device_type_name.upper()
        device_type, _ = self.get_or_instantiate(
            self.device_type,
            ids={"model": device_type_name, "manufacturer__name": DEFAULT_MANUFACTURER},
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

    def load_router(self, record):
        """Load router from Cradlepoint into DiffSync store.

        Args:
            record (dict): Current record information from Cradlepoint.
        """
        serial_number = str(record["serial_number"])

        # Load the identifier based on the configuration
        identifier = ""
        for value in self.config.unique_cradlepoint_field_order:
            identifier = record.get(value, None)
            if identifier:
                break
        if not identifier:
            self.job.logger.error(
                "Could not find a unique identifier for router with ID %s",
                record.get("id", "unknown"),
            )
            return

        device_type = self.product_mappings.get(record["product"], "unknown")

        router_information = {
            "name": identifier,
            "device_type__model": device_type.upper(),
            "role__name": record["device_type"].capitalize(),
            "status__name": record["state"].capitalize(),
            "serial": serial_number,
            "cradlepoint_id_number": record["id"],
            # Custom fields in Nautobot do not support float values so we must use strings instead.
            "device_latitude": str(record.get("latitude")),
            "device_longitude": str(record.get("longitude")),
            "device_altitude": str(record.get("altitude_meters")),
            "device_gps_method": record.get("method"),
            "device_accuracy": record.get("accuracy"),
        }
        # The name field is actually the associated SAN.
        router_information["location__name"] = self.find_location(router_information["name"])
        self.load_status(router_information["status__name"])
        self.load_device_type(router_information["device_type__model"])
        self.load_device_role(router_information["role__name"])

        router, _ = self.get_or_instantiate(
            self.device,
            ids={"name": router_information.pop("name")},
            attrs=router_information,
        )
        return router

    def retrieve_router_location(self):
        """Query Cradlepoint API with multiple router IDs for location information."""
        # We are iterating over the IDs here so we don't make a huge request to the locations API and we can window.

        def _segment_iterable(iterable, segment_size):
            """Yield segments of an iterable."""
            iterator = iter(iterable)
            while chunk := list(islice(iterator, segment_size)):
                yield chunk

        for router_id_chunk in _segment_iterable(self.routers.keys(), int(DEFAULT_API_DEVICE_LIMIT) // 4):
            time.sleep(5)
            router_locations = self.client.get_locations(
                {
                    "router__in": ",".join(router_id_chunk),
                    "fields": ",".join(
                        [
                            "accuracy",
                            "altitude_meters",
                            "latitude",
                            "longitude",
                            "method",
                            "router",
                        ]
                    ),
                }
            ).get("data", [])
            # Process the fetched locations
            for record in router_locations:
                router_id = record.pop("router").rstrip("/").rsplit("/", 1)[-1]

                router = self.routers.get(router_id)
                if not router:
                    self.job.logger.info(msg=f"Router ID {router_id} not found in router dictionary.")
                    continue
                # Update the router's information
                router.update(record)

    def load_device_types(self):
        """Populate device type dictionary mapping from Cradlepoint."""
        # Load device types into mapping dictionary
        product_call = self.client.get_products({"limit": 500})
        products = product_call.get("data", [])
        self.product_mappings = {item["resource_url"]: item["name"] for item in products}

    def load(self):
        """Entrypoint for loading data from Cradlepoint."""
        # Load device types into mapping dictionary
        self.load_device_types()

        offset_number = self.starting_offset
        next = True
        call_counter = 1
        # TODO:  This will change to a while loop for the actual implementation.
        while next:
            self.job.logger.info(f"Call counter: {call_counter}")
            call_counter += 1
            routers_call = self.client.get_routers(
                {
                    "limit": int(DEFAULT_API_DEVICE_LIMIT),
                    "offset": offset_number,
                    "fields": ",".join(
                        [
                            "product",
                            "device_type",
                            "state",
                            "serial_number",
                            "id",
                            "name",
                            "mac",
                        ],
                    ),
                }
            )
            routers_from_call = routers_call.get("data", [])

            # Create router dictionary
            for record in routers_from_call:
                self.routers.setdefault(
                    record["id"],
                    record,
                )

            self.retrieve_router_location()
            offset_number += int(DEFAULT_API_DEVICE_LIMIT)

            if not routers_call.get("meta", {}).get("next"):
                next = False  # noqa: F841

        # Populate diffsync store.
        for record in self.routers.values():
            self.load_router(record)
