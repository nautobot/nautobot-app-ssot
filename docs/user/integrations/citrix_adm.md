# Citrix ADM SSoT Integration

The Citrix ADM SSoT integration is built as part of the [Nautobot Single Source of Truth (SSoT)](https://github.com/nautobot/nautobot-app-ssot) app. The SSoT app enables Nautobot to be the aggregation point for data coming from multiple systems of record (SoR).

From Citrix ADM into Nautobot, it synchronizes the following objects:

| Citrix ADM              | Nautobot                     |
| ----------------------- | ---------------------------- |
| Datacenter              | Location*                    |
| Devices                 | Devices                      |
| Hardwares               | DeviceTypes                  |
| OSVersions              | SoftwareVersions             |
| Ports                   | Interfaces                   |
| Prefixes                | Prefixes                     |
| IP Addresses            | IP Addresses                 |

## Usage

Once the app is installed and configured, you will be able to perform an inventory ingestion from an individual or multiple Citrix ADM instances into Nautobot. From the Nautobot SSoT Dashboard view (`/plugins/ssot/`), Citrix ADM will show as a Data Source.

![Dashboard View](../../images/citrix_adm_dashboard.png)

From the Dashboard, you can also view more information about the App by clicking on the `Citrix ADM to Nautobot` link and see the Detail view. This view will show the mappings of Citrix ADM objects to Nautobot objects, the sync history, and other configuration details for the App:

![Detail View](../../images/citrix_adm_detail-view.png)

In order to utilize this integration you must first enable the Job. You can find the available installed Jobs under Jobs -> Jobs:

![Job List](../../images/citrix_adm_job_list.png)

To enable the Job you must click on the orange pencil icon to the right of the `Citrix ADM to Nautobot` Job. You will be presented with the settings for the Job as shown below:

![Job Settings](../../images/citrix_adm_job_settings.png)

You'll need to check the `Enabled` checkbox and then the `Update` button at the bottom of the page. You will then see that the play button next to the Job changes to blue and becomes functional, linking to the Job form.

![Enabled Job](../../images/citrix_adm_enabled_job.png)

Once the Job is enabled, you'll need to manually create a few objects in Nautobot to use with the Job. First, you'll need to create the Secrets, SecretsGroup, and ExternalIntegration as detailed in the [Citrix ADM Configuration](../../admin/integrations/citrix_adm_setup.md#configuration) instructions.

> You can utilize multiple Citrix ADM Controllers with this integration as long as you specify a unique Tenant per Controller. The failure to use differing Tenants will have the Devices, Prefixes, and IPAddresses potentially removed if they are non-existent on the additional Controller. Locations should remain unaffected.

With those configured, you will then need to define a LocationType to use for the imported Networks. With those created, you can run the Job to start the synchronization:

![Job Form](../../images/citrix_adm_job_form.png)

If you wish to just test the synchronization but not have any data created in Nautobot you'll want to select the `Dryrun` toggle. Clicking the `Debug` toggle will enable more verbose logging to inform you of what is occuring behind the scenes. After those toggles there are also dropdowns that allow you to specify the Citrix ADM instance(s) to synchronize with and to define the LocationType to use for the imported Datacenters from those instances. In addition, there are also some optional settings on the Job form:

- Should the LocationType that you specify for the imported Networks require a parent Location to be assigned, you can define this parent one of two ways:

1. The Parent Location field allows you to define a singular Location that will be assigned as the parent for all imported Datacenter Locations.

2. The Location Mapping field allows you to define a dictionary of Location mappings. This feature is intended for specifying parent Locations for the Datacenter Locations in Citrix ADM. This is useful if this information is missing from Citrix ADM but required for Nautobot or to allow you to change the information as it's imported to match information from another System of Record. The expected pattern for this field is `{"<Location Name>": {"parent": "<Parent location Name>"}}`.

In addition, the ability to assign Roles to your imported Devices as provided with the Hostname Mapping field. This field allows you to specify a list of tuples containing a regular expression pattern to match against Device hostnames and the Role to assign if matched. Ex: [(".*INT-LB.*", "Internal Load-Balancer")]

- Finally there is an option to specify a Tenant to be assigned to the imported Devices, Prefixes, and IPAddresses. This is handy for cases where you have multiple Citrix ADM instances that are used by differing business units.

Running this Job will redirect you to a `Nautobot Job Result` view.

Once the Job has finished you can click on the `SSoT Sync Details` button at the top right of the Job Result page to see detailed information about the data that was synchronized from Citrix ADM and the outcome of the sync Job.
