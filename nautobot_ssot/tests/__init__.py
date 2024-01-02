"""Unit tests for nautobot_ssot app."""

from django.conf import settings

if "job_logs" in settings.DATABASES:
    settings.DATABASES["job_logs"] = settings.DATABASES["job_logs"].copy()
    settings.DATABASES["job_logs"]["TEST"] = {"MIRROR": "default"}
