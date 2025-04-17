"""Cradlepoint Adapter for DiffSync."""

from diffsync import Adapter

from nautobot_ssot.integrations.cradlepoint.constants import (
    DEFAULT_LOCATION,
    DEFAULT_MANUFACTURER,
)
from nautobot_ssot.integrations.cradlepoint.diffsync.adapters.base import BaseNautobotAdapter
from nautobot_ssot.integrations.cradlepoint.utilities.clients import CradlepointClient


class CradlepointSourceAdapter(BaseNautobotAdapter, Adapter):
    """Cradlepoint Adapter."""

    def __init__(self, *args, job=None, sync=None, client, config, **kwargs):
        """Initialize Cradlepoint Adapter."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.client: CradlepointClient = client
        self.config = config

    def _load_product(self, data, **kwargs):
        """Load individual produt to diffsync store from API response."""
        self.add(self.device_type(
            model=data["name"],
            manufacturer__name=kwargs.pop("manufactuer", DEFAULT_MANUFACTURER),
            cpid=data["id"]
        ))

    def load_products(self):
        """Load Cradlepoint device types from `products` endpoint"""
        products = self.client.load_from_paginated_list("get_products")
        while products:
            for product in products:
                self._load_product(product)
            products = self.client.load_from_paginated_list("products")

    def load_manufacturer(self):
        """Load manufacturer to diffsync store."""
        self.add(self.manufacturer(name=DEFAULT_MANUFACTURER))

    def load(self):
        """Load diffsync objects from Cradlepoint API."""
        self.load_manufacturer()
        self.load_products()
