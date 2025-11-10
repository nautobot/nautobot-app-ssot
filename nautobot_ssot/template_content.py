"""App template content extensions of base Nautobot views."""

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from nautobot.apps.ui import Button, TemplateExtension
from nautobot.core.views.utils import get_obj_from_context
from nautobot.extras.models import Job

from nautobot_ssot.models import Sync, SyncRecord
from nautobot_ssot.tables import SyncRecordTable

# pylint: disable=abstract-method


class JobResultSyncLink(TemplateExtension):
    """Add button linking to Sync data for relevant JobResults."""

    model = "extras.jobresult"

    def buttons(self):
        """Inject a custom button into the JobResult detail view, if applicable."""
        try:
            sync = Sync.objects.get(job_result=self.context["object"])
            return f"""
                <div class="btn-group">
                    <a href="{reverse('plugins:nautobot_ssot:sync', kwargs={'pk': sync.pk})}" class="btn btn-primary">
                        <span class="mdi mdi-database-sync-outline"></span> SSoT Sync Details
                    </a>
                </div>
            """
        except Sync.DoesNotExist:
            return ""


class ProcessRecordButton(Button):  # pylint: disable=abstract-method
    """Button for processing a Sync Record."""

    def __init__(self, *args, **kwargs):
        """Initialize the Process Record button."""
        super().__init__(label="Process Record", icon="mdi-import", color="info", weight=100, *args, **kwargs)

    def get_link(self, context):
        """Generate the URL to run Job with Sync Record pre-selected."""
        record = get_obj_from_context(context)
        job = Job.objects.get(name="Process Sync Records")
        # _job_result = JobResult.enqueue_job(job, context["request"].user, records=[record.id])
        # Generate a URL for Process Sync Records Job with the record ID as a parameter
        return f"/extras/jobs/{job.id}/run/?records={record.id}"

    def should_render(self, context):
        """Only render if the user has permissions to change SyncRecords."""
        user = context["request"].user
        # Check if user has permission to add a layout
        return user.has_perm("nautobot_ssot.change_syncrecord")


class SyncRecordsJobButton(TemplateExtension):  # pylint: disable=abstract-method
    """Class to modify FailedSSoT list view."""

    model = "nautobot_ssot.syncrecord"

    object_detail_buttons = [ProcessRecordButton()]


class BaseSyncRecordTabExtension(TemplateExtension):
    """Base class for SyncRecord tab extensions."""

    def get_extra_context(self, context):
        """Provide extra context for the SyncRecord tab."""
        obj = get_obj_from_context(context, "object")
        ct = ContentType.objects.get_for_model(obj)
        sync_records = SyncRecord.objects.filter(
            synced_object_id=obj.id,
            synced_object_type=ct,
        ).order_by("-timestamp")
        record_table = SyncRecordTable(sync_records)
        return {"syncrecord_table": record_table}

    def detail_tabs(self):
        """Add a Configuration Compliance tab to the Device detail view if the Configuration Compliance associated to it."""
        app_label, model = self.model.split(".")
        try:
            if SyncRecord.objects.filter(
                synced_object_id=self.context["object"].id,
                synced_object_type__app_label=app_label,
                synced_object_type__model=model,
            ).exists():
                return [
                    {
                        "title": "Sync History",
                        "url": reverse(
                            "plugins:nautobot_ssot:syncrecord_history",
                            kwargs={
                                "pk": self.context["object"].id,
                            },
                        ),
                    }
                ]
        except ObjectDoesNotExist:
            return []

        return []


class LocationTypeSyncRecordTabExtension(BaseSyncRecordTabExtension):
    """Add Sync History tab to LocationType detail view."""

    model = "dcim.locationtype"


class LocationSyncRecordTabExtension(BaseSyncRecordTabExtension):
    """Add Sync History tab to Location detail view."""

    model = "dcim.location"


class ManufacturerSyncRecordTabExtension(BaseSyncRecordTabExtension):
    """Add Sync History tab to Manufacturer detail view."""

    model = "dcim.manufacturer"


class DeviceTypeSyncRecordTabExtension(BaseSyncRecordTabExtension):
    """Add Sync History tab to DeviceType detail view."""

    model = "dcim.devicetype"


class DeviceSyncRecordTabExtension(BaseSyncRecordTabExtension):
    """Add Sync History tab to Device detail view."""

    model = "dcim.device"


class InterfaceSyncRecordTabExtension(BaseSyncRecordTabExtension):
    """Add Sync History tab to Device detail view."""

    model = "dcim.interface"


class PlatformSyncRecordTabExtension(BaseSyncRecordTabExtension):
    """Add Sync History tab to Platform detail view."""

    model = "dcim.platform"


class SoftwareVersionSyncRecordTabExtension(BaseSyncRecordTabExtension):
    """Add Sync History tab to SoftwareVersion detail view."""

    model = "dcim.softwareversion"


class StatusSyncRecordTabExtension(BaseSyncRecordTabExtension):
    """Add Sync History tab to Status detail view."""

    model = "extras.status"


class RoleSyncRecordTabExtension(BaseSyncRecordTabExtension):
    """Add Sync History tab to Status detail view."""

    model = "extras.role"


class NamespaceSyncRecordTabExtension(BaseSyncRecordTabExtension):
    """Add Sync History tab to Namespace detail view."""

    model = "ipam.namespace"


class PrefixSyncRecordTabExtension(BaseSyncRecordTabExtension):
    """Add Sync History tab to Prefix detail view."""

    model = "ipam.prefix"


class IPAddressSyncRecordTabExtension(BaseSyncRecordTabExtension):
    """Add Sync History tab to IPAddress detail view."""

    model = "ipam.ipaddress"


class VRFSyncRecordTabExtension(BaseSyncRecordTabExtension):
    """Add Sync History tab to VRF detail view."""

    model = "ipam.vrf"


class VLANSyncRecordTabExtension(BaseSyncRecordTabExtension):
    """Add Sync History tab to VLAN detail view."""

    model = "ipam.vlan"


class VLANGroupSyncRecordTabExtension(BaseSyncRecordTabExtension):
    """Add Sync History tab to VLANGroup detail view."""

    model = "ipam.vlangroup"


class TenantSyncRecordTabExtension(BaseSyncRecordTabExtension):
    """Add Sync History tab to Tenant detail view."""

    model = "tenancy.tenant"


class VirtualMachineSyncRecordTabExtension(BaseSyncRecordTabExtension):
    """Add Sync History tab to VirtualMachine detail view."""

    model = "virtualization.virtualmachine"


template_extensions = [
    JobResultSyncLink,
    SyncRecordsJobButton,
    LocationTypeSyncRecordTabExtension,
    LocationSyncRecordTabExtension,
    ManufacturerSyncRecordTabExtension,
    DeviceTypeSyncRecordTabExtension,
    DeviceSyncRecordTabExtension,
    InterfaceSyncRecordTabExtension,
    PlatformSyncRecordTabExtension,
    SoftwareVersionSyncRecordTabExtension,
    StatusSyncRecordTabExtension,
    RoleSyncRecordTabExtension,
    NamespaceSyncRecordTabExtension,
    PrefixSyncRecordTabExtension,
    IPAddressSyncRecordTabExtension,
    VRFSyncRecordTabExtension,
    VLANSyncRecordTabExtension,
    VLANGroupSyncRecordTabExtension,
    TenantSyncRecordTabExtension,
    VirtualMachineSyncRecordTabExtension,
]
