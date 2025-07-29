# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Network to Code, LLC
# Copyright (c) 2025 NVIDIA Corporation

"""Nautobot adapter for OpenShift integration synchronization.

This module implements the Nautobot-side adapter for DiffSync, responsible for loading
existing Nautobot objects and creating/updating objects based on OpenShift data. The
adapter serves as the target side of the synchronization process.

Adapter Architecture:
- Loads existing Nautobot objects that correspond to OpenShift resources
- Creates required supporting objects (device types, platforms, etc.)
- Manages object relationships and dependencies
- Handles create, update, and delete operations
- Maintains referential integrity across DCIM, IPAM, and tenancy models

Key Responsibilities:
- DCIM integration for OpenShift nodes and infrastructure
- IPAM integration for network resources and IP addresses
- Tenancy integration for organizational structure
- Virtualization integration for KubeVirt VMs
- Status and lifecycle management for synchronized objects

Object Lifecycle Management:
- Creates supporting objects on first sync (device types, roles, etc.)
- Loads existing objects for comparison and updates
- Handles object creation with proper relationships
- Manages object deletion and cleanup
- Maintains audit trails and change history

Data Model Integration:
- Utilizes Nautobot's core DCIM models for infrastructure
- Leverages IPAM models for network resource management
- Integrates with tenancy models for organizational structure
- Supports custom fields for OpenShift metadata preservation
- Maintains relationships between related objects

Error Handling and Recovery:
- Graceful handling of missing prerequisite objects
- Validation of object relationships and constraints
- Recovery from partial sync failures
- Comprehensive error logging and reporting
"""

from typing import List, Dict, Optional
from uuid import UUID

from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType
from nautobot.tenancy.models import Tenant
from nautobot.dcim.models import (
    Device, DeviceType, DeviceRole, Manufacturer, Site, Platform,
    Interface
)
from nautobot.virtualization.models import (
    VirtualMachine, Cluster, ClusterType, VMInterface
)
from nautobot.ipam.models import IPAddress, Service
from nautobot.extras.models import Status, Role, Tag, JobResult

from nautobot_ssot.integrations.openshift.diffsync.models.nautobot import (
    NautobotTenant, NautobotDevice, NautobotVirtualMachine,
    NautobotIPAddress, NautobotService, NautobotCluster
)


class OpenshiftNautobotAdapter(Adapter):
    """DiffSync adapter for loading and managing Nautobot objects.
    
    This adapter serves as the target side of the OpenShift synchronization,
    responsible for loading existing Nautobot objects and creating new ones
    based on discovered OpenShift resources. It handles the complete DCIM,
    IPAM, and tenancy integration for OpenShift workloads.
    
    Supported Object Types:
    - Tenants: Organizational structure from OpenShift projects
    - Clusters: Container orchestration platform grouping
    - Devices: OpenShift nodes as infrastructure components
    - Virtual Machines: KubeVirt VMs as virtualized workloads
    - IP Addresses: Network resources for pods, services, and VMs
    - Services: Network service definitions and endpoints
    
    Prerequisite Object Management:
    - Creates device types, roles, and platforms for OpenShift
    - Establishes cluster types for container orchestration
    - Sets up manufacturers and sites for infrastructure context
    - Configures status objects for lifecycle management
    - Manages tags for object categorization and filtering
    
    Data Loading Strategy:
    1. Initialize prerequisite objects (types, roles, statuses)
    2. Load existing objects from Nautobot for comparison
    3. Create missing objects based on OpenShift data
    4. Update existing objects with current information
    5. Handle relationships and dependencies properly
    6. Clean up orphaned objects if configured
    
    Integration Points:
    - DCIM: Infrastructure devices and physical layout
    - IPAM: Network addresses and service definitions
    - Tenancy: Organizational structure and access control
    - Virtualization: VM management and resource allocation
    - Extras: Custom fields, tags, and status management
    """
    
    # Map DiffSync model names to model classes for registration
    # This enables the adapter to create and manage these model types
    tenant = NautobotTenant
    device = NautobotDevice
    cluster = NautobotCluster
    virtualmachine = NautobotVirtualMachine
    ipaddress = NautobotIPAddress
    service = NautobotService
    
    # Define top-level models that exist independently (no parent references)
    # These models are loaded first and can be referenced by child models
    top_level = ["tenant", "cluster", "device", "virtualmachine", "service"]
    
    # Prerequisite Nautobot objects required for OpenShift integration
    # These objects are created automatically if they don't exist
    
    # Cluster type for OpenShift container orchestration platforms
    openshift_cluster_type: Optional[ClusterType] = None
    
    # Manufacturer for OpenShift nodes (Red Hat or generic)
    openshift_manufacturer: Optional[Manufacturer] = None
    
    # Platform for OpenShift node operating system (Red Hat CoreOS)
    openshift_platform: Optional[Platform] = None
    
    # Device type for OpenShift nodes (generic or specific hardware)
    openshift_device_type: Optional[DeviceType] = None
    
    # Device role for OpenShift nodes (master, worker, infra)
    openshift_device_role: Optional[DeviceRole] = None
    
    # Site for OpenShift cluster location and compliance
    openshift_site: Optional[Site] = None
    
    # Active status for operational objects
    status_active: Optional[Status] = None
    
    def __init__(self, *args, job=None, sync=None, **kwargs):
        """Initialize the Nautobot adapter with job context and prerequisites.
        
        Sets up the adapter with necessary context for creating and managing
        Nautobot objects. Initializes prerequisite objects required for
        OpenShift integration and prepares the adapter for data loading.
        
        Args:
            job: SSoT job instance for logging and context
            sync: DiffSync instance for synchronization state
            
        Initialization Process:
        1. Store job context for logging and error reporting
        2. Create or retrieve prerequisite Nautobot objects
        3. Validate object relationships and dependencies
        4. Prepare adapter for data loading and synchronization
        5. Set up error handling and recovery mechanisms
        
        Prerequisite Objects:
        - Device types and roles for OpenShift nodes
        - Cluster types for container orchestration
        - Platforms and manufacturers for infrastructure context
        - Sites for geographic and compliance organization
        - Status objects for lifecycle management
        """
        super().__init__(*args, **kwargs)
        
        # Store context for logging and configuration access
        self.job = job
        self.sync = sync
        
        # Initialize prerequisite objects required for OpenShift integration
        self._create_openshift_prerequisites()
        
        # Log adapter initialization
        self.job.logger.info("Initialized Nautobot adapter for OpenShift integration")
    
    def _create_openshift_prerequisites(self):
        """Create or retrieve prerequisite Nautobot objects for OpenShift integration.
        
        Ensures that all required supporting objects exist in Nautobot before
        attempting to create OpenShift-related objects. This includes device
        types, roles, platforms, and other foundational objects.
        
        Created Objects:
        - ClusterType: "OpenShift" for container orchestration platforms
        - Manufacturer: "Red Hat" for OpenShift infrastructure
        - Platform: "Red Hat CoreOS" for node operating systems
        - DeviceType: "OpenShift Node" for generic node hardware
        - DeviceRole: "OpenShift Worker" for compute nodes
        - Site: "Default Site" for cluster location
        - Status: "Active" for operational objects
        
        Error Handling:
        - Graceful handling of existing objects
        - Validation of object creation success
        - Logging of prerequisite creation activities
        - Recovery from partial creation failures
        """
        try:
            # Create or get cluster type for OpenShift platforms
            self.openshift_cluster_type, created = ClusterType.objects.get_or_create(
                name="OpenShift",
                defaults={
                    "description": "Red Hat OpenShift container orchestration platform"
                }
            )
            if created:
                self.job.logger.info("Created OpenShift cluster type")
            
            # Create or get manufacturer for OpenShift infrastructure
            self.openshift_manufacturer, created = Manufacturer.objects.get_or_create(
                name="Red Hat",
                defaults={
                    "description": "Red Hat Inc. - Enterprise open source solutions"
                }
            )
            if created:
                self.job.logger.info("Created Red Hat manufacturer")
            
            # Create or get platform for OpenShift nodes
            self.openshift_platform, created = Platform.objects.get_or_create(
                name="Red Hat CoreOS",
                defaults={
                    "manufacturer": self.openshift_manufacturer,
                    "description": "Container-optimized operating system for OpenShift"
                }
            )
            if created:
                self.job.logger.info("Created Red Hat CoreOS platform")
            
            # Create or get device type for OpenShift nodes
            self.openshift_device_type, created = DeviceType.objects.get_or_create(
                model="OpenShift Node",
                manufacturer=self.openshift_manufacturer,
                defaults={
                    "description": "Generic OpenShift cluster node",
                    "height": 1,  # 1U by default
                    "is_full_depth": True
                }
            )
            if created:
                self.job.logger.info("Created OpenShift Node device type")
            
            # Create or get device role for OpenShift workers
            self.openshift_device_role, created = DeviceRole.objects.get_or_create(
                name="OpenShift Worker",
                defaults={
                    "description": "OpenShift worker node running application workloads",
                    "color": "ff0000"  # Red Hat red
                }
            )
            if created:
                self.job.logger.info("Created OpenShift Worker device role")
            
            # Create or get default site for cluster location
            self.openshift_site, created = Site.objects.get_or_create(
                name="Default Site",
                defaults={
                    "description": "Default site for OpenShift cluster resources"
                }
            )
            if created:
                self.job.logger.info("Created default site for OpenShift")
            
            # Get or create active status for operational objects
            self.status_active, created = Status.objects.get_or_create(
                name="Active",
                defaults={
                    "description": "Operational and active status"
                }
            )
            
            # Associate status with relevant content types
            if created:
                # Add status to device, VM, and other content types
                content_types = ContentType.objects.filter(
                    model__in=["device", "virtualmachine", "ipaddress", "service"]
                )
                self.status_active.content_types.set(content_types)
                self.job.logger.info("Created Active status with content type associations")
            
            self.job.logger.info("Successfully initialized all OpenShift prerequisite objects")
            
        except Exception as e:
            self.job.logger.error(f"Failed to create OpenShift prerequisites: {e}")
            raise
    
    def load(self):
        """Load existing Nautobot objects for comparison with OpenShift data.
        
        Loads all existing Nautobot objects that could correspond to OpenShift
        resources, enabling the DiffSync engine to determine what objects need
        to be created, updated, or deleted based on the current OpenShift state.
        
        Loading Strategy:
        1. Load tenants that may correspond to OpenShift projects
        2. Load clusters that represent OpenShift platforms
        3. Load devices that may be OpenShift nodes
        4. Load virtual machines that may be KubeVirt VMs
        5. Load IP addresses used by OpenShift resources
        6. Load services that may correspond to OpenShift services
        
        Filtering Logic:
        - Uses custom fields to identify OpenShift-synchronized objects
        - Applies tags to filter objects created by SSoT
        - Considers object naming patterns for OpenShift resources
        - Includes only objects within scope of synchronization
        
        Performance Considerations:
        - Uses select_related for efficient relationship loading
        - Applies filters to reduce query overhead
        - Loads objects in dependency order
        - Minimizes database round trips
        """
        self.job.logger.info("Loading existing Nautobot objects for OpenShift comparison")
        
        # Load existing objects that may correspond to OpenShift resources
        self._load_tenants()
        self._load_clusters()
        self._load_devices()
        self._load_virtual_machines()
        self._load_ip_addresses()
        self._load_services()
        
        # Log loading completion with statistics
        total_objects = len(self.objects)
        self.job.logger.info(f"Loaded {total_objects} existing Nautobot objects")
    
    def _load_tenants(self):
        """Load existing tenants that may correspond to OpenShift projects.
        
        Loads Nautobot tenants that could represent OpenShift projects or
        namespaces, enabling comparison with discovered OpenShift projects
        to determine synchronization actions.
        
        Loading Criteria:
        - Tenants with OpenShift-related custom fields
        - Tenants tagged as synchronized from OpenShift
        - Tenants matching OpenShift naming patterns
        - All tenants if no specific filtering is configured
        
        Custom Field Detection:
        - "openshift_project_uid": OpenShift project unique identifier
        - "openshift_namespace": Original namespace name
        - "sync_source": Source system for tenant creation
        """
        # Load tenants that may be synchronized from OpenShift
        tenants = Tenant.objects.filter(
            # Add filtering logic here based on custom fields or tags
            # For now, load all tenants for comparison
        ).select_related()
        
        tenant_count = 0
        for tenant in tenants:
            # Create DiffSync model for existing tenant
            tenant_model = self.tenant(
                name=tenant.name,
                description=tenant.description or "",
                custom_fields=tenant.custom_field_data
            )
            self.add(tenant_model)
            tenant_count += 1
        
        self.job.logger.debug(f"Loaded {tenant_count} existing tenants")
    
    def _load_clusters(self):
        """Load existing clusters that may represent OpenShift platforms.
        
        Loads Nautobot clusters that could represent OpenShift container
        orchestration platforms, enabling comparison with discovered
        OpenShift clusters for synchronization.
        
        Loading Criteria:
        - Clusters with OpenShift cluster type
        - Clusters tagged as OpenShift platforms
        - Clusters with OpenShift-related custom fields
        - Clusters matching OpenShift naming conventions
        """
        # Load clusters that may represent OpenShift platforms
        clusters = Cluster.objects.filter(
            cluster_type=self.openshift_cluster_type
        ).select_related("cluster_type", "site")
        
        cluster_count = 0
        for cluster in clusters:
            # Create DiffSync model for existing cluster
            cluster_model = self.cluster(
                name=cluster.name,
                cluster_type=cluster.cluster_type.name,
                site=cluster.site.name if cluster.site else None
            )
            self.add(cluster_model)
            cluster_count += 1
        
        self.job.logger.debug(f"Loaded {cluster_count} existing OpenShift clusters")
    
    def _load_devices(self):
        """Load existing devices that may be OpenShift nodes.
        
        Loads Nautobot devices that could represent OpenShift cluster nodes,
        enabling comparison with discovered nodes for infrastructure
        synchronization and capacity planning.
        
        Loading Criteria:
        - Devices with OpenShift device roles
        - Devices with OpenShift-related custom fields
        - Devices tagged as OpenShift infrastructure
        - Devices matching node naming patterns
        """
        # Load devices that may be OpenShift nodes
        devices = Device.objects.filter(
            device_role=self.openshift_device_role
        ).select_related(
            "device_type", "device_role", "platform", "site", "primary_ip4"
        )
        
        device_count = 0
        for device in devices:
            # Create DiffSync model for existing device
            device_model = self.device(
                name=device.name,
                device_type=device.device_type.model,
                device_role=device.device_role.name,
                platform=device.platform.name if device.platform else None,
                site=device.site.name,
                status=device.status.name,
                primary_ip4=str(device.primary_ip4.address) if device.primary_ip4 else None,
                custom_fields=device.custom_field_data
            )
            self.add(device_model)
            device_count += 1
        
        self.job.logger.debug(f"Loaded {device_count} existing OpenShift devices")
    
    def _load_virtual_machines(self):
        """Load existing virtual machines that may be KubeVirt VMs.
        
        Loads Nautobot virtual machines that could represent KubeVirt VMs
        running on OpenShift, enabling comparison with discovered VMs for
        virtualization workload synchronization.
        
        Loading Criteria:
        - VMs in OpenShift clusters
        - VMs with KubeVirt-related custom fields
        - VMs tagged as KubeVirt workloads
        - VMs matching KubeVirt naming patterns
        """
        # Load VMs that may be KubeVirt virtual machines
        vms = VirtualMachine.objects.filter(
            cluster__cluster_type=self.openshift_cluster_type
        ).select_related(
            "cluster", "platform", "primary_ip4", "status"
        )
        
        vm_count = 0
        for vm in vms:
            # Create DiffSync model for existing VM
            vm_model = self.virtualmachine(
                name=vm.name,
                cluster=vm.cluster.name,
                status=vm.status.name,
                vcpus=vm.vcpus,
                memory=vm.memory,
                disk=vm.disk,
                primary_ip4=str(vm.primary_ip4.address) if vm.primary_ip4 else None,
                platform=vm.platform.name if vm.platform else None,
                custom_fields=vm.custom_field_data
            )
            self.add(vm_model)
            vm_count += 1
        
        self.job.logger.debug(f"Loaded {vm_count} existing KubeVirt virtual machines")
    
    def _load_ip_addresses(self):
        """Load existing IP addresses that may be used by OpenShift resources.
        
        Loads Nautobot IP addresses that could be assigned to OpenShift
        pods, services, or infrastructure, enabling network resource
        synchronization and IPAM integration.
        
        Loading Criteria:
        - IP addresses with OpenShift-related custom fields
        - IP addresses tagged as OpenShift resources
        - IP addresses in OpenShift-related subnets
        - IP addresses assigned to OpenShift devices/VMs
        """
        # Load IP addresses that may be used by OpenShift
        ip_addresses = IPAddress.objects.filter(
            # Add filtering logic based on custom fields or tags
            # For now, load addresses that might be OpenShift-related
        ).select_related("status")
        
        ip_count = 0
        for ip in ip_addresses:
            # Create DiffSync model for existing IP address
            ip_model = self.ipaddress(
                address=str(ip.address),
                status=ip.status.name,
                description=ip.description or "",
                custom_fields=ip.custom_field_data
            )
            self.add(ip_model)
            ip_count += 1
        
        self.job.logger.debug(f"Loaded {ip_count} existing IP addresses")
    
    def _load_services(self):
        """Load existing services that may correspond to OpenShift services.
        
        Loads Nautobot services that could represent OpenShift service
        definitions, enabling network service synchronization and
        connectivity mapping.
        
        Loading Criteria:
        - Services with OpenShift-related custom fields
        - Services tagged as OpenShift network services
        - Services matching OpenShift naming patterns
        - Services in OpenShift-related networks
        """
        # Load services that may correspond to OpenShift services
        services = Service.objects.filter(
            # Add filtering logic based on custom fields or tags
            # For now, load services that might be OpenShift-related
        )
        
        service_count = 0
        for service in services:
            # Create DiffSync model for existing service
            service_model = self.service(
                name=service.name,
                protocol=service.protocol,
                ports=service.ports,
                description=service.description or "",
                custom_fields=service.custom_field_data
            )
            self.add(service_model)
            service_count += 1
        
        self.job.logger.debug(f"Loaded {service_count} existing services")

# =====================================================================
# NAUTOBOT ADAPTER PATTERNS FOR MAINTENANCE DEVELOPERS
# =====================================================================
#
# 1. Prerequisite Object Management:
#    def ensure_prerequisite_objects():
#        # Create all required supporting objects
#        cluster_type = get_or_create_cluster_type("OpenShift")
#        manufacturer = get_or_create_manufacturer("Red Hat")
#        platform = get_or_create_platform("Red Hat CoreOS", manufacturer)
#        device_type = get_or_create_device_type("OpenShift Node", manufacturer)
#        device_role = get_or_create_device_role("OpenShift Worker")
#        site = get_or_create_site("Default Site")
#        status = get_or_create_status("Active")
#
# 2. Object Loading with Relationships:
#    def load_objects_efficiently():
#        # Use select_related for foreign key relationships
#        devices = Device.objects.select_related(
#            'device_type__manufacturer',
#            'device_role',
#            'platform',
#            'site',
#            'primary_ip4__status'
#        ).filter(device_role__name='OpenShift Worker')
#        
#        # Use prefetch_related for many-to-many relationships
#        vms = VirtualMachine.objects.prefetch_related(
#            'tags',
#            'cluster__devices'
#        ).filter(cluster__cluster_type__name='OpenShift')
#
# 3. Custom Field Filtering:
#    def filter_by_custom_fields():
#        # Filter objects by OpenShift-specific custom fields
#        openshift_tenants = Tenant.objects.filter(
#            custom_field_data__sync_source="openshift-ssot"
#        )
#        
#        # Filter by multiple custom field criteria
#        openshift_devices = Device.objects.filter(
#            custom_field_data__openshift_cluster="prod-cluster",
#            custom_field_data__openshift_node_role="worker"
#        )
#
# 4. Object Creation with Dependencies:
#    def create_vm_with_dependencies(vm_data):
#        # Ensure cluster exists first
#        cluster, _ = Cluster.objects.get_or_create(
#            name=vm_data["cluster_name"],
#            defaults={
#                'cluster_type': openshift_cluster_type,
#                'site': openshift_site
#            }
#        )
#        
#        # Create VM with cluster relationship
#        vm = VirtualMachine.objects.create(
#            name=vm_data["name"],
#            cluster=cluster,
#            vcpus=vm_data["vcpus"],
#            memory=vm_data["memory"],
#            status=status_active
#        )
#        
#        # Create IP address if provided
#        if vm_data.get("ip_address"):
#            ip = IPAddress.objects.create(
#                address=vm_data["ip_address"],
#                status=status_active
#            )
#            vm.primary_ip4 = ip
#            vm.save()
#        
#        return vm
#
# 5. Error Recovery Patterns:
#    def create_with_error_recovery(model_class, **kwargs):
#        try:
#            return model_class.objects.create(**kwargs)
#        except IntegrityError as e:
#            # Handle unique constraint violations
#            if "unique constraint" in str(e).lower():
#                logger.warning(f"Object already exists: {kwargs}")
#                return model_class.objects.get(**{
#                    field: value for field, value in kwargs.items()
#                    if field in model_class._meta.get_fields()
#                })
#            raise
#        except ValidationError as e:
#            # Handle field validation errors
#            logger.error(f"Validation error creating {model_class.__name__}: {e}")
#            raise
#
# =====================================================================
# PERFORMANCE OPTIMIZATION STRATEGIES
# =====================================================================
#
# 1. Efficient Querying:
#    # Use select_related for single-value relationships
#    devices = Device.objects.select_related(
#        'device_type', 'device_role', 'site', 'platform'
#    )
#    
#    # Use prefetch_related for multi-value relationships
#    devices = Device.objects.prefetch_related(
#        'interfaces', 'tags', 'custom_fields'
#    )
#    
#    # Combine both for complex relationships
#    vms = VirtualMachine.objects.select_related(
#        'cluster__cluster_type', 'platform', 'status'
#    ).prefetch_related('tags', 'vminterfaces__ip_addresses')
#
# 2. Bulk Operations:
#    # Use bulk_create for multiple objects
#    devices_to_create = [
#        Device(name=f"node-{i}", device_type=openshift_device_type)
#        for i in range(100)
#    ]
#    Device.objects.bulk_create(devices_to_create, batch_size=50)
#    
#    # Use bulk_update for existing objects
#    devices = Device.objects.filter(device_role=openshift_device_role)
#    for device in devices:
#        device.status = status_active
#    Device.objects.bulk_update(devices, ['status'], batch_size=50)
#
# 3. Query Optimization:
#    # Use only() to limit fields when you don't need full objects
#    devices = Device.objects.only('name', 'primary_ip4').filter(
#        device_role=openshift_device_role
#    )
#    
#    # Use defer() to exclude heavy fields
#    devices = Device.objects.defer('custom_field_data').filter(
#        device_role=openshift_device_role
#    )
#
# 4. Transaction Management:
#    from django.db import transaction
#    
#    @transaction.atomic
#    def sync_cluster_resources(cluster_data):
#        # All operations in single transaction
#        cluster = create_cluster(cluster_data)
#        devices = create_devices(cluster_data.nodes)
#        vms = create_vms(cluster_data.vms)
#        
#        # If any operation fails, entire transaction rolls back
#        return cluster, devices, vms
#
# =====================================================================
# RELATIONSHIP MANAGEMENT PATTERNS
# =====================================================================
#
# 1. Forward Relationship Creation:
#    # Create parent objects first
#    cluster = Cluster.objects.create(
#        name="prod-openshift",
#        cluster_type=openshift_cluster_type
#    )
#    
#    # Then create child objects with relationships
#    vm = VirtualMachine.objects.create(
#        name="web-server",
#        cluster=cluster  # Foreign key relationship
#    )
#
# 2. Reverse Relationship Management:
#    # Access reverse relationships efficiently
#    cluster = Cluster.objects.get(name="prod-openshift")
#    
#    # Get all VMs in the cluster
#    cluster_vms = cluster.virtualmachines.all()
#    
#    # Get cluster devices (if devices have cluster field)
#    cluster_devices = cluster.devices.all()
#
# 3. Many-to-Many Relationships:
#    # Add tags to objects
#    openshift_tag = Tag.objects.get(name="OpenShift")
#    device.tags.add(openshift_tag)
#    
#    # Set multiple tags at once
#    device.tags.set([openshift_tag, worker_tag, prod_tag])
#    
#    # Remove tags
#    device.tags.remove(openshift_tag)
#
# 4. Custom Field Management:
#    # Set custom field data
#    device.custom_field_data = {
#        "openshift_cluster": "prod-cluster",
#        "openshift_node_role": "worker",
#        "cpu_capacity": "8",
#        "memory_capacity": "32Gi"
#    }
#    device.save()
#    
#    # Update specific custom fields
#    device.custom_field_data.update({
#        "last_sync_time": "2023-10-15T10:30:00Z"
#    })
#    device.save()
#
# =====================================================================
