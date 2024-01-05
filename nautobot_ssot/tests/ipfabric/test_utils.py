"""Tests for IPFabric utilities.utils."""
from django.test import SimpleTestCase

from nautobot_ssot.integrations.ipfabric.constants import DEFAULT_INTERFACE_TYPE
from nautobot_ssot.integrations.ipfabric.utilities import utils


class TestUtils(SimpleTestCase):  # pylint: disable=too-many-public-methods
    """Test IPFabric utilities.utils."""

    def test_virtual_interface(self):
        self.assertEqual("virtual", utils.convert_media_type("Virtual"))

    def test_bridge_interface(self):
        self.assertEqual("bridge", utils.convert_media_type("Bridge"))

    def test_lag_interface(self):
        self.assertEqual("lag", utils.convert_media_type("LAG"))

    def test_hunderd_meg_base_t_interface(self):
        self.assertEqual("100base-tx", utils.convert_media_type("100Base-T"))

    def test_hundred_meg_interface(self):
        self.assertEqual("100base-tx", utils.convert_media_type("100MegabitEthernet"))

    def test_gig_base_t_interface(self):
        self.assertEqual("1000base-t", utils.convert_media_type("1000BaseT"))
        self.assertEqual("1000base-t", utils.convert_media_type("10/100/1000BaseTX"))

    def test_rj45_uses_gig_base_t_interface(self):
        self.assertEqual("1000base-t", utils.convert_media_type("RJ45"))

    def test_gig_default_uses_base_t_interface(self):
        self.assertEqual("1000base-t", utils.convert_media_type("1GigThisUsesDefault"))

    def test_gig_sfp_interface(self):
        self.assertEqual("1000base-x-sfp", utils.convert_media_type("10/100/1000BaseTX SFP"))

    def test_gig_sfp_used_for_sfp_type_interface(self):
        self.assertEqual("1000base-x-sfp", utils.convert_media_type("1000BaseLX"))
        self.assertEqual("1000base-x-sfp", utils.convert_media_type("1000BaseSX"))
        self.assertEqual("1000base-x-sfp", utils.convert_media_type("1000BaseLR"))
        self.assertEqual("1000base-x-sfp", utils.convert_media_type("1000BaseSR"))

    def test_gig_gbic_interface(self):
        self.assertEqual("1000base-x-gbic", utils.convert_media_type("10/100/1000BaseTX GBIC"))

    def test_two_and_half_gig_base_t_interface(self):
        self.assertEqual("2.5gbase-t", utils.convert_media_type("100/1000/2.5GBaseTX"))

    def test_five_gig_base_t_interface(self):
        self.assertEqual("5gbase-t", utils.convert_media_type("100/1000/2.5G/5GBaseTX"))

    def test_ten_gig_xfp_interface(self):
        self.assertEqual("10gbase-x-xfp", utils.convert_media_type("10GBase XFP"))

    def test_ten_gig_x2_interface(self):
        self.assertEqual("10gbase-x-x2", utils.convert_media_type("10GBase X2"))

    def test_ten_gig_xenpak_interface(self):
        self.assertEqual("10gbase-x-xenpak", utils.convert_media_type("10GBase XENPAK"))

    def test_ten_gig_sfp_interface(self):
        self.assertEqual("10gbase-x-sfpp", utils.convert_media_type("10GBase SFP"))

    def test_ten_gig_default_uses_sfp_interface(self):
        self.assertEqual("10gbase-x-sfpp", utils.convert_media_type("10G"))

    def test_twenty_five_gig_sfp_interface(self):
        self.assertEqual("25gbase-x-sfp28", utils.convert_media_type("25G"))

    def test_forty_gig_sfp_interface(self):
        self.assertEqual("40gbase-x-qsfpp", utils.convert_media_type("40G"))

    def test_fifty_gig_sfp_interface(self):
        self.assertEqual("50gbase-x-sfp56", utils.convert_media_type("50G"))

    def test_hundred_gig_qsfp_interface(self):
        self.assertEqual("100gbase-x-qsfp28", utils.convert_media_type("100G QSFP"))

    def test_hundred_gig_default_uses_cfp_interface(self):
        self.assertEqual("100gbase-x-cfp", utils.convert_media_type("100G"))

    def test_two_hundred_gig_qsfp_interface(self):
        self.assertEqual("200gbase-x-qsfp56", utils.convert_media_type("200G QSFP"))

    def test_two_hundred_gig_default_uses_cfp_interface(self):
        self.assertEqual("200gbase-x-cfp2", utils.convert_media_type("200G"))

    def test_four_hundred_gig_qsfp_interface(self):
        self.assertEqual("400gbase-x-qsfp112", utils.convert_media_type("400G QSFP"))

    def test_four_hundred_gig_default_uses_osfp_interface(self):
        self.assertEqual("400gbase-x-osfp", utils.convert_media_type("400G"))

    def test_eight_hundred_gig_qsfp_interface(self):
        self.assertEqual("800gbase-x-qsfpdd", utils.convert_media_type("800G QSFP"))

    def test_eight_hundred_gig_default_uses_osfp_interface(self):
        self.assertEqual("800gbase-x-osfp", utils.convert_media_type("800G"))

    def test_unknown_interface_uses_default_interface(self):
        self.assertEqual(DEFAULT_INTERFACE_TYPE, utils.convert_media_type("ThisShouldGiveTheDefault"))
