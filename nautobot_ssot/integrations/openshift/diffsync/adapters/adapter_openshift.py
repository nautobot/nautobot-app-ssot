"""OpenShift adapter for DiffSync."""
from typing import Dict, List, Any
from diffsync import Adapter

from nautobot_ssot.integrations.openshift.utilities.openshift_client import OpenshiftClient
from nautobot_ssot.integrations.openshift.diffsync.models.base import (
    OpenshiftProject, OpenshiftNode
)
from nautobot_ssot.integrations.openshift.diffsync.models.containers import (
    OpenshiftPod, OpenshiftContainer, OpenshiftDeployment, OpenshiftService
)
from nautobot_ssot.integrations.openshift.diffsync.models.kubevirt import (
    OpenshiftVirtualMachine, OpenshiftVirtualMachineInstance
)


class OpenshiftAdapter(Adapter):
    """DiffSync adapter for OpenShift."""
    
    # Define model classes
    project = OpenshiftProject
    node = OpenshiftNode
    pod = OpenshiftPod
    container = OpenshiftContainer
    deployment = OpenshiftDeployment
    service = OpenshiftService
    virtualmachine = OpenshiftVirtualMachine
    vmi = OpenshiftVirtualMachineInstance
    
    # Define top-level models
    top_level = ["project", "node", "deployment", "service", "virtualmachine"]
    
    def __init__(self, *args, job=None, sync=None, config=None, client_config=None, **kwargs):
        """Initialize the OpenShift adapter."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.config = config
        self.client_config = client_config or {}
        
        # Initialize OpenShift client with extracted configuration
        self.client = OpenshiftClient(
            url=self.client_config.get("url", config.openshift_instance.remote_url),
            api_token=self.client_config.get("api_token", ""),
            verify_ssl=self.client_config.get("verify_ssl", config.openshift_instance.verify_ssl)
        )
    
    def load(self):
        """Load data from OpenShift."""
        # Verify connection
        if not self.client.verify_connection():
            self.job.logger.error("Failed to connect to OpenShift API")
            raise Exception("Failed to connect to OpenShift API")
        
        # Load projects/namespaces
        if self.client_config.get("sync_namespaces", self.config.sync_namespaces):
            self._load_projects()
        
        # Load nodes
        if self.client_config.get("sync_nodes", self.config.sync_nodes):
            self._load_nodes()
        
        # Load workloads based on configuration
        workload_types = self.client_config.get("workload_types", self.config.workload_types)
        if workload_types in ["all", "containers"]:
            if self.client_config.get("sync_containers", self.config.sync_containers):
                self._load_containers()
            if self.client_config.get("sync_deployments", self.config.sync_deployments):
                self._load_deployments()
        
        if workload_types in ["all", "vms"]:
            if (self.client_config.get("sync_kubevirt_vms", self.config.sync_kubevirt_vms) 
                and self.client.kubevirt_available):
                self._load_virtual_machines()
        
        # Load services
        if self.client_config.get("sync_services", self.config.sync_services):
            self._load_services()
    
    def _load_projects(self):
        """Load OpenShift projects/namespaces."""
        namespace_filter = self.client_config.get("namespace_filter", self.config.namespace_filter)
        projects = self.client.get_projects(namespace_filter)
        
        for project_data in projects:
            project = self.project(**project_data)
            self.add(project)
            self.job.logger.debug(f"Loaded project: {project.name}")
    
    def _load_nodes(self):
        """Load OpenShift nodes."""
        nodes = self.client.get_nodes()
        
        for node_data in nodes:
            node = self.node(**node_data)
            self.add(node)
            self.job.logger.debug(f"Loaded node: {node.name}")
    
    def _load_containers(self):
        """Load containers and pods, excluding KubeVirt VMs."""
        pods, containers = self.client.get_pods_and_containers()
        
        # Process pods
        for pod_data in pods:
            if not pod_data["is_kubevirt_vm"]:
                pod = self.pod(**pod_data)
                self.add(pod)
                self.job.logger.debug(f"Loaded pod: {pod.namespace}/{pod.name}")
        
        # Process containers
        for container_data in containers:
            container = self.container(**container_data)
            self.add(container)
            self.job.logger.debug(
                f"Loaded container: {container.namespace}/{container.pod_name}/{container.name}"
            )
    
    def _load_deployments(self):
        """Load OpenShift deployments."""
        deployments = self.client.get_deployments()
        
        for deployment_data in deployments:
            deployment = self.deployment(**deployment_data)
            self.add(deployment)
            self.job.logger.debug(f"Loaded deployment: {deployment.namespace}/{deployment.name}")
    
    def _load_services(self):
        """Load OpenShift services."""
        services = self.client.get_services()
        
        for service_data in services:
            service = self.service(**service_data)
            self.add(service)
            self.job.logger.debug(f"Loaded service: {service.namespace}/{service.name}")
    
    def _load_virtual_machines(self):
        """Load KubeVirt virtual machines."""
        vms = self.client.get_virtual_machines()
        
        for vm_data in vms:
            vm = self.virtualmachine(**vm_data)
            self.add(vm)
            self.job.logger.debug(f"Loaded VM: {vm.namespace}/{vm.name}")
            
            # If VM is running, load its instance
            if vm.running and vm.vmi_uid:
                vmi_data = self.client.get_virtual_machine_instance(
                    vm.namespace, vm.name
                )
                if vmi_data:
                    vmi = self.vmi(**vmi_data)
                    self.add(vmi)
                    self.job.logger.debug(f"Loaded VMI: {vmi.namespace}/{vmi.name}")
