"""Test Forward Enterprise job functionality."""

from unittest import TestCase

from nautobot.extras.jobs import Job

from nautobot_ssot.integrations.forward_enterprise.jobs import ForwardEnterpriseDataSource
from nautobot_ssot.jobs.base import DataSource


class TestForwardEnterpriseJob(TestCase):
    """Test Forward Enterprise job functionality."""

    def test_job_init(self):
        """Test job initialization."""
        job = ForwardEnterpriseDataSource()
        self.assertTrue(hasattr(job, "run"))
        self.assertTrue(hasattr(job, "load_source_adapter"))

    def test_job_has_required_attributes(self):
        """Test that job has required SSoT attributes."""
        job = ForwardEnterpriseDataSource()
        # Should have the required SSoT job attributes
        self.assertTrue(hasattr(job, "class_path"))
        self.assertTrue(hasattr(job, "name"))
        self.assertTrue(hasattr(job, "data_source"))
        self.assertTrue(hasattr(job, "data_target"))

    def test_job_meta_attributes(self):
        """Test job meta attributes."""
        job = ForwardEnterpriseDataSource()
        # Check that the job has proper metadata
        self.assertEqual(job.data_source, "Forward Enterprise")
        self.assertEqual(job.data_target, "Nautobot")
        self.assertIn("Forward Enterprise", job.name)

    def test_job_form_fields(self):
        """Test that job has expected form fields."""
        job = ForwardEnterpriseDataSource()
        # Should have form fields for configuration
        # These would be defined in the job's Meta class or as attributes
        self.assertTrue(hasattr(job, "Meta") or hasattr(job, "_get_vars"))

    def test_job_inheritance(self):
        """Test that job properly inherits from required base classes."""
        job = ForwardEnterpriseDataSource()
        # Should inherit from both DataSource and Job
        self.assertIsInstance(job, DataSource)
        self.assertIsInstance(job, Job)

    def test_job_form_variables(self):
        """Test that job has expected form variables."""
        job = ForwardEnterpriseDataSource()
        # Should have the expected form variables
        self.assertTrue(hasattr(job, "credentials"))
        self.assertTrue(hasattr(job, "namespace"))
        self.assertTrue(hasattr(job, "sync_interfaces"))
        self.assertTrue(hasattr(job, "sync_ipam"))
        self.assertTrue(hasattr(job, "delete_objects"))
