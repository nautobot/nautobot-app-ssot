"""Tests for what the loaders report when IP Fabric describes one object twice.

DiffSync keys a model by its identity, so a second record under the same identity cannot be added.
Each loader catches that and reports it rather than letting the load end, which is the only way an
operator learns the appliance is describing one object two ways.
"""

import copy
import unittest.mock
from collections import defaultdict

from ipfabric.models.device import Device
from nautobot.apps.testing import TestCase

from nautobot_ssot.tests.ipfabric.job_log import job_log_text, job_logger
from nautobot_ssot.tests.ipfabric.test_ipfabric_adapter import (
    DEVICE_INVENTORY_FIXTURE,
    SITE_FIXTURE,
    VLAN_FIXTURE,
    build_adapter,
    mock_ipfabric_client,
)


class TestDuplicatesIPFabricReports(TestCase):
    """One record per object is the assumption; a second is reported and not loaded."""

    def loaded_with(self, **tables):
        """Load an adapter whose named tables serve the given rows, and return its warnings."""
        client = mock_ipfabric_client()
        for name, rows in tables.items():
            if name == "sites":
                client.inventory.sites.all.return_value = rows
            elif name == "vlans":
                client.fetch_all = unittest.mock.MagicMock(
                    side_effect=lambda table, rows=rows: rows if table == "tables/vlan/site-summary" else ""
                )
        logger = job_logger()
        build_adapter(client=client, logger=logger)
        return job_log_text(logger, "warning")

    def test_a_location_reported_twice_is_reported_once(self):
        warnings = self.loaded_with(sites=SITE_FIXTURE + [copy.deepcopy(SITE_FIXTURE[0])])

        self.assertIn("Duplicate Location discovered", warnings)

    def test_a_vlan_reported_twice_at_one_location_is_reported(self):
        warnings = self.loaded_with(vlans=VLAN_FIXTURE + [copy.deepcopy(VLAN_FIXTURE[0])])

        self.assertIn("Duplicate VLAN discovered", warnings)

    def test_a_vlan_whose_name_is_too_long_is_reported(self):
        """Nautobot holds 255 characters, so a longer name is a VLAN the sync cannot write."""
        long_named = copy.deepcopy(VLAN_FIXTURE[0])
        long_named["vlanName"] = "v" * 300

        warnings = self.loaded_with(vlans=[long_named])

        self.assertIn("due to character limit exceeding", warnings)

    def test_a_device_reported_twice_is_reported(self):
        client = mock_ipfabric_client()
        for site, devices in list(client.devices.by_site.items()):  # pylint: disable=no-member
            client.devices.by_site[site] = (  # pylint: disable=no-member
                devices + [copy.deepcopy(devices[0])] if devices else devices
            )
        logger = job_logger()

        build_adapter(client=client, logger=logger)

        self.assertIn("Duplicate Device discovered", job_log_text(logger, "warning"))


class TestDevicesWithNoUsableSerial(TestCase):
    """A serial IP Fabric does not report, or reports longer than Nautobot holds, is counted."""

    def loaded_without_serials(self, serial):
        """Load an adapter whose Devices all carry the given serial, and return its warnings."""
        client = mock_ipfabric_client()
        client.devices.by_site = defaultdict(list)
        for record in DEVICE_INVENTORY_FIXTURE:
            record = dict(record, sn=serial)
            client.devices.by_site[record["siteName"]].append(Device(**record))  # pylint: disable=no-member
        logger = job_logger()
        adapter = build_adapter(client=client, logger=logger)
        return adapter, job_log_text(logger, "warning")

    def test_a_serial_longer_than_nautobot_holds_is_counted_not_named(self):
        adapter, warnings = self.loaded_without_serials("s" * 300)

        self.assertTrue(adapter.devices_without_a_serial, "The Devices were expected to lose their serials.")
        self.assertIn("No serial number recorded for", warnings)
        self.assertIn("Devices", warnings)


class TestSelfLinkingAndPseudoInterfaceSummaries(TestCase):
    """The two counts the loader reports once rather than per Device or per reported link."""

    def test_a_link_from_an_interface_to_itself_is_counted_per_endpoint(self):
        client = mock_ipfabric_client()
        matrix = client.technology.interfaces.connectivity_matrix.all.return_value
        self_link = copy.deepcopy(matrix[0])
        self_link["remoteHost"] = self_link["localHost"]
        self_link["remoteInt"] = self_link["localInt"]
        client.technology.interfaces.connectivity_matrix.all.return_value = matrix + [
            self_link,
            copy.deepcopy(self_link),
        ]
        logger = job_logger()

        adapter = build_adapter(client=client, logger=logger, sync_cables=True)

        self.assertTrue(adapter.self_linking_endpoints, "The matrix was expected to carry a self link.")
        self.assertIn("to itself", job_log_text(logger, "warning"))

    def test_the_pseudo_management_interfaces_are_counted(self):
        logger = job_logger()

        adapter = build_adapter(logger=logger)

        self.assertTrue(adapter.pseudo_management_interfaces, "The fixtures carry NAT reached Devices.")
        self.assertIn("Fabricated a pseudo management Interface for", job_log_text(logger, "info"))
