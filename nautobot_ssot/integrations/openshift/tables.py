"""Tables for OpenShift integration."""
import django_tables2 as tables
from nautobot.core.tables import BaseTable, ButtonsColumn, ToggleColumn
from nautobot_ssot.integrations.openshift.models import SSOTOpenshiftConfig


class SSOTOpenshiftConfigTable(BaseTable):
    """Table for SSOTOpenshiftConfig."""
    
    pk = ToggleColumn()
    name = tables.LinkColumn()
    actions = ButtonsColumn(
        model=SSOTOpenshiftConfig,
        buttons=("edit", "delete"),
    )
    
    class Meta:
        """Meta class for table."""
        model = SSOTOpenshiftConfig
        fields = (
            "pk",
            "name",
            "url",
            "description",
            "verify_ssl",
            "sync_namespaces",
            "sync_nodes",
            "sync_containers",
            "sync_deployments",
            "sync_services",
            "sync_kubevirt_vms",
            "workload_types",
            "actions",
        )
        default_columns = (
            "pk",
            "name",
            "url",
            "description",
            "verify_ssl",
            "sync_namespaces",
            "sync_nodes",
            "sync_containers",
            "sync_deployments",
            "sync_services",
            "sync_kubevirt_vms",
            "workload_types",
            "actions",
        )
