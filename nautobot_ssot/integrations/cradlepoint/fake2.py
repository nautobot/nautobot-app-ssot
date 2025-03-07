import sys
import time

from django.conf import settings
from django.db import transaction
from django.forms import widgets

from nautobot.apps.jobs import (
    BooleanVar,
    ChoiceVar,
    DryRunVar,
    FileVar,
    IntegerVar,
    IPAddressVar,
    IPAddressWithMaskVar,
    IPNetworkVar,
    Job,
    JobButtonReceiver,
    JobHookReceiver,
    JSONVar,
    MultiChoiceVar,
    MultiObjectVar,
    ObjectVar,
    register_jobs,
    StringVar,
    TextVar,
)
from nautobot.dcim.models import Device, Location, LocationType
from nautobot.extras.choices import ObjectChangeActionChoices
from nautobot.extras.jobs import get_task_logger
from nautobot.extras.models import Status


class ExampleSingletonJob(Job):
    class Meta:
        name = "Example job, only one can run at any given time."
        is_singleton = True

    def run(self, *args, **kwargs):
        time.sleep(60)


jobs = [ExampleSingletonJob]
