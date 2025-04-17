"""Cradlepoint Adapter for DiffSync."""

from diffsync import Adapter

from nautobot_ssot.integrations.cradlepoint.constants import (
    DEFAULT_LOCATION_NAME,
    DEFAULT_MANUFACTURER,
)
from nautobot_ssot.integrations.cradlepoint.diffsync.adapters.base import BaseNautobotAdapter
from nautobot_ssot.integrations.cradlepoint.utilities.clients import CradlepointClient
from nautobot_ssot.integrations.cradlepoint.utilities.helpers import get_id_from_url

class CradlepointSourceAdapter(BaseNautobotAdapter, Adapter):
    """Cradlepoint Adapter."""

    def load_manufacturer(self):
        """Load manufacturer to diffsync store."""
        self.add(self.manufacturer(name=DEFAULT_MANUFACTURER))

    def __init__(self, *args, job=None, sync=None, client, config, **kwargs):
        """Initialize Cradlepoint Adapter."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.client: CradlepointClient = client
        self.config = config

    def load_product(self, data, **kwargs):
        """Load individual produt to diffsync store from API response."""
        self.add(self.device_type(
            model=data["name"],
            manufacturer__name=kwargs.pop("manufactuer", DEFAULT_MANUFACTURER),
            cpid=data["id"]
        ))

    def load_products(self):
        """Load Cradlepoint device types from `products` endpoint."""
        for product in self.client.load_from_paginated_list("products"):
            self.load_product(product)

    def load_status(self, data):
        """Get or load individual status object to diffsync store."""
        status, _ = self.get_or_instantiate(
            self.status,
            ids={"name": data["state"].capitalize()},
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
        return status

    def load_role(self, data):
        """Load device role from Cradlepoint into DiffSync store."""
        role, _ = self.get_or_instantiate(
            self.role,
            ids={"name": data["device_type"].capitalize()},
            attrs={
                "content_types": [
                    {"model": "device", "app_label": "dcim"},
                ]
            },
        )
        return role

    def _get_router_name(self, data):
        return data["name"]
    
    def _get_router_location_name(self, data):
        return DEFAULT_LOCATION_NAME

    def _get_router_location_parent_name(self, data):
        return None
        
    def load_router(self, data):
        """Load router into diffsync store."""
        status = self.load_status(data)
        role = self.load_role(data)

        # TODO: Handle instances where `full_product_name` doesn't match products endpoint
        product_id = get_id_from_url(data["product"])
        product = self.get(self.device_type, {"cpid": product_id})

        router = self.device(
            name=self._get_router_name(data),
            location__name=self._get_router_location_name(data),
            location__parent__name=self._get_router_location_parent_name(data),
            status__name=status.name,
            role__name=role.name,
            device_type__model=product.name,
            device_type__manufacturer__name=product.manufacturer__name,
            serial=str(data["serial_number"]),
            cpid=data["id"]
        )
        return router

    def load_routers(self):
        """Load routers from Cradlepoint to DiffSync store."""
        for router in self.client.load_from_paginated_list("routers"):
            self.load_router(router)

    def load(self):
        """Load diffsync objects from Cradlepoint API."""
        self.load_manufacturer()
        self.load_products()
        self.load_routers()
