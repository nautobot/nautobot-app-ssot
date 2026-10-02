"""Unit tests for the ServiceNowDiffSync adapter class."""

from collections import defaultdict
from itertools import islice
from unittest.mock import MagicMock

import requests
from nautobot.apps.testing import TestCase
from nautobot.extras.models import JobResult

from nautobot_ssot.integrations.servicenow.diffsync import models
from nautobot_ssot.integrations.servicenow.diffsync.adapter_servicenow import ServiceNowDiffSync
from nautobot_ssot.integrations.servicenow.exceptions import AmbiguousReferenceError
from nautobot_ssot.integrations.servicenow.jobs import ServiceNowDataTarget
from nautobot_ssot.integrations.servicenow.servicenow import ServiceNowClient
from nautobot_ssot.integrations.servicenow.third_party.pysnow.exceptions import MultipleResults


class MockServiceNowClient:
    """Mock version of the ServiceNowClient class using canned data."""

    def __init__(self):
        self.query_params = defaultdict(list)
        self.field_params = defaultdict(list)

    def get_by_sys_id(self, table, sys_id):  # pylint: disable=unused-argument
        """Get a record with a given sys_id from a given table."""
        return None

    def all_table_entries(self, table, query={}, fields=None, limit=10000):  # pylint: disable=dangerous-default-value,unused-argument
        """Iterator over all records in a given table."""

        self.query_params[table].append(query)
        self.field_params[table].append(fields)

        if table == "cmn_location":
            yield from [
                {
                    "country": "",
                    "parent": "",
                    "city": "",
                    "latitude": "",
                    "sys_updated_on": "2021-07-12 20:19:23",
                    "sys_id": "7200ad3d2f153010fe08351ef699b69a",
                    "sys_updated_by": "admin",
                    "stock_room": "false",
                    "street": "",
                    "sys_created_on": "2021-07-12 20:19:23",
                    "contact": "",
                    "phone_territory": "",
                    "company": "",
                    "lat_long_error": "",
                    "state": "",
                    "sys_created_by": "admin",
                    "longitude": "",
                    "zip": "",
                    "sys_mod_count": "0",
                    "sys_tags": "",
                    "time_zone": "",
                    "full_name": "Asia",
                    "fax_phone": "",
                    "phone": "",
                    "name": "Asia",
                    "coordinates_retrieved_on": "",
                },
                {
                    "country": "Japan",
                    "parent": "7200ad3d2f153010fe08351ef699b69a",
                    "city": "Japan",
                    "latitude": "36.204824",
                    "sys_updated_on": "2021-07-12 20:19:30",
                    "sys_id": "0d9561b437d0200044e0bfc8bcbe5d32",
                    "sys_updated_by": "admin",
                    "stock_room": "false",
                    "street": "",
                    "sys_created_on": "2012-02-17 17:57:16",
                    "contact": "",
                    "phone_territory": "dcb7e002eb1201007128a5fc5206fe64",
                    "company": "81fd65ecac1d55eb42a426568fc87a63",
                    "lat_long_error": "",
                    "state": "",
                    "sys_created_by": "admin",
                    "longitude": "138.252924",
                    "zip": "",
                    "sys_mod_count": "1",
                    "sys_tags": "",
                    "time_zone": "",
                    "full_name": "Asia/Japan",
                    "fax_phone": "",
                    "phone": "",
                    "name": "Japan",
                    "coordinates_retrieved_on": "",
                },
                {
                    "country": "Japan",
                    "parent": "0d9561b437d0200044e0bfc8bcbe5d32",
                    "city": "Tokyo",
                    "latitude": "35.6894875",
                    "sys_updated_on": "2012-02-19 17:11:11",
                    "sys_id": "821c169bac1d55eb68ede6e36aa35112",
                    "sys_updated_by": "admin",
                    "stock_room": "false",
                    "street": "",
                    "sys_created_on": "2010-11-25 08:17:47",
                    "contact": "",
                    "phone_territory": "",
                    "company": "81fd65ecac1d55eb42a426568fc87a63",
                    "lat_long_error": "",
                    "state": "",
                    "sys_created_by": "dariusz.maint",
                    "longitude": "139.6917064",
                    "zip": "",
                    "sys_mod_count": "3",
                    "sys_tags": "",
                    "time_zone": "",
                    "full_name": "Asia/Japan/Tokyo",
                    "fax_phone": "",
                    "phone": "",
                    "name": "Tokyo",
                    "coordinates_retrieved_on": "",
                },
                {
                    "country": "China",
                    "parent": "7200ad3d2f153010fe08351ef699b69a",
                    "city": "China",
                    "latitude": "35.86166",
                    "sys_updated_on": "2021-07-12 20:19:26",
                    "sys_id": "8195ad7437d0200044e0bfc8bcbe5d8f",
                    "sys_updated_by": "admin",
                    "stock_room": "false",
                    "street": "",
                    "sys_created_on": "2012-02-17 17:57:15",
                    "contact": "",
                    "phone_territory": "4cb7e002eb1201007128a5fc5206fe0b",
                    "company": "81fdf9ebac1d55eb4cb89f136a082555",
                    "lat_long_error": "",
                    "state": "",
                    "sys_created_by": "admin",
                    "longitude": "104.195397",
                    "zip": "",
                    "sys_mod_count": "1",
                    "sys_tags": "",
                    "time_zone": "",
                    "full_name": "Asia/China",
                    "fax_phone": "",
                    "phone": "",
                    "name": "China",
                    "coordinates_retrieved_on": "",
                },
                {
                    "country": "",
                    "parent": "8195ad7437d0200044e0bfc8bcbe5d8f",
                    "city": "",
                    "latitude": "",
                    "sys_updated_on": "2021-07-14 21:39:47",
                    "sys_id": "84a54c662f513010fe08351ef699b624",
                    "sys_updated_by": "admin",
                    "stock_room": "false",
                    "street": "",
                    "sys_created_on": "2021-07-14 21:39:47",
                    "contact": "",
                    "phone_territory": "",
                    "company": "",
                    "lat_long_error": "",
                    "state": "",
                    "sys_created_by": "admin",
                    "longitude": "",
                    "zip": "",
                    "sys_mod_count": "0",
                    "sys_tags": "",
                    "time_zone": "",
                    "full_name": "Asia/China/hkg",
                    "fax_phone": "",
                    "phone": "",
                    "name": "hkg",
                    "coordinates_retrieved_on": "",
                },
            ]
        elif table == "cmdb_ci_ip_switch":
            if query and query["location"] == "84a54c662f513010fe08351ef699b624":  # hkg
                yield from [
                    {
                        "attested_date": "",
                        "can_switch": "false",
                        "stack": "false",
                        "operational_status": "1",
                        "cpu_manufacturer": "",
                        "sys_updated_on": "2021-07-14 21:45:09",
                        "discovery_source": "",
                        "first_discovered": "",
                        "due_in": "",
                        "can_partitionvlans": "false",
                        "gl_account": "",
                        "invoice_number": "",
                        "sys_created_by": "admin",
                        "ram": "",
                        "warranty_expiration": "",
                        "cpu_speed": "",
                        "owned_by": "",
                        "checked_out": "",
                        "firmware_manufacturer": "",
                        "disk_space": "",
                        "sys_domain_path": "/",
                        "discovery_proto_id": "",
                        "maintenance_schedule": "",
                        "cost_center": "",
                        "attested_by": "",
                        "dns_domain": "",
                        "assigned": "",
                        "life_cycle_stage": "",
                        "purchase_date": "",
                        "short_description": "",
                        "managed_by": "",
                        "range": "",
                        "firmware_version": "",
                        "can_print": "false",
                        "last_discovered": "",
                        "ports": "",
                        "sys_class_name": "cmdb_ci_ip_switch",
                        "cpu_count": "1",
                        "manufacturer": "",
                        "life_cycle_stage_status": "",
                        "vendor": "",
                        "can_route": "false",
                        "model_number": "",
                        "assigned_to": "",
                        "start_date": "",
                        "bandwidth": "",
                        "serial_number": "",
                        "support_group": "",
                        "correlation_id": "",
                        "unverified": "false",
                        "attributes": "",
                        "asset": "a2d60ce62f513010fe08351ef699b618",
                        "skip_sync": "false",
                        "device_type": "",
                        "attestation_score": "",
                        "sys_updated_by": "admin",
                        "sys_created_on": "2021-07-14 21:40:27",
                        "cpu_type": "",
                        "sys_domain": "global",
                        "install_date": "",
                        "asset_tag": "",
                        "hardware_substatus": "",
                        "fqdn": "",
                        "stack_mode": "",
                        "change_control": "",
                        "internet_facing": "true",
                        "physical_interface_count": "",
                        "delivery_date": "",
                        "hardware_status": "installed",
                        "channels": "",
                        "install_status": "1",
                        "supported_by": "",
                        "name": "hkg-leaf-01",
                        "subcategory": "IP",
                        "default_gateway": "",
                        "assignment_group": "",
                        "managed_by_group": "",
                        "can_hub": "false",
                        "sys_id": "f9c500a62f513010fe08351ef699b65b",
                        "po_number": "",
                        "checked_in": "",
                        "sys_class_path": "/!!/!2/!!/!,",
                        "mac_address": "",
                        "company": "",
                        "justification": "",
                        "department": "",
                        "snmp_sys_location": "",
                        "comments": "",
                        "cost": "",
                        "sys_mod_count": "1",
                        "monitor": "false",
                        "ip_address": "",
                        "model_id": "aa722dbd2f153010fe08351ef699b605",
                        "duplicate_of": "",
                        "sys_tags": "",
                        "cost_cc": "USD",
                        "discovery_proto_type": "",
                        "order_date": "",
                        "schedule": "",
                        "environment": "",
                        "due": "",
                        "attested": "false",
                        "location": "84a54c662f513010fe08351ef699b624",
                        "category": "Resource",
                        "fault_count": "0",
                        "lease_id": "",
                    },
                    {
                        "attested_date": "",
                        "can_switch": "false",
                        "stack": "false",
                        "operational_status": "1",
                        "cpu_manufacturer": "",
                        "sys_updated_on": "2021-07-14 21:45:07",
                        "discovery_source": "",
                        "first_discovered": "",
                        "due_in": "",
                        "can_partitionvlans": "false",
                        "gl_account": "",
                        "invoice_number": "",
                        "sys_created_by": "admin",
                        "ram": "",
                        "warranty_expiration": "",
                        "cpu_speed": "",
                        "owned_by": "",
                        "checked_out": "",
                        "firmware_manufacturer": "",
                        "disk_space": "",
                        "sys_domain_path": "/",
                        "discovery_proto_id": "",
                        "maintenance_schedule": "",
                        "cost_center": "",
                        "attested_by": "",
                        "dns_domain": "",
                        "assigned": "",
                        "life_cycle_stage": "",
                        "purchase_date": "",
                        "short_description": "",
                        "managed_by": "",
                        "range": "",
                        "firmware_version": "",
                        "can_print": "false",
                        "last_discovered": "",
                        "ports": "",
                        "sys_class_name": "cmdb_ci_ip_switch",
                        "cpu_count": "1",
                        "manufacturer": "",
                        "life_cycle_stage_status": "",
                        "vendor": "",
                        "can_route": "false",
                        "model_number": "",
                        "assigned_to": "",
                        "start_date": "",
                        "bandwidth": "",
                        "serial_number": "",
                        "support_group": "",
                        "correlation_id": "",
                        "unverified": "false",
                        "attributes": "",
                        "asset": "9ed6c8e62f513010fe08351ef699b6c8",
                        "skip_sync": "false",
                        "device_type": "",
                        "attestation_score": "",
                        "sys_updated_by": "admin",
                        "sys_created_on": "2021-07-14 21:40:36",
                        "cpu_type": "",
                        "sys_domain": "global",
                        "install_date": "",
                        "asset_tag": "",
                        "hardware_substatus": "",
                        "fqdn": "",
                        "stack_mode": "",
                        "change_control": "",
                        "internet_facing": "true",
                        "physical_interface_count": "",
                        "delivery_date": "",
                        "hardware_status": "installed",
                        "channels": "",
                        "install_status": "1",
                        "supported_by": "",
                        "name": "hkg-leaf-02",
                        "subcategory": "IP",
                        "default_gateway": "",
                        "assignment_group": "",
                        "managed_by_group": "",
                        "can_hub": "false",
                        "sys_id": "c4d540a62f513010fe08351ef699b602",
                        "po_number": "",
                        "checked_in": "",
                        "sys_class_path": "/!!/!2/!!/!,",
                        "mac_address": "",
                        "company": "",
                        "justification": "",
                        "department": "",
                        "snmp_sys_location": "",
                        "comments": "",
                        "cost": "",
                        "sys_mod_count": "1",
                        "monitor": "false",
                        "ip_address": "",
                        "model_id": "aa722dbd2f153010fe08351ef699b605",
                        "duplicate_of": "",
                        "sys_tags": "",
                        "cost_cc": "USD",
                        "discovery_proto_type": "",
                        "order_date": "",
                        "schedule": "",
                        "environment": "",
                        "due": "",
                        "attested": "false",
                        "location": "84a54c662f513010fe08351ef699b624",
                        "category": "Resource",
                        "fault_count": "0",
                        "lease_id": "",
                    },
                ]
            else:
                yield from []
        elif table == "cmdb_ci_network_adapter":
            if query and query["cmdb_ci"] == "f9c500a62f513010fe08351ef699b65b":  # hkg-leaf-01
                yield from [
                    {
                        "mac_manufacturer": "",
                        "attested_date": "",
                        "skip_sync": "false",
                        "operational_status": "1",
                        "sys_updated_on": "2021-07-14 21:40:27",
                        "attestation_score": "",
                        "discovery_source": "",
                        "first_discovered": "",
                        "sys_updated_by": "admin",
                        "due_in": "",
                        "sys_created_on": "2021-07-14 21:40:27",
                        "sys_domain": "global",
                        "install_date": "",
                        "gl_account": "",
                        "invoice_number": "",
                        "sys_created_by": "admin",
                        "warranty_expiration": "",
                        "asset_tag": "",
                        "cmdb_ci": "f9c500a62f513010fe08351ef699b65b",
                        "fqdn": "",
                        "change_control": "",
                        "owned_by": "",
                        "checked_out": "",
                        "sys_domain_path": "/",
                        "dhcp_enabled": "false",
                        "delivery_date": "",
                        "maintenance_schedule": "",
                        "install_status": "1",
                        "cost_center": "",
                        "attested_by": "",
                        "supported_by": "",
                        "dns_domain": "",
                        "name": "Ethernet1",
                        "assigned": "",
                        "life_cycle_stage": "",
                        "purchase_date": "",
                        "subcategory": "Network",
                        "short_description": "",
                        "virtual": "false",
                        "assignment_group": "",
                        "managed_by": "",
                        "managed_by_group": "",
                        "can_print": "false",
                        "last_discovered": "",
                        "sys_class_name": "cmdb_ci_network_adapter",
                        "manufacturer": "",
                        "sys_id": "f9c500a62f513010fe08351ef699b65d",
                        "po_number": "",
                        "checked_in": "",
                        "netmask": "255.255.255.0",
                        "sys_class_path": "/!!/!8",
                        "life_cycle_stage_status": "",
                        "mac_address": "",
                        "vendor": "",
                        "alias": "",
                        "company": "",
                        "justification": "",
                        "model_number": "",
                        "department": "",
                        "assigned_to": "",
                        "start_date": "",
                        "comments": "",
                        "cost": "",
                        "sys_mod_count": "0",
                        "monitor": "false",
                        "serial_number": "",
                        "ip_address": "",
                        "model_id": "",
                        "duplicate_of": "",
                        "sys_tags": "",
                        "cost_cc": "USD",
                        "order_date": "",
                        "schedule": "",
                        "support_group": "",
                        "environment": "",
                        "due": "",
                        "attested": "false",
                        "correlation_id": "",
                        "unverified": "false",
                        "attributes": "",
                        "location": "",
                        "asset": "",
                        "category": "Hardware",
                        "fault_count": "0",
                        "ip_default_gateway": "",
                        "lease_id": "",
                    },
                    {
                        "mac_manufacturer": "",
                        "attested_date": "",
                        "skip_sync": "false",
                        "operational_status": "1",
                        "sys_updated_on": "2021-07-14 21:40:28",
                        "attestation_score": "",
                        "discovery_source": "",
                        "first_discovered": "",
                        "sys_updated_by": "admin",
                        "due_in": "",
                        "sys_created_on": "2021-07-14 21:40:28",
                        "sys_domain": "global",
                        "install_date": "",
                        "gl_account": "",
                        "invoice_number": "",
                        "sys_created_by": "admin",
                        "warranty_expiration": "",
                        "asset_tag": "",
                        "cmdb_ci": "f9c500a62f513010fe08351ef699b65b",
                        "fqdn": "",
                        "change_control": "",
                        "owned_by": "",
                        "checked_out": "",
                        "sys_domain_path": "/",
                        "dhcp_enabled": "false",
                        "delivery_date": "",
                        "maintenance_schedule": "",
                        "install_status": "1",
                        "cost_center": "",
                        "attested_by": "",
                        "supported_by": "",
                        "dns_domain": "",
                        "name": "Ethernet2",
                        "assigned": "",
                        "life_cycle_stage": "",
                        "purchase_date": "",
                        "subcategory": "Network",
                        "short_description": "",
                        "virtual": "false",
                        "assignment_group": "",
                        "managed_by": "",
                        "managed_by_group": "",
                        "can_print": "false",
                        "last_discovered": "",
                        "sys_class_name": "cmdb_ci_network_adapter",
                        "manufacturer": "",
                        "sys_id": "4ac500a62f513010fe08351ef699b65f",
                        "po_number": "",
                        "checked_in": "",
                        "netmask": "255.255.255.0",
                        "sys_class_path": "/!!/!8",
                        "life_cycle_stage_status": "",
                        "mac_address": "",
                        "vendor": "",
                        "alias": "",
                        "company": "",
                        "justification": "",
                        "model_number": "",
                        "department": "",
                        "assigned_to": "",
                        "start_date": "",
                        "comments": "",
                        "cost": "",
                        "sys_mod_count": "0",
                        "monitor": "false",
                        "serial_number": "",
                        "ip_address": "",
                        "model_id": "",
                        "duplicate_of": "",
                        "sys_tags": "",
                        "cost_cc": "USD",
                        "order_date": "",
                        "schedule": "",
                        "support_group": "",
                        "environment": "",
                        "due": "",
                        "attested": "false",
                        "correlation_id": "",
                        "unverified": "false",
                        "attributes": "",
                        "location": "",
                        "asset": "",
                        "category": "Hardware",
                        "fault_count": "0",
                        "ip_default_gateway": "",
                        "lease_id": "",
                    },
                ]
            else:
                yield from []
        else:
            yield from []


class ServiceNowDiffSyncTestCase(TestCase):
    """Test the ServiceNowDiffSync adapter class."""

    job_class = ServiceNowDataTarget
    databases = ("default", "job_logs")

    def test_data_loading(self):
        """Test the load() function."""
        job = self.job_class()
        job.job_result = JobResult.objects.create(name=job.class_path, task_name="fake task", worker="default")
        snds = ServiceNowDiffSync(job=job, sync=None, client=MockServiceNowClient())
        snds.load()

        self.assertEqual(
            ["Asia", "China", "Japan", "Tokyo", "hkg"],
            sorted(loc.get_unique_id() for loc in snds.get_all("location")),
        )
        japan = snds.get("location", "Japan")
        self.assertEqual("Asia", japan.parent_location_name)
        self.assertEqual("0d9561b437d0200044e0bfc8bcbe5d32", japan.sys_id)
        self.assertEqual([], japan.devices)

        tokyo = snds.get("location", "Tokyo")
        self.assertEqual("Japan", tokyo.parent_location_name)
        self.assertEqual([], tokyo.devices)

        hkg = snds.get("location", "hkg")
        self.assertEqual("China", hkg.parent_location_name)
        self.assertEqual(["hkg-leaf-01", "hkg-leaf-02"], hkg.devices)

        self.assertEqual(
            ["hkg-leaf-01", "hkg-leaf-02"],
            sorted(dev.get_unique_id() for dev in snds.get_all("device")),
        )

        hkg_leaf_01 = snds.get("device", "hkg-leaf-01")
        self.assertEqual("hkg", hkg_leaf_01.location_name)
        self.assertEqual(["hkg-leaf-01__Ethernet1", "hkg-leaf-01__Ethernet2"], hkg_leaf_01.interfaces)

        self.assertEqual(
            ["hkg-leaf-01__Ethernet1", "hkg-leaf-01__Ethernet2"],
            sorted(intf.get_unique_id() for intf in snds.get_all("interface")),
        )

    def test_filtering(self):
        """Want to ensure our table query filtering is passed through correctly.

        In the mappings yaml, we have a table filter for company to only grab records with manufacturer=True.
        """
        job = self.job_class()
        job.job_result = JobResult.objects.create(name=job.class_path, task_name="fake task", worker="default")
        mock_snow_client = MockServiceNowClient()
        snds = ServiceNowDiffSync(job=job, sync=None, client=mock_snow_client)

        snds.load()
        self.assertEqual(mock_snow_client.query_params["core_company"], [{"manufacturer": True}])
        self.assertEqual(mock_snow_client.field_params["core_company"], [["manufacturer", "name", "sys_id"]])


class ServiceNowClientPaginationTestCase(TestCase):
    """Test that ServiceNowClient.all_table_entries paginates the full result set."""

    @staticmethod
    def _client_returning(rows):
        client = ServiceNowClient.__new__(ServiceNowClient)
        client.worker = None
        calls = []

        def resource(api_path=None):  # pylint: disable=unused-argument
            res = MagicMock()

            def get(query=None, fields=None, limit=None, offset=None, stream=None):  # pylint: disable=unused-argument
                calls.append({"fields": fields, "limit": limit, "offset": offset})
                page = MagicMock()
                page.all.return_value = iter(rows[offset : offset + limit])
                return page

            res.get.side_effect = get
            return res

        client.resource = resource
        return client, calls

    def test_paginates_beyond_single_page(self):
        """A table larger than one page is returned in full, not truncated at the page size."""
        rows = [{"sys_id": f"id{i}"} for i in range(25001)]
        client, calls = self._client_returning(rows)
        result = list(client.all_table_entries("cmdb_ci", fields=["sys_id"], limit=10000))
        self.assertEqual(len(result), 25001)
        self.assertEqual([row["sys_id"] for row in result], [row["sys_id"] for row in rows])
        self.assertEqual([call["offset"] for call in calls], [0, 10000, 20000, 25001])
        self.assertTrue(all(call["fields"] == ["sys_id"] for call in calls))

    def test_returns_all_when_server_caps_response_below_limit(self):
        """ServiceNow may return fewer rows than requested; offset must advance by the count actually returned."""
        server_cap = 4576
        rows = [{"sys_id": f"id{i}"} for i in range(12934)]
        client = ServiceNowClient.__new__(ServiceNowClient)
        client.worker = None
        calls = []

        def resource(api_path=None):  # pylint: disable=unused-argument
            res = MagicMock()

            def get(query=None, fields=None, limit=None, offset=None, stream=None):  # pylint: disable=unused-argument
                calls.append(offset)
                returned = min(limit, server_cap)
                page = MagicMock()
                page.all.return_value = iter(rows[offset : offset + returned])
                return page

            res.get.side_effect = get
            return res

        client.resource = resource
        result = list(client.all_table_entries("incident", fields=["sys_id"], limit=10000))
        self.assertEqual(len(result), 12934)
        self.assertEqual([row["sys_id"] for row in result], [row["sys_id"] for row in rows])
        self.assertEqual(calls, [0, 4576, 9152, 12934])

    def test_terminates_on_exact_page_multiple(self):
        """A row count that is an exact multiple of the page size still terminates."""
        rows = [{"sys_id": f"id{i}"} for i in range(10000)]
        client, calls = self._client_returning(rows)
        result = list(client.all_table_entries("t", limit=10000))
        self.assertEqual(len(result), 10000)
        self.assertEqual(len(calls), 2)

    def test_default_fields_preserves_all_columns_behavior(self):
        """With no fields specified, sysparm_fields stays empty so all columns are returned as before."""
        rows = [{"sys_id": "id0"}]
        client, calls = self._client_returning(rows)
        list(client.all_table_entries("t"))
        self.assertEqual(calls[0]["fields"], [])
        self.assertEqual(calls[0]["limit"], 10000)

    def test_streams_page_without_materializing(self):
        """Each page is consumed lazily; reading a few records does not pull the whole page into memory."""
        pages = []

        class CountingPage:
            """Page that records how many of its rows were actually pulled."""

            def __init__(self, count):
                self.count = count
                self.pulled = 0

            def all(self):
                """Lazily yield rows, counting each one as it is consumed."""
                for i in range(self.count):
                    self.pulled += 1
                    yield {"sys_id": f"id{i}"}

        client = ServiceNowClient.__new__(ServiceNowClient)
        client.worker = None

        def resource(api_path=None):  # pylint: disable=unused-argument
            res = MagicMock()

            def get(query=None, fields=None, limit=None, offset=None, stream=None):  # pylint: disable=unused-argument
                page = CountingPage(limit)
                pages.append(page)
                return page

            res.get.side_effect = get
            return res

        client.resource = resource
        first_three = list(islice(client.all_table_entries("t", limit=10000), 3))
        self.assertEqual(len(first_three), 3)
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].pulled, 3)


class ServiceNowClientReferenceTestCase(TestCase):
    """Test that reference lookups distinguish "no match" from "multiple matches"."""

    TABLE = "cmdb_hardware_product_model"
    QUERY = {"name": "C9300-48P"}

    @staticmethod
    def _client(response=None, get_error=None):
        """Build a client whose resource().get() returns `response`, or raises `get_error`."""
        client = ServiceNowClient.__new__(ServiceNowClient)
        client.worker = None
        resource = MagicMock()
        if get_error is not None:
            resource.get.side_effect = get_error
        else:
            resource.get.return_value = response
        client.resource = MagicMock(return_value=resource)
        return client, resource

    @staticmethod
    def _response(one_or_none=None, error=None, rows=None):
        response = MagicMock()
        if error is not None:
            response.one_or_none.side_effect = error
        else:
            response.one_or_none.return_value = one_or_none
        response.all.return_value = iter(rows or [])
        return response

    def test_get_by_query_raises_on_multiple_results(self):
        """Ambiguity must be raised, not collapsed to None, so callers cannot silently skip the field."""
        client, _ = self._client(self._response(error=MultipleResults("Expected single-record result")))
        with self.assertRaises(AmbiguousReferenceError) as context:
            client.get_by_query(self.TABLE, self.QUERY)
        self.assertEqual(context.exception.table, self.TABLE)
        self.assertEqual(context.exception.column, "name")
        self.assertEqual(context.exception.value, "C9300-48P")

    def test_get_by_query_returns_none_on_http_error(self):
        """An HTTP error (e.g. a nonexistent table) is still tolerated by the load path."""
        client, _ = self._client(get_error=requests.exceptions.HTTPError("400 Client Error"))
        self.assertIsNone(client.get_by_query(self.TABLE, self.QUERY))

    def test_get_by_query_returns_none_when_no_match(self):
        """A genuine miss is still None; only ambiguity changes behavior."""
        client, _ = self._client(self._response(one_or_none=None))
        self.assertIsNone(client.get_by_query(self.TABLE, self.QUERY))

    def test_get_all_by_query_returns_every_candidate(self):
        """The write path needs all candidates so it can report which records collided."""
        rows = [{"sys_id": "aaa", "name": "C9300-48P"}, {"sys_id": "bbb", "name": "C9300-48P"}]
        client, resource = self._client(self._response(rows=rows))
        self.assertEqual(client.get_all_by_query(self.TABLE, self.QUERY), rows)
        self.assertEqual(resource.get.call_args.kwargs["query"], self.QUERY)
        self.assertEqual(resource.get.call_args.kwargs["limit"], 100)

    def test_get_all_by_query_returns_empty_list_on_http_error(self):
        client, _ = self._client(get_error=requests.exceptions.HTTPError("400 Client Error"))
        self.assertEqual(client.get_all_by_query(self.TABLE, self.QUERY), [])

    def test_diagnostics_reach_the_job_log(self):
        """Client-side diagnostics must reach the Job Result, not only the module logger."""
        client, _ = self._client(self._response(one_or_none=None))
        client.worker = MagicMock()
        client.get_by_query(self.TABLE, self.QUERY)
        client.worker.logger.warning.assert_called_once()


class FieldsForMappingsTestCase(TestCase):
    """Test sysparm_fields derivation from the YAML mappings."""

    def test_derives_columns_and_reference_keys(self):
        """Derived fields include sys_id, every mapped column, and every reference key."""
        mappings = [
            {
                "field": "manufacturer_name",
                "reference": {"key": "manufacturer", "table": "core_company", "column": "name"},
            },
            {"field": "model_name", "column": "name"},
            {"field": "model_number", "column": "model_number"},
        ]
        self.assertEqual(
            ServiceNowDiffSync.fields_for_mappings(mappings),
            ["manufacturer", "model_number", "name", "sys_id"],
        )


class AmbiguousReferenceWarningTestCase(TestCase):
    """Test that duplicates which will break the next sync are surfaced during load, dry run included."""

    @staticmethod
    def _adapter(product_models):
        adapter = ServiceNowDiffSync(client=MagicMock(), job=MagicMock())
        adapter.mapping_data = ServiceNowDiffSync.load_yaml_datafile("mappings.yaml")
        adapter.sys_ids = {"cmdb_hardware_product_model": {record["sys_id"]: record for record in product_models}}
        return adapter

    def test_indistinguishable_records_are_reported(self):
        """A dry run never writes, so it never resolves a reference; the collision must surface at load."""
        adapter = self._adapter(
            [
                {"sys_id": "m1", "name": "C9300-48P", "manufacturer": "c1"},
                {"sys_id": "m2", "name": "C9300-48P", "manufacturer": "c1"},
            ]
        )
        adapter.warn_about_ambiguous_references()
        warning = str(adapter.job.logger.warning.call_args)
        self.assertIn("cmdb_hardware_product_model", warning)
        self.assertIn("C9300-48P", warning)
        self.assertIn("model_name", warning)

    def test_records_separated_by_the_match_column_are_not_reported(self):
        """Same model name under different manufacturers is exactly what the `match` clause resolves."""
        adapter = self._adapter(
            [
                {"sys_id": "m1", "name": "C9300-48P", "manufacturer": "c1"},
                {"sys_id": "m2", "name": "C9300-48P", "manufacturer": "c2"},
            ]
        )
        adapter.warn_about_ambiguous_references()
        adapter.job.logger.warning.assert_not_called()

    def test_records_with_an_empty_lookup_value_are_not_reported(self):
        """A null source value never triggers a lookup, so these records can never collide."""
        adapter = self._adapter(
            [
                {"sys_id": "m1", "name": "", "manufacturer": ""},
                {"sys_id": "m2", "name": "", "manufacturer": ""},
                {"sys_id": "m3", "name": "", "manufacturer": "c1"},
            ]
        )
        adapter.warn_about_ambiguous_references()
        adapter.job.logger.warning.assert_not_called()

    def test_an_empty_match_column_still_reports_a_name_collision(self):
        """Only the lookup column itself being empty makes a record unreachable, not a match column."""
        adapter = self._adapter(
            [
                {"sys_id": "m1", "name": "Unknown", "manufacturer": ""},
                {"sys_id": "m2", "name": "Unknown", "manufacturer": ""},
            ]
        )
        adapter.warn_about_ambiguous_references()
        self.assertIn("Unknown", str(adapter.job.logger.warning.call_args))


class ServiceNowModelUpdateTestCase(TestCase):
    """Test that ServiceNowCRUDMixin.update writes and verifies only the mapped, changed fields."""

    ENTRY = {"table": "cmdb_ci_ip_switch", "mappings": [{"field": "asset_tag", "column": "asset_tag"}]}
    # ServiceNow returns the full record on update, including a server-managed timestamp that always changes.
    UPDATE_RESULT = {"sys_id": "abc123", "asset_tag": "NEW-TAG", "sys_updated_on": "2026-06-23 12:23:52"}

    def _device(self):
        resource = MagicMock()
        result = MagicMock()
        result.one.return_value = self.UPDATE_RESULT
        resource.update.return_value = result
        client = MagicMock()
        client.resource.return_value = resource
        adapter = ServiceNowDiffSync(client=client, job=MagicMock())
        adapter.job.debug = False
        adapter.mapping_data = {"device": self.ENTRY}
        return models.Device(name="switch1", adapter=adapter, sys_id="abc123"), resource

    def test_update_keys_on_known_sys_id(self):
        """The update is keyed on the sys_id captured at load time, not re-queried by identifier."""
        device, resource = self._device()
        device.update({"asset_tag": "NEW-TAG"})
        self.assertEqual(resource.update.call_args.kwargs["query"], {"sys_id": "abc123"})

    def test_update_payload_only_includes_mapped_changed_fields(self):
        """Only the mapped, changed column is sent — not the full existing record or server-managed fields."""
        device, resource = self._device()
        device.update({"asset_tag": "NEW-TAG"})
        self.assertEqual(resource.update.call_args.kwargs["payload"], {"asset_tag": "NEW-TAG"})

    def test_update_tolerates_server_managed_timestamp_change(self):
        """A changed sys_updated_on in the response must not raise ObjectNotUpdated for a successful write."""
        device, _ = self._device()
        self.assertEqual(device.update({"asset_tag": "NEW-TAG"}), device)
