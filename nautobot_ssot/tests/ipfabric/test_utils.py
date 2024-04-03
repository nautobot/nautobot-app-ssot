"""Tests for IPFabric utilities.utils."""

from django.test import SimpleTestCase

from nautobot_ssot.integrations.ipfabric.constants import DEFAULT_INTERFACE_TYPE
from nautobot_ssot.integrations.ipfabric.utilities import utils


class TestUtils(SimpleTestCase):  # pylint: disable=too-many-public-methods
    """Test IPFabric utilities.utils."""

    def test_virtual_interface(self):
        self.assertEqual("virtual", utils.convert_media_type("Virtual", "VLAN1"))

    def test_bridge_interface(self):
        self.assertEqual("bridge", utils.convert_media_type("Bridge", "Bridge0"))

    def test_lag_interface(self):
        self.assertEqual("lag", utils.convert_media_type("LAG", "Po1"))

    def test_hunderd_meg_base_t_interface(self):
        self.assertEqual("100base-tx", utils.convert_media_type("100Base-T", "Fa1"))

    def test_hundred_meg_interface(self):
        self.assertEqual("100base-tx", utils.convert_media_type("100MegabitEthernet", "Fa1"))

    def test_gig_base_t_interface(self):
        self.assertEqual("1000base-t", utils.convert_media_type("1000BaseT", "Gi1"))
        self.assertEqual("1000base-t", utils.convert_media_type("10/100/1000BaseTX", "Gi1"))

    def test_rj45_uses_gig_base_t_interface(self):
        self.assertEqual("1000base-t", utils.convert_media_type("RJ45", "Gi1"))

    def test_gig_default_uses_base_t_interface(self):
        self.assertEqual("1000base-t", utils.convert_media_type("1GigThisUsesDefault", "Gi1"))

    def test_gig_sfp_interface(self):
        self.assertEqual("1000base-x-sfp", utils.convert_media_type("10/100/1000BaseTX SFP", "Gi1"))

    def test_gig_sfp_used_for_sfp_type_interface(self):
        self.assertEqual("1000base-x-sfp", utils.convert_media_type("1000BaseLX", "Gi1"))
        self.assertEqual("1000base-x-sfp", utils.convert_media_type("1000BaseSX", "Gi1"))
        self.assertEqual("1000base-x-sfp", utils.convert_media_type("1000BaseLR", "Gi1"))
        self.assertEqual("1000base-x-sfp", utils.convert_media_type("1000BaseSR", "Gi1"))

    def test_gig_gbic_interface(self):
        self.assertEqual("1000base-x-gbic", utils.convert_media_type("10/100/1000BaseTX GBIC", "Gi1"))

    def test_two_and_half_gig_base_t_interface(self):
        self.assertEqual("2.5gbase-t", utils.convert_media_type("100/1000/2.5GBaseTX", "TwoGi1"))

    def test_five_gig_base_t_interface(self):
        self.assertEqual("5gbase-t", utils.convert_media_type("100/1000/2.5G/5GBaseTX", "FiveGi1"))

    def test_ten_gig_xfp_interface(self):
        self.assertEqual("10gbase-x-xfp", utils.convert_media_type("10GBase XFP", "TenGi1"))

    def test_ten_gig_x2_interface(self):
        self.assertEqual("10gbase-x-x2", utils.convert_media_type("10GBase X2", "TenGi1"))

    def test_ten_gig_xenpak_interface(self):
        self.assertEqual("10gbase-x-xenpak", utils.convert_media_type("10GBase XENPAK", "TenGi1"))

    def test_ten_gig_sfp_interface(self):
        self.assertEqual("10gbase-x-sfpp", utils.convert_media_type("10GBase SFP", "TenGi1"))

    def test_ten_gig_default_uses_sfp_interface(self):
        self.assertEqual("10gbase-x-sfpp", utils.convert_media_type("10G", "TenGi1"))

    def test_twenty_five_gig_sfp_interface(self):
        self.assertEqual("25gbase-x-sfp28", utils.convert_media_type("25G", "TweGi1"))

    def test_forty_gig_sfp_interface(self):
        self.assertEqual("40gbase-x-qsfpp", utils.convert_media_type("40G", "FoGi1"))

    def test_fifty_gig_sfp_interface(self):
        self.assertEqual("50gbase-x-sfp56", utils.convert_media_type("50G", "FiGi1"))

    def test_hundred_gig_qsfp_interface(self):
        self.assertEqual("100gbase-x-qsfp28", utils.convert_media_type("100G QSFP", "HunGi1"))

    def test_hundred_gig_default_uses_cfp_interface(self):
        self.assertEqual("100gbase-x-cfp", utils.convert_media_type("100G", "HunGi1"))

    def test_two_hundred_gig_qsfp_interface(self):
        self.assertEqual("200gbase-x-qsfp56", utils.convert_media_type("200G QSFP", "TwoHunGi1"))

    def test_two_hundred_gig_default_uses_cfp_interface(self):
        self.assertEqual("200gbase-x-cfp2", utils.convert_media_type("200G", "TwoHunGi1"))

    def test_four_hundred_gig_qsfp_interface(self):
        self.assertEqual("400gbase-x-qsfp112", utils.convert_media_type("400G QSFP", "FoHunGi1"))

    def test_four_hundred_gig_default_uses_osfp_interface(self):
        self.assertEqual("400gbase-x-osfp", utils.convert_media_type("400G", "FoHunGi1"))

    def test_eight_hundred_gig_qsfp_interface(self):
        self.assertEqual("800gbase-x-qsfpdd", utils.convert_media_type("800G QSFP", "EiHunGi1"))

    def test_eight_hundred_gig_default_uses_osfp_interface(self):
        self.assertEqual("800gbase-x-osfp", utils.convert_media_type("800G", "EiHunGi1"))

    def test_unknown_interface_uses_default_interface(self):
        self.assertEqual(DEFAULT_INTERFACE_TYPE, utils.convert_media_type("ThisShouldGiveTheDefault", ""))

    def test_interface_name_lag(self):
        self.assertEqual("lag", utils.convert_media_type("", "Po1"))
        self.assertEqual("lag", utils.convert_media_type("", "Port-channel1"))

    def test_interface_name_vlan(self):
        self.assertEqual("virtual", utils.convert_media_type("", "Vlan1"))
        self.assertEqual("virtual", utils.convert_media_type("", "Vl1"))

    def test_interface_name_loopback(self):
        self.assertEqual("virtual", utils.convert_media_type("", "Loopback1"))
        self.assertEqual("virtual", utils.convert_media_type("", "Lo1"))

    def test_interface_name_tunnel(self):
        self.assertEqual("virtual", utils.convert_media_type("", "Tu1"))
        self.assertEqual("virtual", utils.convert_media_type("", "Tunnel1"))

    def test_interface_name_vxlan(self):
        self.assertEqual("virtual", utils.convert_media_type("", "Vxlan1"))
        self.assertEqual("virtual", utils.convert_media_type("", "Vx1"))

    def test_interface_name_fastethernet(self):
        self.assertEqual("100base-tx", utils.convert_media_type("", "FastEthernet1"))
        self.assertEqual("100base-tx", utils.convert_media_type("", "Fa1"))

    def test_interface_name_gigethernet(self):
        self.assertEqual("1000base-t", utils.convert_media_type("", "GigabitEthernet1"))
        self.assertEqual("1000base-t", utils.convert_media_type("", "Gi1"))

    def test_interface_name_tengigethernet(self):
        self.assertEqual("10gbase-x-sfpp", utils.convert_media_type("", "TenGigabitEthernet1"))
        self.assertEqual("10gbase-x-sfpp", utils.convert_media_type("", "Te1"))

    def test_interface_name_twentyfivegigethernet(self):
        self.assertEqual("25gbase-x-sfp28", utils.convert_media_type("", "TwentyFiveGigabitEthernet1"))

    def test_interface_name_fortygigethernet(self):
        self.assertEqual("40gbase-x-qsfpp", utils.convert_media_type("", "FortyGigabitEthernet1"))
        self.assertEqual("40gbase-x-qsfpp", utils.convert_media_type("", "Fo1"))

    def test_interface_name_fiftygigethernet(self):
        self.assertEqual("50gbase-x-sfp56", utils.convert_media_type("", "FiftyGigabitEthernet1"))
        self.assertEqual("50gbase-x-sfp56", utils.convert_media_type("", "Fi1"))

    def test_interface_name_hundredgigethernet(self):
        self.assertEqual("100gbase-x-qsfp28", utils.convert_media_type("", "HundredGigabitEthernet1"))
        self.assertEqual("100gbase-x-qsfp28", utils.convert_media_type("", "Hu1"))

    def test_interface_name_twohundredgigethernet(self):
        self.assertEqual("200gbase-x-qsfp56", utils.convert_media_type("", "TwoHundredGigabitEthernet1"))
