# IPFabric SSoT Integration

SSoT IPFabric integration providing a simple way to synchronize data between [IPFabric](https://ipfabric.io/) and [Nautobot](https://github.com/nautobot/nautobot). Ensure data stays consistent between the two platforms by leveraging [DiffSync](https://github.com/networktocode/diffsync) capabilities and allowing users to take full advantage of both platforms with up-to-date, synchronized data.

## Usage

You can navigate to the SSoT Dashboard with the following steps:

1. Click the **Plugins** menu and select **Dashboard** under *Single Source of Truth*.

![SSoT Dashboard Nav Menu](../../images/ipfabric-nav-dashboard.png)

Now you should see the dashboard with information pertaining to **IP Fabric**.

![SSoT Dashboard](../../images/ipfabric-dashboard.png)

We can see **IP Fabric** under **Data Sources** with some quick information such as the results of the latest synchronizations and the ability to launch the synchronization job.

On the right-hand side, we're provided with additional information such as the source, target, start time, status, and the type of job.

Let's go ahead and click on **IP Fabric** under **Data Sources**.

![IPFabric Data Source](../../images/ipfabric-datasource.png)

Now we can see additional details as to which IP Fabric host we're syncing from and the models that get mapped between the source and destination. We can also kick off sync job by clicking on **Sync Now**, but we will revisit that shortly.

Below, the sync history is provided with more details of what happened during each synchronization job.

![IPFabric Sync History](../../images/ipfabric-sync-history.png)

Now back to running the job. Let's click on **Sync Now**.

![Sync Run](../../images/ipfabric-sync-run.png)

There are several options available.

- **Debug**: Enables more verbose logging that can be useful for troubleshooting synchronization issues.
- **Safe Delete Mode**: Delete operations changes the object status to a predefined value (configurable via settings) and tags the object with `SSoT Safe Delete` Tag.
- **Sync Tagged Only**: Only load Nautobot data into DiffSync adapters that has the `SSoT Synced from IPFabric` Tag.
- **Bulk Write Mode**: Write objects in batches rather than one at a time. Much faster on a large sync, at the cost of change log entries, signals and per-object validation. Disabled by default; see [Bulk Write Mode](#bulk-write-mode) for what it does and does not give up.
- **Sync Locations**: Create, update and delete Nautobot Locations from IP Fabric sites. Enabled by default. Deselect where another system owns the site list; see [Choosing what to sync](../../admin/integrations/ipfabric_setup.md#locations) for what that does and does not stop.
- **Sync Manufacturers**: Create Nautobot Manufacturers for the vendors IP Fabric reports. Enabled by default.
- **Sync Device Types**: Create Nautobot Device Types for the models IP Fabric reports. Enabled by default.
- **Sync Roles**: Create Nautobot Roles from the device types IP Fabric reports. Enabled by default.
- **Sync Platforms**: Create Nautobot Platforms from the families IP Fabric reports. Enabled by default.
- **Sync Interfaces**: Sync each Device's Interfaces. Enabled by default.
- **Sync IP Addresses**: Sync the IP Address on each Interface. Enabled by default; requires **Sync Interfaces**.
- **Sync Primary IP**: Assign a Device's primary IP from IP Fabric. Enabled by default; requires **Sync IP Addresses**. IP Fabric reports the address it logged in with, which is not necessarily the address a CMDB considers the management one.
- **Sync VLANs**: Sync each Location's VLANs. Enabled by default.
- **Sync Cables**: Sync the device connections in IP Fabric's connectivity matrix to Nautobot Cables. Disabled by default; requires **Sync Interfaces**. See [Cables](#cables).
- **Dry run**: This will only report the difference between the source and destination without synchronization.
- **Site Filter**: Filter the data loaded into DiffSync by a top level location of a specified Site.

Deselecting an object type keeps it out of the sync in both directions, so existing Nautobot records of that type are left untouched rather than removed as absent from IP Fabric. An object type whose requirement is not selected is skipped, and the Job log names the unmet requirement. Devices are always synced, since every other object type is either a Device or hangs off one.

Which types appear on the form, and which are pre-selected, can be set per installation. See [Choosing what to sync](../../admin/integrations/ipfabric_setup.md#choosing-what-to-sync).

If interested to see the source code, click on **Source**.

After a job is launched, you will be redirected to the job results page which will provide any logged messages during the synchronization.

If you're interested in more details, click **SSoT Sync Details**.

![Job Results](../../images/ipfabric-job-results.png)

You can then view the details of each object.

![Sync Details](../../images/ipfabric-sync-details.png)

## DiffSync Models

Currently, this integration will provide the ability to sync the following IP Fabric models into Nautobot.

- Site ➡️ Nautobot Site
- Device ➡️ Nautobot Device
- Part Numbers ➡️ Nautobot Manufacturer/Device Type/Platform
- Interfaces ➡️ Nautobot Device Interfaces
- IP Addresses ➡️ Nautobot IP Addresses
- Connectivity Matrix ➡️ Nautobot Cables (opt in, see [Cables](#cables))

### IPFabric Site

| IP Fabric (Source) | DiffSync Model | Nautobot (Destination) |
| ------------------ | -------------- | ---------------------- |
| siteName           | Location.name  | Site                   |

### IPFabric Device

| IP Fabric (Source) | DiffSync Model       | Nautobot (Destination) |
|--------------------|----------------------|------------------------|
| hostname           | Device.name          | Device.name            |
| siteName           | Device.location_name | Device.site            |
| vendor             | Device.vendor        | Device.manufacturer    |
| model              | Device.model         | Device.device_type     |
| sn                 | Device.serial_number | Device.serial          |
| devType*           | Device.role          | Device.role            |

> Note: `devType` is an IP Fabric field that can be used to set the Device role. This can be disabled by setting `ipfabric_sync_ipf_dev_type_to_role` to `False` in the configuration. If this is disabled, the default role will be used for adding new devices and roles will be ignored during diffsync update preventing a custom Nautobot role from being overridden.

### IPFabric Interface

| IP Fabric (Source) | DiffSync Model          | Nautobot (Destination)    |
| ------------------ | ----------------------- | ------------------------- |
| intName            | Interface.name          | Interface.name            |
| hostname           | Interface.device_name   | Interface.assigned_object |
| mac                | Interface.mac_address   | Interface.mac_address     |
| mtu                | Interface.mtu           | Interface.mtu             |
| N/A                | Interface.type          | Interface.type            |
| primaryIp          | Interface.ip_address    | IPAddress.address         |
| N/A                | Interface.subnet_mask   | IPAddress.address         |
| N/A                | Interface.ip_is_primary | Device.primary_ip         |

> Note: Interfaces only support synchronizing 1 IP Address at the moment.

### IPFabric VLAN

| IP Fabric (Source) | DiffSync Model | Nautobot (Destination) |
| ------------------ | -------------- | ---------------------- |
| vlanName           | Vlan.name      | VLAN.name              |
| vlanId             | Vlan.vid       | VLAN.vid               |
| status             | Vlan.status    | VLAN.status            |
| siteName           | Vlan.site      | VLAN.site              |

### IPFabric Cable

Cables are built from IP Fabric's connectivity matrix (`tables/interfaces/connectivity-matrix`), which reports links that IP Fabric has already correlated from both ends.

| IP Fabric (Source)   | DiffSync Model               | Nautobot (Destination)      |
| -------------------- | ---------------------------- | --------------------------- |
| localHost/remoteHost | Cable.termination_a_device   | Cable.termination_a.device  |
| localInt/remoteInt   | Cable.termination_a_name     | Cable.termination_a.name    |
| localHost/remoteHost | Cable.termination_b_device   | Cable.termination_b.device  |
| localInt/remoteInt   | Cable.termination_b_name     | Cable.termination_b.name    |
| N/A                  | Cable.status                 | Cable.status                |

## Subnet Masks

IP Fabric describes a subnet per Device, so an address on several Devices carries whatever subnet each of them reports for it. Nautobot holds one mask per IP Address, and parents an address to the most specific Prefix containing it, so two records for one address in a Namespace cannot coexist.

Where the reports disagree, the sync takes the narrowest of them for every Interface carrying that address, which is the report that agrees with the address's parent Prefix, and logs the address it did this for. Choosing once rather than per Device is what lets the mask settle; following each Device's own report left every run rewriting what the last had written.

## Sync Tagged Only

With **Sync Tagged Only** selected, which is the default, the sync reads and writes only Devices carrying the `SSoT Synced from IPFabric` Tag. Deselecting it brings every Device in the selected Locations into scope, including Devices another process created, and the sync then updates their Interfaces as well as those of the Devices it created itself.

The option governs reading and writing together. It has to: a Device loaded from Nautobot but excluded from writing would have every difference IP Fabric reports about it reported again on every run and never applied.

## Cables

Cable synchronization is opt in via the **Sync Cables** job option, and is disabled by default because Nautobot allows only one Cable per Interface. Enabling it lets the sync replace connections that were recorded by hand.

A link has no stable identifier in either system: IP Fabric reports it once from each device's point of view, and Nautobot stores whichever end was cabled first as the A side. Both adapters therefore sort a link's two `(device, interface)` endpoints and use the lower one as the A side, so the same physical link resolves to one Cable either way.

Only links with both endpoints in scope are synced, since a Cable with one end out of scope would look absent from IP Fabric and be deleted on every run. A link is skipped when:

- Either Interface was not loaded, because a Site filter excludes the far end, or because the far end is a stack member whose interfaces IP Fabric reports against the stack master.
- Either Interface is virtual or wireless. Nautobot refuses to cable these types, and IP Fabric reports links over tunnel interfaces.
- The entry does not name both a device and an interface on each side.
- The Interface at either end is already recorded on a link kept earlier in the same run. IP Fabric describes a shared segment, such as a cloud subnet, as a link from every Interface in it to the segment, so one Interface can be reported on many links. Nautobot terminates at most one Cable on an Interface, so the lowest sorting of those links is kept and the rest are logged. The choice is by sort order rather than by whichever came first in the data, so that a re-sync keeps the same link instead of replacing the Cable the previous run recorded.

When IP Fabric reports a link that has moved, the Cable holding the Interface must be removed before the new one can be recorded. With **Safe Delete Mode** enabled, this does not happen; the conflict is logged as a warning and the new Cable is not created, leaving the change for an operator to review. With Safe Delete Mode disabled, the stale Cable is deleted and the new one is created.

## Bulk Write Mode

A sync writes each object on its own: Nautobot validates it, records a change log entry, and fires
the signals any app has registered. For a few hundred objects that cost is invisible. An estate of a
few thousand devices carries a hundred thousand Interfaces and about as many IP Addresses, and there
the per-object cost is most of the job's run time.

**Bulk Write Mode** writes them in batches instead. Measured over 200 Interfaces each carrying an IP
address, a sync drops from 8.8 seconds to 0.5. It is disabled by default, because it gives up three
things that are worth understanding before turning it on.

### What it gives up

**No change log entries.** Nothing written in bulk appears in an object's Change Log tab, or in the
global change log, for that run. The objects themselves are still tagged `SSoT Synced from IPFabric`
and still carry the `last_synced_from_sor` custom field, so what the sync touched is still visible on
the object; what is missing is the before-and-after record of the change.

**No signals.** Anything an app has hooked to object creation does not run for objects written in
bulk. Webhooks do not fire.

**No per-object validation.** Nautobot's `clean()` is not called, so a check written in Python is not
applied. Database constraints still are: a row that violates one is refused, and a batch a refusal
stops is retried an object at a time so the offending object is named in the job log and the rest are
still written.

### Two differences to expect

Devices created in bulk do not get the components their Device Type templates define. IP Fabric
reports the interfaces a device actually has, and those are what the sync creates, so for this
integration that is usually what you want — but if you rely on Device Type templates populating
components, do not use this mode.

A duplicate Location name is not caught. Nautobot constrains a Location's name to be unique among its
siblings, and the sites this integration creates have no parent; PostgreSQL treats those as distinct,
so two sites of the same name would both be written where a per-object sync would have rejected the
second. IP Fabric reports each site once, so this is a difference rather than an outcome to expect.

On Nautobot 3.2 the same applies to two Interfaces of one name on a Device. Nautobot 3.1 refuses that
in the database, and 3.2 moved the check into Python, which a batched insert does not run. IP Fabric
reports each interface once, so this too is a difference rather than an outcome to expect.

### What it does not change

Cables are always written one at a time, whichever mode is selected. Creating a Cable also sets the
cable, peer and path fields on both Interfaces it connects and builds Nautobot's cable paths, and all
of that happens through signals a batched write does not fire. A Cable written in bulk would appear
in the Cables list while showing no connection on either interface.

Deletions are unaffected. **Safe Delete Mode** governs those, and it is independent of this setting.

## Safe Delete Mode

By design, a Nautobot SSoT app using DiffSync will Create, Update or Delete when synchronizing two data sources. However, this may not always be what we want to happen with our Source of Truth (Nautobot). A job configuration option is available and enabled by default to prevent deleting objects from the database and instead, update the `Status` of said object alongside assigning a default Tag, `SSoT Safe Delete`. For example, if an additional snapshot is created from IPFabric, synchronized with Nautobot and, it just so happens that a device was unreachable, down for maintenance, etc., This doesn't `always` mean that our Source of Truth should delete this object, but we may need to bring attention to this matter. We let you decide what should happen. One thing to note is that some of the objects will auto recover from the changed status if a new job shows the object is present. However, currently, IP addresses and Interfaces will not auto-update to remove the `SSoT Safe Delete` Tag. The user is responsible for reviewing and updating accordingly. Safe delete tagging of objects works in an idempotent way. If an object has been tagged already, the custom field defining the last update will not be updated with a new sync date from IPFabric. So, if you re-run your sync job days apart and, you'd expect the date to change, but the object has been flagged as safe to delete; you will not see an updated date on the object custom field unless the status changed, in which case the tag (depending on the object) would be removed followed by updating the last date of sync.

The default status change of an object were to be `deleted` by SSoT DiffSync operations, will be specified below. These are the default transitions states, unless otherwise specified in the configuration options of the integration by a user.

- Device -> Offline (Auto deletes tag upon recovery)
- IPAddresses -> Deprecated (Does not auto-delete tag upon recovery)
- VLAN -> Deprecated (Auto deletes tag upon recovery)
- Site -> Decommissioning (Auto deletes tag upon recovery)
- Interfaces -> Tagged with `SSoT Safe Delete` (Does not auto-delete Tag upon recovery)
- Cable -> Decommissioning (Auto deletes tag upon recovery)

If you would like to change the default status change value, ensure you provide a valid status name available for the referenced object. Not all objects share the same `Status`.

![Safe Delete](../../images/ipfabric-safe-delete.png)

An example object that's been modified by SSoT App and tagged as `SSoT Safe Delete` and `SSoT Synced from IPFabric`. Notice the Status and child object, IPAddress has also changed to Deprecated and, it's status changed and tagged as well.

![Safe Delete Address](../../images/ipfabric-safe-delete-ipaddress.png)

During job execution, a warning will be provided to show the status change of an object.

![Safe Delete Status Change](../../images/ipfabric-safe-delete-log.png)

If an object has already been updated with the tag, a warning message will be displayed and the object will not be modified (including sync date).

![Safe Delete Status Change](../../images/ipfabric-safe-delete-debug-skip.png)

## ChatOps

As part of the SSoT synchronization capabilities with IP Fabric, this integration extends the [Nautobot ChatOps app](https://github.com/nautobot/nautobot-app-chatops) by providing users with the ability to begin the sync job from a ChatOps command (Slack).

![ssot-chatops-sync](../../images/ipfabric-chatops-ssot.png)

## Screenshots

Main SSoT IPFabric Dashboard:

![Dashboard](../../images/ipfabric-dashboard.png)

Sync Details:

![Dashboard](../../images/ipfabric-sync-details.png)
