"""Tables for OpenShift integration."""
import django_tables2 as tables
from nautobot.apps.tables import BaseTable, BooleanColumn, ButtonsColumn

from .models import SSOTOpenshiftConfig


class SSOTOpenshiftConfigTable(BaseTable):
    """Table for SSOTOpenshiftConfig."""
    
    name = tables.LinkColumn()
    openshift_url = tables.Column(accessor="openshift_instance__remote_url")
    enable_sync_to_nautobot = BooleanColumn(orderable=False)
    job_enabled = BooleanColumn(orderable=False)
    sync_namespaces = BooleanColumn(orderable=False)
    sync_nodes = BooleanColumn(orderable=False)
    sync_containers = BooleanColumn(orderable=False)
    sync_deployments = BooleanColumn(orderable=False)
    sync_services = BooleanColumn(orderable=False)
    sync_kubevirt_vms = BooleanColumn(orderable=False)
    actions = ButtonsColumn(SSOTOpenshiftConfig, buttons=("changelog", "edit", "delete"))
    
    class Meta(BaseTable.Meta):
        """Meta attributes."""
        model = SSOTOpenshiftConfig
        fields = (
            "name",
            "openshift_url",
            "description",
            "enable_sync_to_nautobot",
            "job_enabled",
            "sync_namespaces",
            "sync_nodes",
            "sync_containers",
            "sync_deployments",
            "sync_services",
            "sync_kubevirt_vms",
            "workload_types",
            "namespace_filter",
        )
        default_columns = (
            "name",
            "openshift_url",
            "description",
            "enable_sync_to_nautobot",
            "job_enabled",
            "sync_namespaces",
            "sync_nodes",
            "sync_containers",
            "sync_deployments",
            "sync_services",
            "sync_kubevirt_vms",
            "workload_types",
        )
