# OpenShift SSoT Integration

The SSoT OpenShift Integration allows for synchronizing container and virtual machine workloads between [Red Hat OpenShift](https://www.redhat.com/en/technologies/cloud-computing/openshift) (including KubeVirt VMs) and [Nautobot](https://github.com/nautobot/nautobot).

## Architecture Overview

```mermaid
graph TB
    subgraph "OpenShift Cluster"
        OC[OpenShift API]
        KV[KubeVirt API]
        subgraph "Resources"
            NS[Namespaces/Projects]
            ND[Nodes]
            PD[Pods]
            DP[Deployments]
            SV[Services]
            VM[KubeVirt VMs]
        end
    end
    
    subgraph "Nautobot SSoT"
        OI[OpenShift Integration]
        DS[DiffSync Engine]
    end
    
    subgraph "Nautobot"
        TN[Tenants]
        DV[Devices]
        AP[Applications]
        SR[Services]
        VMS[Virtual Machines]
    end
    
    OC --> OI
    KV --> OI
    OI --> DS
    DS --> TN
    DS --> DV
    DS --> AP
    DS --> SR
    DS --> VMS
    
    NS -.->|maps to| TN
    ND -.->|maps to| DV
    PD -.->|maps to| AP
    DP -.->|maps to| AP
    SV -.->|maps to| SR
    VM -.->|maps to| VMS
```

## Resource Mapping

| OpenShift Resource      | Nautobot Model     | Notes                                      |
| :-------------------- | :---------------- | :----------------------------------------- |
| Project/Namespace     | Tenant            | Organizational grouping                    |
| Node                  | Device            | Physical or virtual compute nodes          |
| Pod/Container         | Application       | Container workloads                        |
| Deployment            | Application       | Grouped container workloads                |
| Service               | Service           | Network services                           |
| KubeVirt VM           | Virtual Machine   | Virtual machines running on OpenShift      |
| KubeVirt VMI          | Virtual Machine   | Running instance updates existing VM       |

## Key Features

- **Dual Workload Support**: Synchronizes both traditional container workloads and KubeVirt virtual machines
- **Intelligent Detection**: Automatically differentiates between container pods and VM pods
- **Flexible Configuration**: Choose to sync all workloads, containers only, or VMs only
- **Namespace Filtering**: Use regex patterns to sync specific namespaces
- **KubeVirt Auto-Detection**: Automatically detects if KubeVirt is installed

## Workload Detection Flow

```mermaid
flowchart TD
    A[Fetch Pod from OpenShift] --> B{Check Pod Labels}
    B -->|Has kubevirt.io/domain| C[Identified as VM Pod]
    B -->|No VM Labels| D[Check Containers]
    D -->|Has virt-launcher| C
    D -->|Regular Containers| E[Container Pod]
    
    C --> F[Query VirtualMachine CR]
    F --> G[Create/Update Nautobot VM]
    
    E --> H{Part of Deployment?}
    H -->|Yes| I[Link to Deployment]
    H -->|No| J[Standalone Pod]
    I --> K[Create/Update Application]
    J --> K
    
    style C fill:#f9f,stroke:#333,stroke-width:2px
    style E fill:#9ff,stroke:#333,stroke-width:2px
```

## Usage

Once the integration is installed and configured, the OpenShift sync will show up under the Data Sources section of the Nautobot SSoT dashboard.

![Dashboard View](../../images/openshift_dashboard.png)

From the dashboard, you can view more details about the OpenShift sync by clicking the `Red Hat OpenShift -> Nautobot` link. This view shows the mapping of OpenShift objects to Nautobot objects, displaying exactly what will be created in Nautobot when the sync runs.

![Detail View](../../images/openshift_detail.png)

## Running a Sync Job

From the OpenShift sync detail page, click the `Sync Now` button to access the sync job form. The job has several configurable fields:

### Job Parameters

- **Dryrun** - When checked, the sync will run and show the diff between Nautobot and OpenShift without making any database changes
- **Memory Profiling** - Provides memory usage information during the sync
- **Debug** - Enables verbose logging for troubleshooting
- **Config** - Select the OpenShift configuration instance to use
- **Task Queue** - Choose which queue to assign this sync job to (if using multiple queues)

![Job View](../../images/openshift_job.png)

### Understanding Workload Types

The OpenShift integration can handle two distinct types of workloads:

#### Container Workloads
- Traditional Kubernetes pods and containers
- Synchronized as Nautobot Applications
- Includes deployments, statefulsets, and daemonsets

#### KubeVirt Virtual Machines
- Full virtual machines running on OpenShift via KubeVirt
- Synchronized as Nautobot Virtual Machines
- Maintains VM-specific attributes like CPU, memory, and disks

## Sync Process Flow

```mermaid
sequenceDiagram
    participant User
    participant Nautobot
    participant SSoT
    participant OpenShift
    participant KubeVirt
    
    User->>Nautobot: Trigger Sync Job
    Nautobot->>SSoT: Execute OpenShift Sync
    SSoT->>OpenShift: Authenticate with Token
    SSoT->>OpenShift: Check API Access
    
    alt KubeVirt Available
        SSoT->>KubeVirt: Detect KubeVirt API
        Note over SSoT: Enable VM Sync Mode
    else KubeVirt Not Available
        Note over SSoT: Container Only Mode
    end
    
    par Fetch Resources
        SSoT->>OpenShift: Get Namespaces
        OpenShift-->>SSoT: Namespace Data
    and
        SSoT->>OpenShift: Get Nodes
        OpenShift-->>SSoT: Node Data
    and
        SSoT->>OpenShift: Get Pods/Containers
        OpenShift-->>SSoT: Pod Data
    and
        SSoT->>KubeVirt: Get Virtual Machines
        KubeVirt-->>SSoT: VM Data
    end
    
    SSoT->>SSoT: Process & Transform Data
    SSoT->>SSoT: Detect VM vs Container Pods
    SSoT->>Nautobot: Apply Changes via DiffSync
    Nautobot-->>User: Display Results
```

## Sync Results

Running the job redirects you to the Job Result page with real-time logs:

![Job Result](../../images/openshift_jobresult.png)

After completion, click the **SSoT Sync Details** button to view:
- Objects created, updated, or deleted
- Detailed diff of changes
- Any errors or warnings encountered

## Data Mapping Details

### Projects/Namespaces → Tenants
OpenShift projects are mapped to Nautobot tenants, providing organizational structure for all synced resources.

### Nodes → Devices
OpenShift nodes (master and worker) are synced as devices with:
- Role (master/worker)
- CPU, memory, and storage capacity
- Operating system information
- IP addresses

### Containers → Applications
Container workloads are synced as applications with:
- Associated namespace (tenant)
- Resource requests and limits
- Image information
- Port mappings

### KubeVirt VMs → Virtual Machines
When KubeVirt is detected, VMs are synced with:
- CPU cores and memory allocation
- Disk configuration
- Network interfaces
- Power state (running/stopped)
- Guest OS information

## Filtering and Scoping

### Namespace Filtering
Use regex patterns to sync only specific namespaces:
- `^prod-.*` - Sync only production namespaces
- `^(dev|test)-.*` - Sync dev and test namespaces
- `.*-frontend$` - Sync namespaces ending with "-frontend"

### Workload Type Selection

```mermaid
graph LR
    A[Workload Type Setting] --> B{Selection}
    B -->|All| C[Sync Containers & VMs]
    B -->|Containers Only| D[Skip KubeVirt VMs]
    B -->|VMs Only| E[Only KubeVirt VMs]
    
    C --> F[Full Inventory]
    D --> G[Application Focus]
    E --> H[VM Migration]
    
    style C fill:#9f9,stroke:#333,stroke-width:2px
    style D fill:#99f,stroke:#333,stroke-width:2px
    style E fill:#f99,stroke:#333,stroke-width:2px
```

## Common Use Cases

### Multi-Environment Sync
Create separate configuration instances for different OpenShift clusters (dev, staging, production) and sync them to different Nautobot tenants.

### Selective VM Import
Use the "VMs Only" workload type to import just KubeVirt virtual machines, useful when migrating from traditional virtualization platforms.

### Container Inventory
Use the "Containers Only" mode to maintain an inventory of containerized applications without VM overhead.

### Compliance Reporting
Regular syncs ensure Nautobot always has current OpenShift resource information for compliance and audit purposes.

## Best Practices

1. **Start Small**: Begin with a single namespace or limited scope to verify configuration
2. **Use Dry Run**: Always test with dry run before the first production sync
3. **Regular Syncs**: Schedule regular syncs to keep data current
4. **Monitor Performance**: Use debug logging for large clusters to identify bottlenecks
5. **Namespace Organization**: Use consistent namespace naming for easier filtering

## Troubleshooting Tips

### Missing VMs
If KubeVirt VMs aren't syncing:
- Check job logs for "KubeVirt detected" message
- Verify service account has virtualization permissions
- Ensure workload type isn't set to "Containers Only"

### Performance Issues
For slow syncs:
- Use namespace filtering to reduce scope
- Enable memory profiling to identify issues
- Consider splitting large clusters across multiple configs

### Authentication Errors
- Verify service account token hasn't expired
- Check API URL includes protocol (https://)
- Test connectivity from Nautobot server to OpenShift API 