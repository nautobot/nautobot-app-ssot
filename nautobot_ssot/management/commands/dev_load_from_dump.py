"""Management command to load data from fixture dump."""

import os
from django.core.management.base import BaseCommand
from django.core import management


class Command(BaseCommand):
    """Publish command to load data from fixture dump."""

    help = "Load data from the test fixture and create an admin user."

    def add_arguments(self, parser):
        """Add arguments for `dev_load_and_build`."""
        parser.add_argument("-u", "--user", type=str, required=True, help="Username to create.")
        parser.add_argument("-p", "--password", type=str, required=True, help="Password to create.")
        parser.add_argument("-e", "--email", type=str, required=False, help="Email to create.")

    def handle(self, *args, **kwargs):
        """Add handler for `dev_load_and_build`."""
        user = kwargs["user"]
        password = kwargs["password"]
        email = kwargs.get("email")
        if not email:
            email = "email@example.com"
        management.call_command("flush", interactive=False)
        management.call_command("loaddata", "nautobot_ssot/fixtures/nautobot_dump.json")
        os.environ.setdefault("DJANGO_SUPERUSER_PASSWORD", password)
        management.call_command("createsuperuser", "--noinput", f"--email={email}", f"--username={user}")
