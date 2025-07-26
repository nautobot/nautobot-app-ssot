# Red Hat OpenShift Integration for Nautobot SSoT

This directory contains the implementation for synchronizing Red Hat OpenShift resources with Nautobot.

## Features

- **Container Workload Sync**: Synchronizes pods, deployments, and services
- **KubeVirt VM Support**: Automatically detects and syncs KubeVirt virtual machines
- **Flexible Configuration**: Choose what resources to sync and apply namespace filters
- **Intelligent Detection**: Differentiates between container pods and VM pods

## Directory Structure

```
openshift/
├── __init__.py              # Package initialization
├── api/                     # REST API implementation
│   ├── serializers.py       # DRF serializers
│   ├── urls.py             # API URL patterns
│   └── views.py            # API viewsets
├── choices.py              # Choice definitions
├── constants.py            # Constants and defaults
├── diffsync/               # DiffSync implementation
│   ├── adapters/           # DiffSync adapters
│   │   ├── adapter_nautobot.py
│   │   └── adapter_openshift.py
│   └── models/             # DiffSync models
│       ├── base.py         # Base models and mixins
│       ├── containers.py   # Container-specific models
│       ├── kubevirt.py     # KubeVirt VM models
│       └── nautobot.py     # Nautobot-specific models
├── filters.py              # Django filters
├── forms.py                # Django forms
├── jobs.py                 # SSoT job definitions
├── models.py               # Django models
├── signals.py              # Django signals
├── tables.py               # Django tables
├── urls.py                 # URL configuration
├── utilities/              # Utility modules
│   ├── openshift_client.py # OpenShift API client
│   └── kubevirt_utils.py   # KubeVirt helpers
└── views.py                # Django views
```

## Key Components

### Models (`models.py`)
- `SSOTOpenshiftConfig`: Stores configuration for OpenShift instances

### Jobs (`jobs.py`)
- `OpenshiftDataSource`: Main sync job from OpenShift to Nautobot

### DiffSync Models
- **Base Models**: Common attributes for all OpenShift resources
- **Container Models**: Pod, Container, Deployment, Service
- **KubeVirt Models**: VirtualMachine, VirtualMachineInstance

### Client (`utilities/openshift_client.py`)
- Handles authentication and API calls to OpenShift
- Detects KubeVirt availability
- Differentiates between container and VM workloads

## Development

See the [implementation guide](openshift.md) for detailed development instructions.

## Testing

Tests are located in `nautobot_ssot/tests/openshift/`:
- Unit tests for models, adapters, and client
- Integration tests for the sync job
- Fixtures for mocking OpenShift API responses

## Documentation

- Admin Guide: `docs/admin/integrations/openshift_setup.md`
- User Guide: `docs/user/integrations/openshift.md`
- Implementation Guide: `openshift.md` (this directory) 