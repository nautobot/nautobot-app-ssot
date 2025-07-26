"""Nautobot DiffSync models for OpenShift integration."""
from typing import Optional, List, Dict, Any
from diffsync import DiffSyncModel


class NautobotTenant(DiffSyncModel):
    """DiffSync model for Nautobot Tenant."""
    
    _modelname = "nautobot_tenant"
    _identifiers = ("name",)
    _attributes = ("description", "custom_fields")
    
    name: str
    description: Optional[str] = ""
    custom_fields: Dict[str, Any] = {}
    
    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create a new tenant in Nautobot."""
        from nautobot.tenancy.models import Tenant
        
        tenant = Tenant.objects.create(
            name=ids["name"],
            description=attrs.get("description", ""),
            custom_field_data=attrs.get("custom_fields", {})
        )
        return super().create(adapter=adapter, ids=ids, attrs=attrs)


class NautobotCluster(DiffSyncModel):
    """DiffSync model for Nautobot Cluster."""
    
    _modelname = "nautobot_cluster"
    _identifiers = ("name",)
    _attributes = ("cluster_type", "site")
    
    name: str
    cluster_type: str
    site: Optional[str] = None
    
    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create a new cluster in Nautobot."""
        from nautobot.virtualization.models import Cluster
        
        cluster = Cluster.objects.create(
            name=ids["name"],
            cluster_type=adapter.openshift_cluster_type,
            site=adapter.openshift_site if attrs.get("site") else None
        )
        return super().create(adapter=adapter, ids=ids, attrs=attrs)


class NautobotDevice(DiffSyncModel):
    """DiffSync model for Nautobot Device."""
    
    _modelname = "nautobot_device"
    _identifiers = ("name",)
    _attributes = (
        "device_type", "device_role", "platform", "site",
        "status", "primary_ip4", "custom_fields"
    )
    
    name: str
    device_type: str
    device_role: str
    platform: Optional[str] = None
    site: str
    status: str = "Active"
    primary_ip4: Optional[str] = None
    custom_fields: Dict[str, Any] = {}
    
    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create a new device in Nautobot."""
        from nautobot.dcim.models import Device
        
        device = Device.objects.create(
            name=ids["name"],
            device_type=adapter.openshift_device_type,
            device_role=adapter.openshift_device_role,
            platform=adapter.openshift_platform,
            site=adapter.openshift_site,
            status=adapter.status_active,
            custom_field_data=attrs.get("custom_fields", {})
        )
        
        # Create primary IP if provided
        if attrs.get("primary_ip4"):
            from nautobot.ipam.models import IPAddress
            ip = IPAddress.objects.create(
                address=attrs["primary_ip4"],
                status=adapter.status_active,
                description=f"Primary IP for {ids['name']}"
            )
            device.primary_ip4 = ip
            device.save()
        
        return super().create(adapter=adapter, ids=ids, attrs=attrs)


class NautobotVirtualMachine(DiffSyncModel):
    """DiffSync model for Nautobot VirtualMachine."""
    
    _modelname = "nautobot_virtualmachine"
    _identifiers = ("name", "cluster")
    _attributes = (
        "status", "vcpus", "memory", "disk",
        "primary_ip4", "platform", "custom_fields"
    )
    
    name: str
    cluster: str
    status: str = "Active"
    vcpus: Optional[int] = None
    memory: Optional[int] = None  # In MB
    disk: Optional[int] = None  # In GB
    primary_ip4: Optional[str] = None
    platform: Optional[str] = None
    custom_fields: Dict[str, Any] = {}
    
    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create a new VM in Nautobot."""
        from nautobot.virtualization.models import VirtualMachine, Cluster
        
        try:
            cluster = Cluster.objects.get(name=ids["cluster"])
        except Cluster.DoesNotExist:
            # Create cluster if it doesn't exist
            cluster = Cluster.objects.create(
                name=ids["cluster"],
                cluster_type=adapter.openshift_cluster_type,
                site=adapter.openshift_site
            )
        
        vm = VirtualMachine.objects.create(
            name=ids["name"],
            cluster=cluster,
            status=adapter.status_active,
            vcpus=attrs.get("vcpus"),
            memory=attrs.get("memory"),
            disk=attrs.get("disk"),
            platform=adapter.openshift_platform if attrs.get("platform") else None,
            custom_field_data=attrs.get("custom_fields", {})
        )
        
        # Create primary IP if provided
        if attrs.get("primary_ip4"):
            from nautobot.ipam.models import IPAddress
            ip = IPAddress.objects.create(
                address=attrs["primary_ip4"],
                status=adapter.status_active,
                description=f"Primary IP for VM {ids['name']}"
            )
            vm.primary_ip4 = ip
            vm.save()
        
        return super().create(adapter=adapter, ids=ids, attrs=attrs)


class NautobotIPAddress(DiffSyncModel):
    """DiffSync model for Nautobot IPAddress."""
    
    _modelname = "nautobot_ipaddress"
    _identifiers = ("address",)
    _attributes = ("status", "description", "custom_fields")
    
    address: str
    status: str = "Active"
    description: Optional[str] = ""
    custom_fields: Dict[str, Any] = {}
    
    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create a new IP address in Nautobot."""
        from nautobot.ipam.models import IPAddress
        
        ip = IPAddress.objects.create(
            address=ids["address"],
            status=adapter.status_active,
            description=attrs.get("description", ""),
            custom_field_data=attrs.get("custom_fields", {})
        )
        return super().create(adapter=adapter, ids=ids, attrs=attrs)


class NautobotService(DiffSyncModel):
    """DiffSync model for Nautobot Service."""
    
    _modelname = "nautobot_service"
    _identifiers = ("name", "protocol", "ports")
    _attributes = ("description", "custom_fields")
    
    name: str
    protocol: str
    ports: List[int] = []
    description: Optional[str] = ""
    custom_fields: Dict[str, Any] = {}
    
    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create a new service in Nautobot."""
        from nautobot.ipam.models import Service
        
        service = Service.objects.create(
            name=ids["name"],
            protocol=ids["protocol"],
            ports=ids["ports"],
            description=attrs.get("description", ""),
            custom_field_data=attrs.get("custom_fields", {})
        )
        return super().create(adapter=adapter, ids=ids, attrs=attrs)
