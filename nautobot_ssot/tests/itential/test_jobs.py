"""Itential SSoT Jobs Test Cases."""

from nautobot.extras.models import Job, JobLogEntry
from nautobot.apps.testing import run_job_for_testing

from nautobot_ssot.tests.itential.fixtures import base


class ItentialSSoTJobsTestCase(base.ItentialSSoTBaseTransactionTestCase):
    """Itential SSoT Jobs Test Cases."""

    databases = ("default", "job_logs")

    def test_successful_job(self):
        """Test successful job."""
        self.job = Job.objects.get(
            job_class_name="ItentialAutomationGatewayDataTarget",
            module_name="nautobot_ssot.integrations.itential.jobs",
        )
        job_result = run_job_for_testing(self.job, dryrun=False, memory_profiling=False, gateway=self.gateway.pk)
        log_entries = JobLogEntry.objects.filter(job_result=job_result)
        self.assertGreater(log_entries.count(), 1)
        log_entries = [log_entry.message for log_entry in log_entries]
        summary_output = "{'create': 1, 'update': 1, 'delete': 1, 'no-change': 0, 'skip': 0}"
        self.assertIn(summary_output, log_entries)
