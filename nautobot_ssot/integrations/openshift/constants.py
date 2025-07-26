"""Constants for OpenShift integration."""

# KubeVirt related constants
KUBEVIRT_GROUP = "kubevirt.io"
KUBEVIRT_VERSION = "v1"
KUBEVIRT_VM_PLURAL = "virtualmachines"
KUBEVIRT_VMI_PLURAL = "virtualmachineinstances"

# OpenShift annotations
OPENSHIFT_DISPLAY_NAME_ANNOTATION = "openshift.io/display-name"
OPENSHIFT_DESCRIPTION_ANNOTATION = "openshift.io/description"

# Node roles
NODE_ROLE_MASTER = "master"
NODE_ROLE_WORKER = "worker"

# VM states
VM_STATE_RUNNING = "Running"
VM_STATE_STOPPED = "Stopped"
VM_STATE_MIGRATING = "Migrating"

# Default values
DEFAULT_CPU_CORES = 1
DEFAULT_MEMORY_MB = 1024
DEFAULT_MACHINE_TYPE = "q35"
