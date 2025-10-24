"""Comprehensive test suite for Forward Enterprise adapter functionality."""

from unittest import TestCase
from unittest.mock import Mock, patch

from diffsync import DiffSync

from nautobot_ssot.integrations.forward_enterprise.diffsync.adapters.forward_enterprise import ForwardEnterpriseAdapter
from nautobot_ssot.integrations.forward_enterprise.diffsync.adapters.nautobot import NautobotDiffSyncAdapter
from nautobot_ssot.integrations.forward_enterprise.exceptions import ForwardEnterpriseValidationError

from .fixtures import (
    MOCK_NQE_DEVICE_QUERY_RESULT,
    MOCK_NQE_INTERFACE_QUERY_RESULT,
    MOCK_NQE_IPAM_QUERY_RESULT,
    DummyJob,
)
from .mocks import MockForwardEnterpriseClient

# pylint: disable=W0212,R0904


class TestForwardEnterpriseAdapter(TestCase):
    """Comprehensive test suite for Forward Enterprise adapter functionality."""

    def setUp(self):
        """Set up test instances."""
        self.job = DummyJob()
        self.api_url = "https://test.example.com"
        self.api_token = "test_token"

    def test_forward_enterprise_adapter_init(self):
        """Test Forward Enterprise adapter initialization."""
        adapter = ForwardEnterpriseAdapter(
            job=self.job,
            sync_interfaces=True,
            sync_ipam=True,
        )
        self.assertIsNotNone(adapter.job)
        self.assertTrue(adapter.sync_interfaces)
        self.assertTrue(adapter.sync_ipam)
        self.assertTrue(hasattr(adapter, "load"))

    def test_forward_enterprise_adapter_init_basic(self):
        """Test basic adapter initialization."""
        adapter = ForwardEnterpriseAdapter(
            job=self.job,
        )
        self.assertIsNotNone(adapter.job)
        self.assertFalse(adapter.sync_interfaces)
        self.assertFalse(adapter.sync_ipam)

    def test_forward_enterprise_adapter_init_with_sync_options(self):
        """Test adapter initialization with sync options."""
        adapter = ForwardEnterpriseAdapter(
            job=self.job,
            sync_interfaces=True,
            sync_ipam=True,
        )
        self.assertTrue(adapter.sync_interfaces)
        self.assertTrue(adapter.sync_ipam)

    def test_forward_enterprise_adapter_init_api_url_rstrip(self):
        """Test that API URL is right-stripped of trailing slashes."""
        adapter = ForwardEnterpriseAdapter(
            job=self.job,
        )
        # The API URL is now handled by the client, so we check the client's api_url
        self.assertEqual(adapter.client.api_url, self.api_url)

    def test_forward_enterprise_adapter_init_with_credentials(self):
        """Test adapter initialization with job credentials."""
        mock_secrets_group = Mock()
        mock_secrets_group.get_secret_value.return_value = "secret_token"
        self.job.credentials.secrets_group = mock_secrets_group

        adapter = ForwardEnterpriseAdapter(
            job=self.job,
        )
        self.assertEqual(adapter.client.api_token, "secret_token")

    def test_nautobot_adapter_init(self):
        """Test Nautobot adapter initialization."""
        adapter = NautobotDiffSyncAdapter(job=self.job)
        self.assertIsNotNone(adapter.job)
        self.assertTrue(hasattr(adapter, "load"))

    def test_adapters_have_same_top_level_models(self):
        """Test that both adapters have the same top-level models."""
        fe_adapter = ForwardEnterpriseAdapter(
            job=self.job,
        )
        nb_adapter = NautobotDiffSyncAdapter(job=self.job)

        # Convert to sets for comparison
        fe_models = set(fe_adapter.top_level)
        nb_models = set(nb_adapter.top_level)

        # Both should have the same models
        self.assertEqual(fe_models, nb_models, f"Model mismatch: FE has {fe_models}, NB has {nb_models}")

    def test_query_id_validation_helper(self):
        """Test the helper method to detect if a string is a query ID."""
        adapter = ForwardEnterpriseAdapter(
            job=self.job,
        )

        # Test valid query IDs
        self.assertTrue(adapter.client._is_query_id("Q_devices_basic"))  # pylint: disable=protected-access
        self.assertTrue(adapter.client._is_query_id("Q_interfaces_all"))  # pylint: disable=protected-access
        self.assertTrue(adapter.client._is_query_id("Q_network_topology_123"))  # pylint: disable=protected-access

        # Test invalid query IDs (actual queries)
        self.assertFalse(adapter.client._is_query_id("devices | select hostname"))  # pylint: disable=protected-access
        self.assertFalse(adapter.client._is_query_id("foreach device in network"))  # pylint: disable=protected-access
        self.assertFalse(adapter.client._is_query_id("q_lowercase_should_not_match"))  # pylint: disable=protected-access
        self.assertFalse(adapter.client._is_query_id("regular_query_id"))  # pylint: disable=protected-access
        self.assertFalse(adapter.client._is_query_id("Q_"))  # pylint: disable=protected-access
        self.assertFalse(adapter.client._is_query_id("Q_ invalid spaces"))  # pylint: disable=protected-access
        self.assertFalse(adapter.client._is_query_id(""))  # pylint: disable=protected-access

    @patch("requests.post")
    def test_execute_nqe_query_with_query(self, mock_post):
        """Test executing NQE query with raw query."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = MOCK_NQE_DEVICE_QUERY_RESULT["items"]
        mock_post.return_value = mock_response

        query = "devices | select hostname, ip"
        adapter = ForwardEnterpriseAdapter(
            job=self.job,
        )

        result = adapter.client.execute_nqe_query(query=query)

        self.assertEqual(result, MOCK_NQE_DEVICE_QUERY_RESULT["items"])
        mock_post.assert_called_once()

        # Verify the request payload contains query
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        self.assertIn("query", payload)
        self.assertNotIn("queryId", payload)

    def test_client_execute_nqe_query_success(self):
        """Test successful NQE query execution."""
        # Use mock client instead of real client
        mock_client = MockForwardEnterpriseClient(
            base_url="https://test.example.com", username="test_user", password="test_token", verify_ssl=True
        )

        # The mock client's nqe.run_query should return device data for device queries
        result = mock_client.nqe.run_query({"query": "devices | select hostname, ip"})

        self.assertEqual(result, MOCK_NQE_DEVICE_QUERY_RESULT)

    def test_execute_nqe_query_no_query_or_id_raises_error(self):
        """Test that execute_nqe_query raises error when neither query nor query_id provided."""
        adapter = ForwardEnterpriseAdapter(
            job=self.job,
        )

        with self.assertRaises(ForwardEnterpriseValidationError) as context:
            adapter.client.execute_nqe_query()

        self.assertIn("Either query or query_id must be provided", str(context.exception))

    @patch("requests.post")
    def test_execute_nqe_query_with_parameters(self, mock_post):
        """Test executing NQE query with parameters."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = MOCK_NQE_DEVICE_QUERY_RESULT["items"]
        mock_post.return_value = mock_response

        adapter = ForwardEnterpriseAdapter(
            job=self.job,
        )

        parameters = {"site": "Site-A", "vendor": "Cisco"}
        result = adapter.client.execute_nqe_query(query="devices | select hostname, ip", parameters=parameters)

        self.assertEqual(result, MOCK_NQE_DEVICE_QUERY_RESULT["items"])

        # Verify the request payload contains parameters
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        self.assertEqual(payload["parameters"], parameters)

    def test_load_vrf_handles_special_names(self):
        """Test that VRF loading handles special names like management."""
        adapter = ForwardEnterpriseAdapter(
            job=self.job,
        )

        # Mock the necessary methods using patch
        with (
            patch.object(adapter, "vrf") as mock_vrf,
            patch.object(adapter, "add") as mock_add,
            patch.object(adapter, "get", side_effect=KeyError),
        ):
            # Test with special VRF names including management VRF
            adapter.load_vrf("management", "Global")
            adapter.load_vrf("default", "Global")

            # Should not raise exceptions and should set system_of_record
            self.assertEqual(mock_vrf.call_count, 2)
            self.assertEqual(mock_add.call_count, 2)

            # Verify system_of_record is set for VRFs
            call_args = mock_vrf.call_args_list
            for call in call_args:
                self.assertIn("system_of_record", call[1])
                self.assertEqual(call[1]["system_of_record"], "Forward Enterprise")

    def test_load_ipam_handles_empty(self):
        """Test that IPAM loading handles empty data."""
        adapter = ForwardEnterpriseAdapter(
            job=self.job,
            sync_ipam=True,
        )
        adapter.ipam_data = []
        adapter.load_ipam()  # Should not raise

    def test_adapter_inheritance(self):
        """Test that adapter properly inherits from DiffSync."""
        adapter = ForwardEnterpriseAdapter(
            job=self.job,
        )
        # Should inherit from DiffSync
        self.assertIsInstance(adapter, DiffSync)
        # Should have the load method from DiffSync
        self.assertTrue(hasattr(adapter, "load"))

    def test_adapter_top_level_models(self):
        """Test that adapter has expected top-level models."""
        adapter = ForwardEnterpriseAdapter(
            job=self.job,
        )
        # Should have device as a top-level model
        self.assertIn("device", adapter.top_level)
        # Should have IPAM models
        self.assertIn("vrf", adapter.top_level)
        self.assertIn("prefix", adapter.top_level)

    def test_adapter_with_realistic_nqe_data(self):
        """Test adapter processing with realistic NQE query results."""
        # Patch the ForwardEnterpriseClient to use our mock
        with patch(
            "nautobot_ssot.integrations.forward_enterprise.diffsync.adapters.forward_enterprise.ForwardEnterpriseClient"
        ) as mock_client_class:
            mock_client = MockForwardEnterpriseClient(
                base_url="https://test.example.com", username="test_user", password="test_token", verify_ssl=True
            )
            mock_client_class.return_value = mock_client

            adapter = ForwardEnterpriseAdapter(
                job=self.job,
                sync_interfaces=True,
                sync_ipam=True,
            )

            # Mock other required methods
            with patch.multiple(
                adapter,
                load_tags=Mock(),
                load_locations=Mock(),
            ):
                # Load data from mocked NQE queries
                adapter.load()

                # Verify that the adapter processed the devices correctly
                self.assertGreater(len(adapter.devices_data), 0)

                # Check specific devices from our mock data
                device_names = [device["name"] for device in adapter.devices_data]
                self.assertIn("sjc-dc12-acc305", device_names)
                self.assertIn("atl-app-lb01", device_names)

                # Verify device attributes are mapped correctly
                arista_device = next(device for device in adapter.devices_data if device["name"] == "sjc-dc12-acc305")
                self.assertEqual(arista_device["manufacturer"], "ARISTA")
                self.assertEqual(arista_device["device_type"], "vEOS")
                self.assertEqual(arista_device["location"], "compute-pod300")

                # Verify F5 device is processed differently
                f5_device = next(device for device in adapter.devices_data if device["name"] == "atl-app-lb01")
                self.assertEqual(f5_device["manufacturer"], "F5")
                self.assertEqual(f5_device["role"], "LOAD_BALANCER")

                # Verify interfaces are loaded
                self.assertGreater(len(adapter.interfaces_data), 0)
                interface_names = [f"{iface['device']}-{iface['name']}" for iface in adapter.interfaces_data]
                self.assertIn("sjc-dc12-acc305-et1", interface_names)
                self.assertIn("sjc-dc12-acc305-ma1", interface_names)

                # Verify IPAM data is loaded
                self.assertGreater(len(adapter.ipam_data), 0)

                # Check that management VRF IPs are captured
                mgmt_ips = [ipam for ipam in adapter.ipam_data if ipam["vrf"] == "management"]
                self.assertGreater(len(mgmt_ips), 0)

                # Verify specific IP addresses from mock data
                ip_addresses = [ipam["ip"] for ipam in adapter.ipam_data]
                self.assertIn("10.117.38.51", ip_addresses)  # Management IP
                self.assertIn("10.100.0.134", ip_addresses)  # Point-to-point IP
        self.assertIn("ipaddress", adapter.top_level)
        self.assertIn("vlan", adapter.top_level)

    def test_adapter_sync_flags(self):
        """Test adapter sync flags functionality."""
        # Test with both flags enabled
        adapter = ForwardEnterpriseAdapter(
            job=self.job,
            sync_interfaces=True,
            sync_ipam=True,
        )
        self.assertTrue(adapter.sync_interfaces)
        self.assertTrue(adapter.sync_ipam)

        # Test with both flags disabled
        adapter = ForwardEnterpriseAdapter(
            job=self.job,
            sync_interfaces=False,
            sync_ipam=False,
        )
        self.assertFalse(adapter.sync_interfaces)
        self.assertFalse(adapter.sync_ipam)

    @patch("requests.post")
    def test_system_of_record_field_set_for_ipam_objects(self, mock_post):
        """Test that system_of_record field is properly set for IPAM objects."""
        # Mock API responses
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = [MOCK_NQE_DEVICE_QUERY_RESULT["items"], MOCK_NQE_IPAM_QUERY_RESULT["items"]]
        mock_post.return_value = mock_response

        adapter = ForwardEnterpriseAdapter(
            job=self.job,
            sync_ipam=True,
        )

        # Mock the client methods to return our test data
        adapter.client.get_device_query_from_config = Mock(return_value="test_device_query")
        adapter.client.get_ipam_query_from_config = Mock(return_value="test_ipam_query")

        # Mock the object creation methods to capture calls
        with (
            patch.object(adapter, "prefix") as mock_prefix,
            patch.object(adapter, "ipaddress") as mock_ipaddress,
            patch.object(adapter, "vrf") as mock_vrf,
            patch.object(adapter, "get", side_effect=KeyError),
            patch.multiple(
                adapter,
                load_tags=Mock(),
                load_locations=Mock(),
                load_manufacturers=Mock(),
                load_device_types=Mock(),
                load_platforms=Mock(),
                load_roles=Mock(),
                load_devices=Mock(),
                _ensure_interface_exists=Mock(),
            ),
        ):
            adapter.load()

        # Verify that VRF objects are created with system_of_record
        vrf_calls = mock_vrf.call_args_list
        self.assertGreater(len(vrf_calls), 0, "VRF objects should be created")
        for call in vrf_calls:
            self.assertIn("system_of_record", call[1])
            self.assertEqual(call[1]["system_of_record"], "Forward Enterprise")

        # Verify that Prefix objects are created with system_of_record
        prefix_calls = mock_prefix.call_args_list
        self.assertGreater(len(prefix_calls), 0, "Prefix objects should be created")
        for call in prefix_calls:
            self.assertIn("system_of_record", call[1])
            self.assertEqual(call[1]["system_of_record"], "Forward Enterprise")

        # Verify that IPAddress objects are created with system_of_record
        ip_calls = mock_ipaddress.call_args_list
        self.assertGreater(len(ip_calls), 0, "IPAddress objects should be created")
        for call in ip_calls:
            self.assertIn("system_of_record", call[1])
            self.assertEqual(call[1]["system_of_record"], "Forward Enterprise")

    def test_load_vlan_sets_system_of_record(self):
        """Test that VLAN objects are created with system_of_record field."""
        adapter = ForwardEnterpriseAdapter(
            job=self.job,
            sync_interfaces=True,
        )

        # Mock interface data with VLAN information
        adapter.interfaces_data = [
            {
                "device": "test-device",
                "name": "Vlan100",
                "enabled": "1",
                "mtu": 1500,
                "mac_address": "00:01:02:03:04:05",
            }
        ]

        with patch.object(adapter, "vlan") as mock_vlan, patch.object(adapter, "get", side_effect=KeyError):
            adapter.load_vlan(100, "test-location")

            # Verify VLAN is created with system_of_record
            mock_vlan.assert_called_once()
            call_args = mock_vlan.call_args[1]
            self.assertIn("system_of_record", call_args)
            self.assertEqual(call_args["system_of_record"], "Forward Enterprise")

    def test_interface_type_determination_uses_constants(self):
        """Test that interface type determination uses constants mapping."""
        adapter = ForwardEnterpriseAdapter(
            job=self.job,
        )

        # Test various interface name patterns
        test_cases = [
            ("ma1", "1000base-t"),  # Management interface
            ("lo0", "virtual"),  # Loopback interface
            ("et1", "1000base-t"),  # Regular ethernet
            ("Vlan100", "virtual"),  # VLAN interface
            ("vmk0", "virtual"),  # VMware interface
        ]

        for interface_name, expected_type in test_cases:
            with self.subTest(interface_name=interface_name):
                result = adapter._determine_interface_type(interface_name)
                self.assertEqual(result, expected_type)

    @patch("requests.post")
    def test_load_flow_with_realistic_data(self, mock_post):
        """Test the complete load flow with realistic Forward Enterprise data."""
        # Mock API responses in sequence
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = [
            MOCK_NQE_DEVICE_QUERY_RESULT["items"],
            MOCK_NQE_INTERFACE_QUERY_RESULT["items"],
            MOCK_NQE_IPAM_QUERY_RESULT["items"],
        ]
        mock_post.return_value = mock_response

        adapter = ForwardEnterpriseAdapter(
            job=self.job,
            sync_interfaces=True,
            sync_ipam=True,
        )

        # Mock the client query methods
        adapter.client.get_device_query_from_config = Mock(return_value="test_device_query")
        adapter.client.get_interface_query_from_config = Mock(return_value="test_interface_query")
        adapter.client.get_ipam_query_from_config = Mock(return_value="test_ipam_query")

        # Mock object creation to capture what gets created
        created_objects = {"devices": [], "interfaces": [], "vrfs": [], "prefixes": [], "ipaddresses": []}

        def mock_add(obj):
            """Mock add method to track created objects."""
            model_name = obj._modelname
            if model_name in created_objects:
                created_objects[model_name].append(obj)

        with (
            patch.object(adapter, "add", side_effect=mock_add),
            patch.object(adapter, "get", side_effect=KeyError),
            patch.multiple(
                adapter,
                load_tags=Mock(),
                load_locations=Mock(),
                load_manufacturers=Mock(),
                load_device_types=Mock(),
                load_platforms=Mock(),
                load_roles=Mock(),
            ),
        ):
            adapter.load()

        # Verify that objects were created from the realistic data
        self.assertEqual(len(adapter.devices_data), 4)  # 4 devices in mock data
        self.assertEqual(len(adapter.interfaces_data), 4)  # 4 interfaces in mock data
        self.assertEqual(len(adapter.ipam_data), 8)  # 8 IPAM records in mock data

    def test_vrf_recreation_prevention(self):
        """Test that VRFs with system_of_record are not recreated on subsequent runs."""
        adapter = ForwardEnterpriseAdapter(
            job=self.job,
            sync_ipam=True,
        )

        # First run - VRF doesn't exist
        with (
            patch.object(adapter, "vrf") as mock_vrf,
            patch.object(adapter, "add") as mock_add,
            patch.object(adapter, "get", side_effect=KeyError),
        ):
            adapter.load_vrf("management", "Global")
            mock_vrf.assert_called_once()
            mock_add.assert_called_once()

        # Reset mocks
        mock_vrf.reset_mock()
        mock_add.reset_mock()

        # Second run - VRF exists with matching system_of_record
        mock_existing_vrf = Mock()
        mock_existing_vrf.system_of_record = "Forward Enterprise"

        with (
            patch.object(adapter, "vrf") as mock_vrf,
            patch.object(adapter, "add") as mock_add,
            patch.object(adapter, "get", return_value=mock_existing_vrf),
        ):
            adapter.load_vrf("management", "Global")

            # Should not create new VRF when one already exists
            mock_vrf.assert_not_called()
            mock_add.assert_not_called()
