#from nautobot.core.testing import TestCase
from nautobot.dcim.models import Device
from typing_extensions import get_type_hints
from unittest import TestCase
from nautobot_ssot.contrib.dataclasses.attributes import StandardAttribute
from netaddr import EUI
from nautobot.dcim.models import Interface

class BasicModel:
    """Simple class used for getting annotation data in test casese."""

    name: str
    mac_address: str
    mtu: int
    mode: str
    enabled: bool
    description: str


class TestLoadStandardAttributeInterface(TestCase):

    def setUp(self):
        type_hints = get_type_hints(BasicModel, include_extras=True)
        self.device1 = Device(
            name="DEV-001",
        )

        self.interface = Interface(
            mac_address=EUI("AA-AA-AA-AA-AA-AA"),
            mtu=1500,
            mode="access",
            enabled=True,
            description=1535,  # for testing wrong return type
        )

        self.interface_mac = StandardAttribute(
            name="mac_address",
            annotation=type_hints["mac_address"]
        )

        self.interface_mtu = StandardAttribute(
            name="mtu",
            annotation=type_hints["mtu"]
        )

        self.interface_enabled = StandardAttribute(
            name="enabled",
            annotation=type_hints["enabled"]
        )

        self.interface_description = StandardAttribute(
            name="description",
            annotation=type_hints["description"]
        )

    def test_mac_address_field(self):
        self.assertEqual(
            self.interface_mac.load(self.interface),
            "AA-AA-AA-AA-AA-AA",
        )

    def test_integer_field(self):
        self.assertEqual(
            self.interface_mtu.load(self.interface),
            1500,
        )

    def test_boolean_field(self):
        self.assertTrue(self.interface_enabled.load(self.interface))

    def test_mismatched_type(self):
        with self.assertRaises(TypeError):
            self.interface_description.load(self.interface)
