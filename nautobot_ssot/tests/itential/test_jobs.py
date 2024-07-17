"""Itential SSoT Jobs Test Cases."""

from django.test import override_settings
from nautobot.extras.models import Job, JobLogEntry
from nautobot.apps.testing import run_job_for_testing

from nautobot_ssot.tests.itential.fixtures import base

from nautobot_ssot.integrations.itential.models import AutomationGatewayModel


@override_settings(
    PLUGINS_CONFIG={
        "nautobot_ssot": {
            "enable_itential": True,
        }
    }
)
class ItentialSSoTJobsTestCase(base.ItentialSSoTBaseTransactionTestCase):
    """Itential SSoT Jobs Test Cases."""

    databases = ("default", "job_logs")

    def test_job_success(self):
        """Test successful job."""
        self.job = Job.objects.get(
            job_class_name="ItentialAutomationGatewayDataTarget",
            module_name="nautobot_ssot.integrations.itential.jobs",
        )
        job_result = run_job_for_testing(
            self.job, dryrun=False, memory_profiling=False, gateway=self.gateway.pk, status=self.status.pk
        )
        log_entries = JobLogEntry.objects.filter(job_result=job_result)
        self.assertGreater(log_entries.count(), 1)
        log_entries = [log_entry.message for log_entry in log_entries]
        summary_output = "{'create': 2, 'update': 1, 'delete': 1, 'no-change': 1, 'skip': 0}"
        self.assertIn(summary_output, log_entries)
        self.assertIn("Sync complete", log_entries)

    def test_job_disabled_gateway(self):
        """Test job with disabled automation gateway."""
        gateway = AutomationGatewayModel.objects.get(name="IAG10")
        self.job = Job.objects.get(
            job_class_name="ItentialAutomationGatewayDataTarget",
            module_name="nautobot_ssot.integrations.itential.jobs",
        )
        job_result = run_job_for_testing(
            self.job, dryrun=False, memory_profiling=False, gateway=gateway.pk, status=self.status.pk
        )
        log_entries = JobLogEntry.objects.filter(job_result=job_result)
        self.assertGreater(log_entries.count(), 1)
        log_entries = [log_entry.message for log_entry in log_entries]
        summary_output = f"{gateway.gateway.remote_url} is not enabled to sync inventory."
        self.assertIn(summary_output, log_entries)
