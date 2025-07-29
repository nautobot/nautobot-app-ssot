# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Network to Code, LLC
# Copyright (c) 2025 NVIDIA Corporation

"""Tables for OpenShift integration.

This module defines Django table configurations for displaying OpenShift SSoT
configurations in list views. Built on django-tables2, it provides sortable,
filterable table presentations with consistent Nautobot styling.

Architecture:
- Uses django-tables2 for declarative table definitions
- Inherits from Nautobot's BaseTable for consistent styling
- Provides specialized column types for different data formats
- Integrates with Nautobot's action button system

Key Features:
- Sortable columns for easy data organization
- Boolean columns with visual indicators (checkmarks/X marks)
- Link columns for navigation to detail views
- Action buttons for common operations (edit, delete, changelog)
- Responsive design for mobile and desktop viewing
- Integration with pagination and filtering systems

Column Types Used:
- LinkColumn: Creates clickable links to detail views
- BooleanColumn: Visual representation of boolean values
- ButtonsColumn: Action buttons for object operations
- Standard Column: Basic text/data display

User Experience:
- Quick scanning of configuration status via boolean columns
- Direct access to related resources via link columns
- Immediate access to common actions via button columns
- Consistent visual hierarchy with other Nautobot tables
"""
import django_tables2 as tables
from nautobot.apps.tables import BaseTable, BooleanColumn, ButtonsColumn

from .models import SSOTOpenshiftConfig


class SSOTOpenshiftConfigTable(BaseTable):
    """Table for displaying OpenShift configuration list views.
    
    This table provides a comprehensive overview of OpenShift SSoT configurations,
    showing essential information at a glance while providing easy access to
    detailed views and common actions.
    
    Design Principles:
    1. Essential Information First: Most important fields in leftmost columns
    2. Visual Indicators: Boolean columns provide quick status assessment
    3. Direct Navigation: Link columns enable quick access to details
    4. Actionable Interface: Button columns provide immediate access to operations
    
    Column Organization:
    - Identification: name, description, openshift_url
    - Status Flags: job_enabled, enable_sync_to_nautobot
    - Sync Options: All sync_* boolean fields for capability overview
    - Configuration: workload_types, namespace_filter
    - Actions: Standard edit/delete/changelog operations
    
    Responsive Behavior:
    - Essential columns shown on all screen sizes
    - Less critical columns hidden on smaller screens
    - Horizontal scrolling available for full table access
    - Touch-friendly button sizing on mobile devices
    """
    
    # =====================================================================
    # IDENTIFICATION AND NAVIGATION COLUMNS
    # =====================================================================
    
    name = tables.LinkColumn(
        verbose_name="Configuration Name",
        attrs={"a": {"class": "fw-bold"}},  # Bold font for primary identifier
    )
    
    openshift_url = tables.Column(
        accessor="openshift_instance__remote_url",
        verbose_name="OpenShift URL",
        attrs={"td": {"class": "font-monospace small"}},  # Monospace for URLs
    )
    
    # =====================================================================
    # STATUS AND CONTROL COLUMNS - Visual indicators for quick assessment
    # =====================================================================
    
    enable_sync_to_nautobot = BooleanColumn(
        orderable=False,  # Boolean columns don't benefit from sorting
        verbose_name="Sync Enabled",
        attrs={"th": {"class": "text-center"}, "td": {"class": "text-center"}},
    )
    
    job_enabled = BooleanColumn(
        orderable=False,
        verbose_name="Job Enabled", 
        attrs={"th": {"class": "text-center"}, "td": {"class": "text-center"}},
    )
    
    # =====================================================================
    # SYNC CAPABILITY COLUMNS - Show what resources will be synchronized
    # =====================================================================
    
    sync_namespaces = BooleanColumn(
        orderable=False,
        verbose_name="Namespaces",
        attrs={"th": {"class": "text-center"}, "td": {"class": "text-center"}},
    )
    
    sync_nodes = BooleanColumn(
        orderable=False,
        verbose_name="Nodes",
        attrs={"th": {"class": "text-center"}, "td": {"class": "text-center"}},
    )
    
    sync_containers = BooleanColumn(
        orderable=False,
        verbose_name="Containers",
        attrs={"th": {"class": "text-center"}, "td": {"class": "text-center"}},
    )
    
    sync_deployments = BooleanColumn(
        orderable=False,
        verbose_name="Deployments",
        attrs={"th": {"class": "text-center"}, "td": {"class": "text-center"}},
    )
    
    sync_services = BooleanColumn(
        orderable=False,
        verbose_name="Services",
        attrs={"th": {"class": "text-center"}, "td": {"class": "text-center"}},
    )
    
    sync_kubevirt_vms = BooleanColumn(
        orderable=False,
        verbose_name="KubeVirt VMs",
        attrs={"th": {"class": "text-center"}, "td": {"class": "text-center"}},
    )
    
    # =====================================================================
    # ACTION BUTTONS - Standard operations for each configuration
    # =====================================================================
    
    actions = ButtonsColumn(
        model=SSOTOpenshiftConfig,
        buttons=("changelog", "edit", "delete"),
        verbose_name="Actions",
    )
    
    class Meta(BaseTable.Meta):
        """Table metadata configuration.
        
        Inherits from BaseTable.Meta to get standard Nautobot table
        behavior including Bootstrap styling, responsive design,
        and consistent visual hierarchy.
        
        Field Configuration:
        - fields: All available columns (complete table functionality)
        - default_columns: Subset shown by default (responsive design)
        
        Column Selection Strategy:
        - Essential fields always visible (name, url, description)
        - Status flags visible for quick assessment
        - Sync options visible to understand capabilities
        - Configuration details available but initially hidden
        - Actions always available for immediate operations
        """
        model = SSOTOpenshiftConfig
        
        # All available columns - users can add via column selector
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
            "actions",
        )
        
        # Default columns shown initially - responsive design consideration
        default_columns = (
            "name",                      # Essential: Primary identifier
            "openshift_url",            # Essential: Connection info
            "description",              # Important: Purpose/context
            "enable_sync_to_nautobot",  # Status: Overall enablement
            "job_enabled",              # Status: Job availability
            "sync_namespaces",          # Capability: Core sync option
            "sync_nodes",               # Capability: Infrastructure sync
            "sync_containers",          # Capability: Workload sync
            "sync_deployments",         # Capability: Application sync
            "sync_services",            # Capability: Service sync
            "sync_kubevirt_vms",        # Capability: VM sync
            "workload_types",           # Configuration: Workload filter
            "actions",                  # Essential: User actions
        )
        
        # Additional table configuration
        attrs = {
            "class": "table table-hover table-sm",  # Bootstrap styling
            "id": "openshift-config-table",         # JavaScript targeting
        }
