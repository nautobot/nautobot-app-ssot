"""Nautobot adapter for OpenShift integration."""
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
    """DiffSync adapter for Nautobot."""
    
    # Define model classes
    tenant = NautobotTenant
    device = NautobotDevice
    cluster = NautobotCluster
    virtualmachine = NautobotVirtualMachine
    ipaddress = NautobotIPAddress
    service = NautobotService
    
    # Define top-level models
    top_level = ["tenant", "cluster", "device", "virtualmachine", "service"]
    
    # Define required Nautobot objects
    openshift_cluster_type: Optional[ClusterType] = None
    openshift_manufacturer: Optional[Manufacturer] = None
    openshift_platform: Optional[Platform] = None
    openshift_device_type: Optional[DeviceType] = None
    openshift_device_role: Optional[DeviceRole] = None
    openshift_site: Optional[Site] = None
    status_active: Optional[Status] = None
    
    def __init__(self, *args, job=None, sync=None, **kwargs):
        """Initialize the Nautobot adapter."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.job_result = JobResult.objects.get(id=self.job.job_result.id)
        
    def load_initial_data(self):
        """Load or create required Nautobot objects."""
        # Get or create statuses
        self.status_active = Status.objects.get_or_create(
            name="Active",
            defaults={"color": "4caf50"}
        )[0]
        
        # Get or create manufacturer
        self.openshift_manufacturer = Manufacturer.objects.get_or_create(
            name="Red Hat",
            defaults={"description": "Red Hat, Inc."}
        )[0]
        
        # Get or create platform
        self.openshift_platform = Platform.objects.get_or_create(
            name="OpenShift",
            defaults={
                "manufacturer": self.openshift_manufacturer,
                "description": "Red Hat OpenShift Container Platform"
            }
        )[0]
        
        # Get or create cluster type
        self.openshift_cluster_type = ClusterType.objects.get_or_create(
            name="OpenShift",
            defaults={"description": "OpenShift Container Platform Cluster"}
        )[0]
        
        # Get or create device type
        self.openshift_device_type = DeviceType.objects.get_or_create(
            model="OpenShift Node",
            manufacturer=self.openshift_manufacturer,
            defaults={"u_height": 0}  # Virtual device
        )[0]
        
        # Get or create device role
        self.openshift_device_role = DeviceRole.objects.get_or_create(
            name="OpenShift Node",
            defaults={"color": "ff5722"}
        )[0]
        
        # Get or create site
        self.openshift_site = Site.objects.get_or_create(
            name="OpenShift Cloud",
            defaults={
                "status": self.status_active,
                "description": "Virtual site for OpenShift resources"
            }
        )[0]
    
    def load(self):
        """Load existing data from Nautobot."""
        self.job.logger.info("Loading data from Nautobot")
        
        # Load initial required objects
        self.load_initial_data()
        
        # Load tenants created from OpenShift
        self._load_tenants()
        
        # Load clusters
        self._load_clusters()
        
        # Load devices representing OpenShift nodes
        self._load_devices()
        
        # Load VMs from KubeVirt
        self._load_virtual_machines()
        
        # Load services
        self._load_services()
        
        # Load IP addresses
        self._load_ip_addresses()
    
    def _load_tenants(self):
        """Load tenants that were created from OpenShift projects."""
        # Filter tenants by custom field or tag to identify OpenShift-synced ones
        tenants = Tenant.objects.filter(
            custom_field_data__openshift_namespace__isnull=False
        )
        
        for tenant in tenants:
            self.add(self.tenant(
                name=tenant.name,
                description=tenant.description or "",
                custom_fields=tenant.custom_field_data
            ))
            self.job.logger.debug(f"Loaded tenant: {tenant.name}")
    
    def _load_clusters(self):
        """Load OpenShift clusters."""
        clusters = Cluster.objects.filter(cluster_type=self.openshift_cluster_type)
        
        for cluster in clusters:
            self.add(self.cluster(
                name=cluster.name,
                cluster_type=cluster.cluster_type.name,
                site=cluster.site.name if cluster.site else None
            ))
            self.job.logger.debug(f"Loaded cluster: {cluster.name}")
    
    def _load_devices(self):
        """Load devices representing OpenShift nodes."""
        devices = Device.objects.filter(
            device_role=self.openshift_device_role,
            platform=self.openshift_platform
        )
        
        for device in devices:
            self.add(self.device(
                name=device.name,
                device_type=device.device_type.model,
                device_role=device.device_role.name,
                platform=device.platform.name if device.platform else None,
                site=device.site.name,
                status=device.status.name,
                primary_ip4=str(device.primary_ip4.address.ip) if device.primary_ip4 else None,
                custom_fields=device.custom_field_data
            ))
            self.job.logger.debug(f"Loaded device: {device.name}")
    
    def _load_virtual_machines(self):
        """Load virtual machines from KubeVirt."""
        # Filter VMs by cluster type or custom field
        vms = VirtualMachine.objects.filter(
            cluster__cluster_type=self.openshift_cluster_type
        )
        
        for vm in vms:
            self.add(self.virtualmachine(
                name=vm.name,
                cluster=vm.cluster.name if vm.cluster else None,
                status=vm.status.name,
                vcpus=vm.vcpus,
                memory=vm.memory,
                disk=vm.disk,
                primary_ip4=str(vm.primary_ip4.address.ip) if vm.primary_ip4 else None,
                platform=vm.platform.name if vm.platform else None,
                custom_fields=vm.custom_field_data
            ))
            self.job.logger.debug(f"Loaded VM: {vm.name}")
    
    def _load_services(self):
        """Load services."""
        # Services would need custom fields to identify OpenShift-synced ones
        services = Service.objects.filter(
            custom_field_data__openshift_service__isnull=False
        )
        
        for service in services:
            self.add(self.service(
                name=service.name,
                protocol=service.protocol,
                ports=service.ports,
                description=service.description or "",
                custom_fields=service.custom_field_data
            ))
            self.job.logger.debug(f"Loaded service: {service.name}")
    
    def _load_ip_addresses(self):
        """Load IP addresses."""
        # Load IPs associated with OpenShift devices and VMs
        ips = IPAddress.objects.filter(
            device__device_role=self.openshift_device_role
        ) | IPAddress.objects.filter(
            virtual_machine__cluster__cluster_type=self.openshift_cluster_type
        )
        
        for ip in ips:
            self.add(self.ipaddress(
                address=str(ip.address),
                status=ip.status.name,
                description=ip.description or "",
                custom_fields=ip.custom_field_data
            ))
            self.job.logger.debug(f"Loaded IP: {ip.address}")
