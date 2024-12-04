# Slurpit SSoT Integration

This integration provides a simple way to synchronize data between [Slurpit](https://slurpit.io/) and [Nautobot](https://github.com/nautobot/nautobot). It support multiple data types, including Devices, Interfaces, and IP Addresses.

It synchronizes the following objects:

| Slurpit                  | Nautobot                     |
| -----------------------  | ---------------------------- |
| Sites                    | Location                     |
| Devices                  | Manufacturer                 |
| Devices                  | Platform                     |
| Devices                  | Device Type                  |
| Devices                  | Device                       |
| Planning (Hardware Info) | Inventory Item               |
| Planning (VLANs)         | VLAN                         |
| Planning (Routing Table) | VRF                          |
| Planning (Routing Table) | Prefix                       |
| Planning (Interfaces)    | Interface                    |
| Planning (Interfaces)    | IP Address                   |

## Usage

Once the integration is installed and configured, from the Nautobot SSoT Dashboard view (`/plugins/ssot/`), Slurpit will be shown as a Data Source. You can click the **Sync** button to access a form view from which you can run the Slurpit-to-Nautobot synchronization Job. Running the job will redirect you to a Nautobot **Job Result** view, from which you can access the **SSoT Sync Details** view to see detailed information about the outcome of the sync Job.

There are several options available for the sync Job:

- **Dryrun**: If enabled, the sync Job will only report the differences between the source and destination without synchronizing any data.
- **Memory Profiling**: If enabled, the sync Job will collect memory profiling data and include it in the Job Result.
- **Slurpit Instance**: The Slurpit instance to sync data from.
- **Site LocationType**: The Nautobot LocationType to use for imported Sites.
- **IPAM Namespace**: The Namespace to use for all imported IPAM data.
- **Ignore Routing Table Prefixes**: If enabled, the sync Job will not import some routing table prefixes such as `0.0.0.0/0`, `::/0`, `224.0.0.0/4` and more. 
- **Sync tagged objects only**: If enabled, the sync Job will only import objects that have been tagged with the `SSoT Synced from Slurpit` tag in Nautobot.
- **Task Queue**: The Task Queue to use for the sync Job.
- **Profile job execution**: If enabled, the sync Job will collect profiling data and include it in the Job Result. This will only be present if Nautobot is running in debug mode.

## Screenshots

![Detail View](../../images/slurpit-detail-view.png)

---

![Results View](../../images/slurpit-result-view.png)
