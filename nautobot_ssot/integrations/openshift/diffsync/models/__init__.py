# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Network to Code, LLC
# Copyright (c) 2025 NVIDIA Corporation

"""DiffSync models for OpenShift integration."""
from .base import OpenshiftProject, OpenshiftNode
from .containers import OpenshiftPod, OpenshiftContainer, OpenshiftDeployment, OpenshiftService
from .kubevirt import OpenshiftVirtualMachine, OpenshiftVirtualMachineInstance
from .nautobot import (
    NautobotTenant, NautobotDevice, NautobotVirtualMachine,
    NautobotIPAddress, NautobotService, NautobotCluster
)

__all__ = [
    "OpenshiftProject",
    "OpenshiftNode",
    "OpenshiftPod",
    "OpenshiftContainer",
    "OpenshiftDeployment",
    "OpenshiftService",
    "OpenshiftVirtualMachine",
    "OpenshiftVirtualMachineInstance",
    "NautobotTenant",
    "NautobotDevice",
    "NautobotVirtualMachine",
    "NautobotIPAddress",
    "NautobotService",
    "NautobotCluster",
]
