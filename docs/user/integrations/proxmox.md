# Proxmox VE Integration

This integration syncs virtualization inventory from Proxmox VE into Nautobot using the Proxmox VE
REST API. It only reads from Proxmox and does not modify the Proxmox cluster.

![Dashboard View](../../images/proxmox_dashboard.png)

## What is read from Proxmox VE

The sync calls these read-only REST endpoints (plus the QEMU guest agent and LXC config):

| Endpoint / source | Used for |
| ----------------- | -------- |
| `/cluster/status` | Cluster name and membership |
| `/cluster/resources` | VM/container inventory and power state |
| `/nodes` | Node (hypervisor host) inventory |
| `/nodes/{node}/status` | Node PVE version, CPU count, memory |
| `/nodes/{node}/network` | Node network interfaces and their IPs |
| QEMU guest agent | IP addresses of running QEMU VMs (agent must be installed and the VM powered on) |
| LXC container config | IP addresses of LXC containers |

## What is created / updated in Nautobot

| Proxmox VE source | Nautobot object |
| ----------------- | --------------- |
| Cluster (`/cluster/status`) | `Cluster` (ClusterType "Proxmox VE"), grouped under a `ClusterGroup` |
| Node (`/nodes`) | DCIM `Device` (host) — when *Sync Nodes as Devices* is enabled |
| Node hardware/version (`/nodes/{node}/status`) | Device custom fields: `proxmox_pve_version`, `proxmox_cpu_count`, `proxmox_memory_gb` |
| Node network interface (`/nodes/{node}/network`) | DCIM `Interface` on the node Device (type mapped per the configurable [node interface type map](../../admin/integrations/proxmox_setup.md#node-interface-type-mapping); defaults: eth→1000base-t, bond→lag, bridge→bridge, vlan→virtual), with MTU |
| Node interface topology | bridge members → `bridge`, bond slaves → `lag`, VLAN raw device → `parent_interface` |
| Node interface IP (`cidr`/`address`) | `IPAddress` assigned to the DCIM Interface; the management IP becomes the Device `primary_ip4` |
| QEMU VM | `VirtualMachine` (linked to its host node Device via the "Proxmox VM Host" relationship) |
| LXC container | `VirtualMachine` — when *Sync LXC Containers* is enabled |
| vCPU / RAM / disk | VirtualMachine `vcpus` / `memory` (MB) / `disk` (GB) |
| Power state | VirtualMachine `status` (mapped via the VM status map) |
| Proxmox VE tags | Nautobot `Tag`s on the VirtualMachine — when *Sync Proxmox VE Tags* is enabled |
| NICs | `VMInterface` |
| IP addresses | `IPAddress` + the containing `Prefix` |

Nautobot's `VirtualMachine` has no host Device field, so each VM is linked to its Proxmox node
through the "Proxmox VM Host" relationship (Device → VirtualMachine).

Every synced object has the `last_synced_from_proxmox_on` custom field set to the date of the last
sync. The integration uses this field to identify the objects it manages. Synced objects are also
tagged "SSoT Synced from Proxmox" (configurable) for visibility in the UI; the tag does not affect
what is synced or deleted.

![Detail View](../../images/proxmox_detail.png)

## Running the job

1. Configure a Proxmox VE instance and credentials, and enable a config for the job (set both
   **Sync to Nautobot** and **Enabled for Sync Job**) — see the [admin setup guide](../../admin/integrations/proxmox_setup.md).
2. Go to **Jobs → SSoT - Virtualization → Proxmox VE ⟹ Nautobot**.
3. Set the job options:
    - **Config** (required) — the `SSOTProxmoxConfig` to use. Only configs that have both *Sync to
      Nautobot* and *Enabled for Sync Job* set appear here.
    - **Debug** — verbose logging.
    - **Cluster Filters** (optional) — restrict the sync to Virtual Machines in the selected clusters.
4. Run a **dry run** first to preview the diff, then run for real.

![Job View](../../images/proxmox_job.png)

![Job Result](../../images/proxmox_jobresult.gif)

## Re-run / idempotency behavior

The sync is idempotent. Each run brings Nautobot in line with Proxmox:

- Unchanged objects are left untouched, changed attributes are updated, and new objects are created.
- Only objects with the `last_synced_from_proxmox_on` custom field are updated or deleted. Manually
  created objects are not modified.
- **Deleted when they disappear from Proxmox:** `VirtualMachine`, `VMInterface`, and node
  `Interface` objects.
- **Not deleted by a sync:** `Prefix`, `IPAddress`, `Device` (nodes), `Cluster`, and
  `ClusterGroup`. A cluster-filtered run does not see every object, and these records may be shared
  with other data.
- Primary IPs (VMs and nodes) and node interface links (bridge, bond, VLAN parent) are set after the
  main sync, once the referenced interfaces and IPs exist.
- Each run re-stamps the SSoT tag and the `last_synced_from_proxmox_on` custom field.
- The job runs with `CONTINUE_ON_FAILURE`, so an error on one object does not stop the sync. Check
  the job log for per-object warnings.

## Limitations

- **One-way sync.** Data flows from Proxmox VE to Nautobot only.
- **QEMU VM IPs require the guest agent.** QEMU VM IP addresses come from the QEMU guest agent, so
  they are only reported for running VMs with the agent installed. VMs without a reachable agent are
  synced without IPs. LXC container IPs come from the container config and do not need an agent.
- **Some objects are not deleted.** `Prefix`, `IPAddress`, `Device` (nodes), `Cluster`, and
  `ClusterGroup` remain in Nautobot after they are removed from Proxmox and must be cleaned up
  manually.
- **Only managed objects are changed.** The sync only updates or deletes objects that have the
  `last_synced_from_proxmox_on` custom field. The SSoT tag (set by the config's **SSoT Tag** field)
  does not affect this.
- **Cluster Filters apply to Virtual Machines only.** Nodes, interfaces, prefixes, and IPs are not
  filtered.
- **Link-local addresses are skipped by default.** Link-local and APIPA addresses on VM interfaces
  are ignored unless *Ignore Link Local* is disabled in the config.
- **Status maps must reference existing statuses.** Values in the VM and IP status maps must name
  existing Nautobot `Status` objects.
- **Resource values are rounded down.** Memory is stored in whole MB and disk in whole GB, so very
  small values may display as `0`.
- **Token authentication only.** Username/password login is not supported.
- **The vSphere integration may delete the SSoT tag.** vSphere tag cleanup is not limited to its own
  tags, so a vSphere sync can remove the "SSoT Synced from Proxmox" tag. The next Proxmox VE sync
  recreates it, and sync behavior is not affected.
