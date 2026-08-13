"""Unit tests for the LibreNMS network-driver resolution helpers."""

from unittest.mock import patch

from django.test import override_settings
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Platform as ORMPlatform
from netutils.lib_mapper import MAIN_LIB_MAPPER

from nautobot_ssot.integrations.librenms.constants import LIBRENMS_OS_TO_NETWORK_DRIVER
from nautobot_ssot.integrations.librenms.utils.nautobot import (
    clear_network_driver_caches,
    known_network_drivers,
    librenms_os_to_network_driver,
    platform_to_network_driver,
)

# `applogic_procera` is not a netutils driver, but LIBRENMS_LIB_MAPPER has emitted it since the
# integration was written, so the mapper keeps it for backwards compatibility.
NON_NETUTILS_DRIVERS = {"applogic_procera"}

PLUGIN_CFG_PATH = "nautobot_ssot.integrations.librenms.constants.PLUGIN_CFG"


class TestLibrenmsOsToNetworkDriver(TestCase):
    """Test `librenms_os_to_network_driver()`."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Drop cached lookups so each test sees the settings it sets."""
        super().setUp()
        clear_network_driver_caches()
        self.addCleanup(clear_network_driver_caches)

    def test_mapped_os_values(self):
        """LibreNMS OS values in the bundled mapper resolve to their driver."""
        for librenms_os, expected in [
            ("ios", "cisco_ios"),
            ("iosxe", "cisco_xe"),
            ("nxos", "cisco_nxos"),
            ("iosxr", "cisco_xr"),
            ("junos", "juniper_junos"),
            ("asa", "cisco_asa"),
            ("routeros", "mikrotik_routeros"),
            ("unifi", "ubiquiti_unifiswitch"),
            ("fortios", "fortinet"),
            ("procera", "applogic_procera"),
        ]:
            with self.subTest(librenms_os=librenms_os):
                self.assertEqual(librenms_os_to_network_driver(librenms_os), expected)

    def test_unmapped_os_that_is_already_a_driver_passes_through(self):
        """An OS value that is itself a recognized driver is used as-is."""
        for librenms_os in ["arista_eos", "linux", "windows"]:
            with self.subTest(librenms_os=librenms_os):
                self.assertEqual(librenms_os_to_network_driver(librenms_os), librenms_os)

    def test_unresolvable_values_return_empty_string(self):
        """Never invent a driver: unknown, empty and whitespace-only values resolve to ""."""
        for librenms_os in ["definitely-not-an-os", "", "   ", None]:
            with self.subTest(librenms_os=librenms_os):
                self.assertEqual(librenms_os_to_network_driver(librenms_os), "")

    def test_deliberately_unmapped_ambiguous_values(self):
        """Ambiguous OS values are left unmapped rather than guessed."""
        for librenms_os in ["dnos", "asyncos", "junose", "cumulus", "opnsense", "vmwareesxi"]:
            with self.subTest(librenms_os=librenms_os):
                self.assertEqual(librenms_os_to_network_driver(librenms_os), "")

    def test_case_and_whitespace_insensitive(self):
        """Keys are stripped and lowercased before lookup."""
        for librenms_os in ["IOS", " ios ", "Ios", "\tIOS\n"]:
            with self.subTest(librenms_os=librenms_os):
                self.assertEqual(librenms_os_to_network_driver(librenms_os), "cisco_ios")

    def test_setting_overrides_bundled_mapping(self):
        """`librenms_network_driver_map` takes precedence over the bundled mapper."""
        with patch.dict(PLUGIN_CFG_PATH, {"librenms_network_driver_map": {"iosxe": "cisco_ios"}}):
            clear_network_driver_caches()
            self.assertEqual(librenms_os_to_network_driver("iosxe"), "cisco_ios")

    def test_setting_can_suppress_bundled_mapping(self):
        """An explicit empty value means "deliberately no driver"."""
        with patch.dict(PLUGIN_CFG_PATH, {"librenms_network_driver_map": {"ios": ""}}):
            clear_network_driver_caches()
            self.assertEqual(librenms_os_to_network_driver("ios"), "")

    def test_setting_keys_are_case_insensitive(self):
        """Override keys are normalized the same way as the lookup key."""
        with patch.dict(PLUGIN_CFG_PATH, {"librenms_network_driver_map": {" IOSXE ": "cisco_ios"}}):
            clear_network_driver_caches()
            self.assertEqual(librenms_os_to_network_driver("iosxe"), "cisco_ios")

    def test_setting_can_map_an_ambiguous_value(self):
        """The documented escape hatch for the intentionally unmapped values."""
        with patch.dict(PLUGIN_CFG_PATH, {"librenms_network_driver_map": {"dnos": "dell_os10"}}):
            clear_network_driver_caches()
            self.assertEqual(librenms_os_to_network_driver("dnos"), "dell_os10")

    @override_settings(NETWORK_DRIVERS={"netmiko": {"acme_widgetos": "acme_widgetos"}})
    def test_operator_network_drivers_setting_is_respected(self):
        """A driver added via Nautobot's NETWORK_DRIVERS setting passes through."""
        clear_network_driver_caches()
        self.assertIn("acme_widgetos", known_network_drivers())
        self.assertEqual(librenms_os_to_network_driver("acme_widgetos"), "acme_widgetos")

    def test_known_network_drivers_includes_netutils_only_drivers(self):
        """The MAIN_LIB_MAPPER union recovers drivers absent from NAME_TO_ALL_LIB_MAPPER."""
        for driver in ["f5_tmsh", "f5_ltm", "f5_linux", "ruckus_smartzone"]:
            with self.subTest(driver=driver):
                self.assertIn(driver, known_network_drivers())


class TestLibrenmsOsToNetworkDriverMapperIntegrity(TestCase):
    """Guard rails on LIBRENMS_OS_TO_NETWORK_DRIVER itself, so future additions stay valid."""

    databases = ("default", "job_logs")

    def setUp(self):
        super().setUp()
        clear_network_driver_caches()
        self.addCleanup(clear_network_driver_caches)

    def test_every_value_is_a_known_driver(self):
        """Every mapped driver must be resolvable, so Platform.network_driver_mappings works."""
        unknown = {driver for driver in LIBRENMS_OS_TO_NETWORK_DRIVER.values() if driver not in known_network_drivers()}
        self.assertEqual(unknown - NON_NETUTILS_DRIVERS, set())

    def test_every_value_except_the_allowlist_is_in_netutils(self):
        """Catches typos in newly added drivers."""
        unknown = {driver for driver in LIBRENMS_OS_TO_NETWORK_DRIVER.values() if driver not in MAIN_LIB_MAPPER}
        self.assertEqual(unknown, NON_NETUTILS_DRIVERS)

    def test_resolution_is_idempotent(self):
        """f(f(os)) == f(os), since consolidated mode re-resolves driver-space values."""
        for librenms_os in LIBRENMS_OS_TO_NETWORK_DRIVER:
            with self.subTest(librenms_os=librenms_os):
                once = librenms_os_to_network_driver(librenms_os)
                self.assertEqual(librenms_os_to_network_driver(once), once)

    def test_keys_are_normalized(self):
        """Keys must already be stripped and lowercased, or they can never be hit."""
        for key in LIBRENMS_OS_TO_NETWORK_DRIVER:
            with self.subTest(key=key):
                self.assertEqual(key, key.strip().lower())


class TestPlatformToNetworkDriver(TestCase):
    """Test `platform_to_network_driver()`, one case per row of the documented adoption table."""

    databases = ("default", "job_logs")

    def setUp(self):
        super().setUp()
        clear_network_driver_caches()
        self.addCleanup(clear_network_driver_caches)

    def test_onboarding_style_platform(self):
        """device-onboarding writes name and driver both as the netmiko driver."""
        platform = ORMPlatform(name="cisco_ios", network_driver="cisco_ios")
        self.assertEqual(platform_to_network_driver(platform), "cisco_ios")

    def test_legacy_fqcn_in_both_fields(self):
        """The shape this integration used to create; resolved via the FQCN alias step."""
        platform = ORMPlatform(name="cisco.ios.ios", network_driver="cisco.ios.ios")
        self.assertEqual(platform_to_network_driver(platform), "cisco_ios")

    def test_dna_center_style_platform(self):
        """FQCN name alongside a correct driver; the driver wins."""
        platform = ORMPlatform(name="cisco.ios.ios", network_driver="cisco_ios")
        self.assertEqual(platform_to_network_driver(platform), "cisco_ios")

    def test_legacy_raw_os_name(self):
        """A row named after the raw LibreNMS OS resolves through the OS mapper."""
        platform = ORMPlatform(name="fortios", network_driver="fortios")
        self.assertEqual(platform_to_network_driver(platform), "fortinet")

    def test_unmapped_os_keeps_its_name(self):
        """An intentionally unmapped OS keeps its identity instead of being guessed at."""
        platform = ORMPlatform(name="opnsense", network_driver="")
        self.assertEqual(platform_to_network_driver(platform), "opnsense")

    def test_hand_made_platform_keeps_its_name(self):
        """A hand-named platform with no driver falls through to its name."""
        platform = ORMPlatform(name="Cisco IOS", network_driver="")
        self.assertEqual(platform_to_network_driver(platform), "Cisco IOS")

    def test_fqcn_only_in_name(self):
        """FQCN name with a blank driver still resolves via the alias step."""
        platform = ORMPlatform(name="junipernetworks.junos.junos", network_driver="")
        self.assertEqual(platform_to_network_driver(platform), "juniper_junos")

    def test_none_platform(self):
        """A device with no platform resolves to ""."""
        self.assertEqual(platform_to_network_driver(None), "")

    def test_whitespace_is_stripped(self):
        """Stored values are stripped before resolution."""
        platform = ORMPlatform(name="  cisco_ios  ", network_driver="  cisco_ios  ")
        self.assertEqual(platform_to_network_driver(platform), "cisco_ios")

    def test_iosxe_row_and_ios_row_are_distinct(self):
        """cisco_xe must not canonicalize onto cisco_ios; the split depends on it."""
        self.assertEqual(
            platform_to_network_driver(ORMPlatform(name="cisco_xe", network_driver="cisco_xe")), "cisco_xe"
        )
        self.assertEqual(librenms_os_to_network_driver("iosxe"), "cisco_xe")
        self.assertNotEqual(librenms_os_to_network_driver("iosxe"), librenms_os_to_network_driver("ios"))
