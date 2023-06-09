# Disable dispatcher from chatops unused. # pylint: disable=unused-argument
"""Chat Ops Worker."""
import uuid

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django_rq import job
from nautobot.core.settings_funcs import is_truthy
from nautobot.extras.models import JobResult
from nautobot_chatops.choices import CommandStatusChoices
from nautobot_chatops.dispatchers import Dispatcher
from nautobot_chatops.workers import handle_subcommands, subcommand_of

from nautobot_ssot_ipfabric.jobs import IpFabricDataSource

# from nautobot.dcim.models import Site

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot_ipfabric", {})
NAUTOBOT_HOST = CONFIG.get("nautobot_host")

BASE_CMD = "ipfabric"
IPFABRIC_LOGO_PATH = "nautobot_ssot_ipfabric/ipfabric_logo.png"
IPFABRIC_LOGO_ALT = "IPFabric Logo"


def prompt_for_bool(dispatcher: Dispatcher, action_id: str, help_text: str):
    """Prompt the user to select a True or False choice."""
    choices = [("Yes", "True"), ("No", "False")]
    dispatcher.prompt_from_menu(action_id, help_text, choices, default=("Yes", "True"))
    return False


# def prompt_for_site(dispatcher: Dispatcher, action_id: str, help_text: str, sites=None, offset=0):
#     """Prompt the user to select a valid site from a drop-down menu."""
#     if sites is None:
#         sites = Site.objects.all().order_by("name")
#     if not sites:
#         dispatcher.send_error("No sites were found")
#         return (CommandStatusChoices.STATUS_FAILED, "No sites found")
#     choices = [(f"{site.name}: {site.name}", site.name) for site in sites]
#     return dispatcher.prompt_from_menu(action_id, help_text, choices, offset=offset)


def ipfabric_logo(dispatcher):
    """Construct an image_element containing the locally hosted IP Fabric logo."""
    return dispatcher.image_element(dispatcher.static_url(IPFABRIC_LOGO_PATH), alt_text=IPFABRIC_LOGO_ALT)


@job("default")
def ipfabric(subcommand, **kwargs):
    """Interact with ipfabric plugin."""
    return handle_subcommands("ipfabric", subcommand, **kwargs)


@subcommand_of("ipfabric")
def ssot_sync_to_nautobot(
    dispatcher,
    dry_run=None,
    safe_delete_mode=None,
    sync_ipfabric_tagged_only=None,
):
    """Start an SSoT sync from IPFabric to Nautobot."""
    if dry_run is None:
        prompt_for_bool(dispatcher, f"{BASE_CMD} ssot-sync-to-nautobot", "Do you want to run a `Dry Run`?")
        return (CommandStatusChoices.STATUS_SUCCEEDED, "Success")

    if safe_delete_mode is None:
        prompt_for_bool(
            dispatcher, f"{BASE_CMD} ssot-sync-to-nautobot {dry_run}", "Do you want to run in `Safe Delete Mode`?"
        )
        return (CommandStatusChoices.STATUS_SUCCEEDED, "Success")

    if sync_ipfabric_tagged_only is None:
        prompt_for_bool(
            dispatcher,
            f"{BASE_CMD} ssot-sync-to-nautobot {dry_run} {safe_delete_mode}",
            "Do you want to sync against `ssot-tagged-from-ipfabric` tagged objects only?",
        )
        return (CommandStatusChoices.STATUS_SUCCEEDED, "Success")

    # if site_filter is None:
    #     prompt_for_site(
    #         dispatcher,
    #         f"{BASE_CMD} ssot-sync-to-nautobot {dry_run} {safe_delete_mode} {sync_ipfabric_tagged_only}",
    #         "Select a Site to use as an optional filter?",
    #     )
    #     return (CommandStatusChoices.STATUS_SUCCEEDED, "Success")

    # Implement filter in future release
    site_filter = False

    data = {
        "debug": False,
        "dry_run": is_truthy(dry_run),
        "safe_delete_mode": is_truthy(safe_delete_mode),
        "sync_ipfabric_tagged_only": is_truthy(sync_ipfabric_tagged_only),
        "site_filter": site_filter,
    }

    sync_job = IpFabricDataSource()

    sync_job.job_result = JobResult(
        name=sync_job.class_path,
        obj_type=ContentType.objects.get(
            app_label="extras",
            model="job",
        ),
        job_id=uuid.uuid4(),
    )
    sync_job.job_result.validated_save()

    dispatcher.send_markdown(
        f"Stand by {dispatcher.user_mention()}, I'm running your sync with options set to `Dry Run`: {dry_run}, `Safe Delete Mode`: {safe_delete_mode}. `Sync Tagged Only`: {sync_ipfabric_tagged_only}",
        ephemeral=True,
    )

    sync_job.run(data, commit=True)
    sync_job.post_run()
    sync_job.job_result.set_status(status="completed" if not sync_job.failed else "failed")
    sync_job.job_result.validated_save()

    blocks = [
        *dispatcher.command_response_header(
            "ipfabric",
            "ssot-sync-to-nautobot",
            [
                ("Dry Run", str(dry_run)),
                ("Safe Delete Mode", str(safe_delete_mode)),
                ("Sync IPFabric Tagged Only", str(sync_ipfabric_tagged_only)),
            ],
            "sync job",
            ipfabric_logo(dispatcher),
        ),
    ]
    dispatcher.send_blocks(blocks)
    if sync_job.job_result.status == "completed":
        dispatcher.send_markdown(
            f"Sync completed succesfully. Here is the link to your job: {NAUTOBOT_HOST}{sync_job.sync.get_absolute_url()}."
        )
    else:
        dispatcher.send_warning(
            f"Sync failed. Here is the link to your job: {NAUTOBOT_HOST}{sync_job.sync.get_absolute_url()}"
        )
    return CommandStatusChoices.STATUS_SUCCEEDED
