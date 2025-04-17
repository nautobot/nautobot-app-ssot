"""Test Cradlepoint Jobs."""

from unittest.mock import Mock

from django.test import TestCase

from nautobot_ssot.integrations.cradlepoint.diffsync.adapters.cradlepoint import CradlepointSourceAdapter


class TestLoadProducts(TestCase):
    """Test the Cradlepoint Sync job."""

    @classmethod
    def setUp(cls):
        cls.adapter = CradlepointSourceAdapter(
            job=Mock(),
            client=Mock(),
            config=Mock(),
            starting_offset=0,
        )

        cls.data = [
            {"device_type":"router","id":32,"name":"Alpha","series":32,"resource_url":"https://www.cradlepointcm.com/api/v2/products/32/"},
            {"device_type":"router","id":137,"name":"Bamity","series":74,"resource_url":"https://www.cradlepointcm.com/api/v2/products/74/"},
            {"device_type":"router","id":141,"name":"Regrant","series":10,"resource_url":"https://www.cradlepointcm.com/api/v2/products/10/"},
            {"device_type":"router","id":112,"name":"Fix San","series":13,"resource_url":"https://www.cradlepointcm.com/api/v2/products/13/"},
            {"device_type":"router","id":44,"name":"Home Ing","series":26,"resource_url":"https://www.cradlepointcm.com/api/v2/products/26/"},
        ]

    def test_load_product(self):
        self.adapter._load_product(self.data[0])
        product = self.adapter.get(
            "device_type",
            {
                "model": "Alpha",
                "manufacturer__name": "Cradlepoint, Inc.",
            }
        )
        self.assertTrue(product.model == "Alpha")