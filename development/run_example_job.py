"""Executes a job locally for testing purposes.

To run this script use the following command:

```
invoke nbshell \
    --plain \
    --file development/run_example_job.py \
    --env RUN_SSOT_TARGET_JOB=False \
    --env RUN_SSOT_JOB_DRY_RUN=True
```

Passing environment variables to the script is optional. The script will default to running the data source job with a dry run enabled.
"""

import json
import os

from django.core.management import call_command
from nautobot.core.settings_funcs import is_truthy
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import ExternalIntegration, Job, Secret, SecretsGroup, SecretsGroupAssociation

_TOKEN = 40 * "a"
os.environ["NAUTOBOT_DEMO_TOKEN"] = _TOKEN

_NAUTOBOT_DEMO_URL = "https://demo.nautobot.com"
_DRY_RUN = is_truthy(os.getenv("RUN_SSOT_JOB_DRY_RUN", "True"))

module_name = "nautobot_ssot.jobs.examples"
is_target_job = is_truthy(os.getenv("RUN_SSOT_TARGET_JOB", "False"))
job_class_name = "ExampleDataTarget" if is_target_job else "ExampleDataSource"

job = Job.objects.get(module_name=module_name, job_class_name=job_class_name)
if not job.enabled:
    job.enabled = True
    job.validated_save()

nautobot_demo, created = ExternalIntegration.objects.get_or_create(
    name="Nautobot Demo",
    defaults={
        "remote_url": _NAUTOBOT_DEMO_URL,
        "verify_ssl": False,
    },
)

if created:
    secret = Secret.objects.create(
        name="nautobot-demo-token",
        provider="environment-variable",
        parameters={"variable": "NAUTOBOT_DEMO_TOKEN"},
    )
    secrets_group = SecretsGroup.objects.create(name="Nautobot Demo Group")
    SecretsGroupAssociation.objects.create(
        secret=secret,
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
    )
    nautobot_demo.secrets_group = secrets_group
    nautobot_demo.validated_save()

data: dict = {
    "debug": True,
    "dryrun": _DRY_RUN,
    "memory_profiling": False,
}

if is_target_job:
    data["target"] = str(nautobot_demo.pk)
    data["target_url"] = _NAUTOBOT_DEMO_URL
    data["target_token"] = _TOKEN
else:
    data["source"] = str(nautobot_demo.pk)
    data["source_url"] = _NAUTOBOT_DEMO_URL
    data["source_token"] = _TOKEN

call_command(
    "runjob",
    f"{module_name}.{job_class_name}",
    data=json.dumps(data),
    username="admin",
    local=True,  # Enable to run the job locally (not as a celery task)
)
