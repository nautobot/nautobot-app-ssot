"""Management command to dump test fixture data."""
import os
from pathlib import Path
from django.core.management.base import BaseCommand
from django.core import management


class Command(BaseCommand):
    """Publish command to dump test fixture data."""

    help = "Destroy, build from initialized + ssot sync data and save to test nautobot_dump.json file."

    def handle(self, *args, **kwargs):
        """Add handler for `dev_destroy_and_dump`."""
        dir_path = Path(Path(os.path.dirname(os.path.realpath(__file__))).parent).parent
        exclude = [
            "contenttypes",
            "auth.permission",
            "nautobot_ssot",
            "sessions.session",
            "database.constance",
            "users.user",
            "users.token",
            "extras.job",
            "django_rq",
            "extras.objectchange",
        ]
        management.call_command(
            "dumpdata",
            exclude=exclude,
            format="json",
            indent=2,
            use_natural_primary_keys=True,
            use_natural_foreign_keys=True,
            output=f"{dir_path}/fixtures/nautobot_dump.json",
        )
