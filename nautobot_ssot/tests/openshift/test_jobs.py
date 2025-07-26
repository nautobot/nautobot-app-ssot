"""Test OpenShift Jobs."""

import os
from copy import deepcopy
from unittest.mock import Mock, patch

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from nautobot_ssot.integrations.openshift import jobs
from .openshift_fixtures import create_default_openshift_config

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})
BACKUP_CONFIG = deepcopy(CONFIG)


@patch.dict(
    os.environ,
    {
        "TEST_OPENSHIFT_USERNAME": "openshift",
        "TEST_OPENSHIFT_TOKEN": "sha256~test-token-12345",
    },
)
class OpenshiftJobTest(TestCase):
    """Test the OpenShift job."""

    def test_metadata(self):
        """Verify correctness of the Job Meta attributes."""
        self.assertEqual("SSoT - OpenShift", jobs.name)
        self.assertEqual("OpenShift ⟹ Nautobot", jobs.OpenshiftDataSource.name)
        self.assertEqual("OpenShift ⟹ Nautobot", jobs.OpenshiftDataSource.Meta.name)
        self.assertEqual("OpenShift", jobs.OpenshiftDataSource.Meta.data_source)
        self.assertEqual(
            "Sync data from OpenShift to Nautobot (including KubeVirt VMs)",
            jobs.OpenshiftDataSource.Meta.description,
        )

    def test_data_mapping(self):
        """Verify correctness of the data_mappings() API."""
        mappings = jobs.OpenshiftDataSource.data_mappings()

        self.assertEqual("Project/Namespace", mappings[0].source_name)
        self.assertIsNone(mappings[0].source_url)
        self.assertEqual("Tenant", mappings[0].target_name)
        self.assertEqual(reverse("tenancy:tenant_list"), mappings[0].target_url)

        self.assertEqual("Node", mappings[1].source_name)
        self.assertIsNone(mappings[1].source_url)
        self.assertEqual("Device", mappings[1].target_name)
        self.assertEqual(reverse("dcim:device_list"), mappings[1].target_url)

        self.assertEqual("Container/Pod", mappings[2].source_name)
        self.assertIsNone(mappings[2].source_url)
        self.assertEqual("Application", mappings[2].target_name)
        self.assertEqual(reverse("extras:application_list"), mappings[2].target_url)

        self.assertEqual("Deployment", mappings[3].source_name)
        self.assertIsNone(mappings[3].source_url)
        self.assertEqual("Application", mappings[3].target_name)
        self.assertEqual(reverse("extras:application_list"), mappings[3].target_url)

        self.assertEqual("KubeVirt VM", mappings[4].source_name)
        self.assertIsNone(mappings[4].source_url)
        self.assertEqual("Virtual Machine", mappings[4].target_name)
        self.assertEqual(reverse("virtualization:virtualmachine_list"), mappings[4].target_url)

        self.assertEqual("Service", mappings[5].source_name)
        self.assertIsNone(mappings[5].source_url)
        self.assertEqual("Service", mappings[5].target_name)
        self.assertEqual(reverse("ipam:service_list"), mappings[5].target_url)

    @patch("nautobot_ssot.integrations.openshift.diffsync.adapters.adapter_openshift.OpenshiftAdapter")
    @patch("nautobot_ssot.integrations.openshift.diffsync.adapters.adapter_nautobot.OpenshiftNautobotAdapter")
    def test_load_source_adapter(self, mock_nautobot_adapter, mock_openshift_adapter):
        """Test loading source adapter."""
        config = create_default_openshift_config()
        job = jobs.OpenshiftDataSource()
        job.kwargs = {"openshift_instance": config}
        job.job = Mock()
        job.sync = Mock()
        
        # Mock the client
        mock_client = Mock()
        mock_client.kubevirt_available = True
        mock_openshift_adapter.return_value.client = mock_client
        
        job.load_source_adapter()
        
        # Verify adapter was created with correct config
        mock_openshift_adapter.assert_called_once_with(
            job=job,
            sync=job.sync,
            config=config,
        )
        
        # Verify KubeVirt detection message
        job.job.logger.info.assert_called_with("KubeVirt detected - will sync virtual machines")
        
        # Verify load was called
        mock_openshift_adapter.return_value.load.assert_called_once()

    @patch("nautobot_ssot.integrations.openshift.diffsync.adapters.adapter_openshift.OpenshiftAdapter")
    @patch("nautobot_ssot.integrations.openshift.diffsync.adapters.adapter_nautobot.OpenshiftNautobotAdapter")
    def test_load_source_adapter_no_kubevirt(self, mock_nautobot_adapter, mock_openshift_adapter):
        """Test loading source adapter when KubeVirt is not available."""
        config = create_default_openshift_config()
        job = jobs.OpenshiftDataSource()
        job.kwargs = {"openshift_instance": config}
        job.job = Mock()
        job.sync = Mock()
        
        # Mock the client without KubeVirt
        mock_client = Mock()
        mock_client.kubevirt_available = False
        mock_openshift_adapter.return_value.client = mock_client
        
        job.load_source_adapter()
        
        # Verify KubeVirt not detected message
        job.job.logger.info.assert_called_with("KubeVirt not detected - will sync containers only")

    def test_load_target_adapter(self):
        """Test loading target adapter."""
        with patch("nautobot_ssot.integrations.openshift.diffsync.adapters.adapter_nautobot.OpenshiftNautobotAdapter") as mock_adapter:
            job = jobs.OpenshiftDataSource()
            job.job = Mock()
            job.sync = Mock()
            
            job.load_target_adapter()
            
            # Verify adapter was created
            mock_adapter.assert_called_once_with(
                job=job,
                sync=job.sync,
            )
            
            # Verify load was called
            mock_adapter.return_value.load.assert_called_once() 