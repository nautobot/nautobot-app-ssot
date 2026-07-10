"""Tests for IPFabric utilities.utils."""

import threading

from django.test import SimpleTestCase

from nautobot_ssot.integrations.ipfabric.constants import DEFAULT_INTERFACE_TYPE
from nautobot_ssot.integrations.ipfabric.utilities import utils
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache


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


class TestJobScopedCache(SimpleTestCase):
    """Test the `job_scoped_cache` decorator class."""

    def setUp(self):
        """Ensure no leaked state from other tests."""
        job_scoped_cache.clear_all()

    def test_cache_hit_returns_same_object(self):
        """Second call with same args returns the cached result (no second invocation)."""
        call_count = {"n": 0}

        @job_scoped_cache
        def make_obj(x):
            call_count["n"] += 1
            return [x]

        first = make_obj(1)
        second = make_obj(1)
        self.assertIs(first, second)
        self.assertEqual(call_count["n"], 1)

    def test_cache_miss_for_different_args(self):
        """Different args produce different cached entries; no false hits."""

        @job_scoped_cache
        def make_obj(x):
            return [x]

        a = make_obj(1)
        b = make_obj(2)
        self.assertIsNot(a, b)
        self.assertEqual(a, [1])
        self.assertEqual(b, [2])

    def test_cache_clear_resets_instance(self):
        """`cache_clear()` on one instance forces the next call to re-invoke the function."""
        call_count = {"n": 0}

        @job_scoped_cache
        def make_obj(x):
            call_count["n"] += 1
            return [x]

        first = make_obj(1)
        make_obj.cache_clear()
        second = make_obj(1)
        self.assertIsNot(first, second)
        self.assertEqual(call_count["n"], 2)

    def test_cache_info_reports_hits_misses_and_size(self):
        """`cache_info()` accurately reports hits, misses, and current size."""

        @job_scoped_cache
        def make_obj(x):
            return [x]

        make_obj(1)  # miss
        make_obj(1)  # hit
        make_obj(2)  # miss
        info = make_obj.cache_info()
        self.assertEqual(info.hits, 1)
        self.assertEqual(info.misses, 2)
        self.assertEqual(info.currsize, 2)
        self.assertIsNone(info.maxsize)

    def test_clear_all_resets_every_instance(self):
        """`clear_all()` resets caches on every registered instance."""

        @job_scoped_cache
        def first(x):
            return [x]

        @job_scoped_cache
        def second(x):
            return {x}

        first(1)
        second(2)
        self.assertEqual(first.cache_info().currsize, 1)
        self.assertEqual(second.cache_info().currsize, 1)

        job_scoped_cache.clear_all()

        self.assertEqual(first.cache_info().currsize, 0)
        self.assertEqual(second.cache_info().currsize, 0)

    def test_clear_group_only_clears_named_group(self):
        """`clear_group()` clears the named group's caches and leaves others intact."""

        @job_scoped_cache(group="alpha")
        def in_group(x):
            return [x]

        @job_scoped_cache
        def ungrouped(x):
            return [x]

        in_group(1)
        ungrouped(1)
        self.assertEqual(in_group.cache_info().currsize, 1)
        self.assertEqual(ungrouped.cache_info().currsize, 1)

        job_scoped_cache.clear_group("alpha")

        self.assertEqual(in_group.cache_info().currsize, 0, "group-cleared cache should be empty")
        self.assertEqual(ungrouped.cache_info().currsize, 1, "ungrouped cache must remain intact")

    def test_thread_local_isolation(self):
        """Each thread gets its own cache store; entries do not leak across threads."""

        @job_scoped_cache
        def make_obj(x):
            return [x]

        main_result = make_obj(1)
        other_thread_result = []

        def in_thread():
            other_thread_result.append(make_obj(1))

        worker = threading.Thread(target=in_thread)
        worker.start()
        worker.join()

        self.assertEqual(len(other_thread_result), 1)
        # Different threads -> separate cache stores -> separate fresh objects with equal values.
        self.assertIsNot(main_result, other_thread_result[0])
        self.assertEqual(main_result, other_thread_result[0])
