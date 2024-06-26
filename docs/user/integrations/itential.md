## Itential Automation Gateway SSoT Integration

The Itential SSoT integration is built as part of the Nautobot Single Source of Truth (SSoT) app. This app enables Nautobot to serve as the aggregation point for inventories in the Itential Automation Gateway (IAG).

## IAG Inventory

The IAG can communicate with network devices using several methods. Each of these communication methods requires a separate inventory in the IAG database. Currently, only the Ansible/Scripts inventory is supported. Support for other inventories may be added at a later date.

Below is a table displaying the IAG communication methods.

| Communication Method |
| ---------------------|
| Ansible              |
| GRPC                 |
| HTTP Requests        |
| NETCONF              |
| Netmiko              |
| Nornir               |
| Scripts              |
| Terraform            |

As a side note, you can create your own scripts or Ansible playbooks that utilize communication methods such as GRPC, HTTP, NETCONF, etc. Itential will use the default Ansible inventory to perform tasks on remote devices with these communication methods. However, if you want the Itential Automation Platform (IAP) to communicate with a remote device using a communication method that is not Ansible or scripts, it requires a separate inventory and iteration by the SSoT App to support those inventories.

## Nautobot to Itential Automation Gateway Modeling

### Device Modeling

Currently, the Itential SSoT integration supports only a one-way sync from Nautobot to the (IAG) devices. For a device object to be synced to an (IAG) host, certain data is required in Nautobot:

1. The device must have an [RFC 1123](https://www.rfc-editor.org/rfc/rfc1123) compliant hostname. The IAG will respond with an HTTP error for non-compliant hostnames.
2. The device must have a management IP address assigned in Nautobot. This management IP address is used to assign the `ansible_host` variable in the IAG inventory.
3. For Ansible to determine how to communicate with a remote device, the device needs to be assigned to a platform in Nautobot. The platform must have an appropriate network driver assigned. The Itential SSoT Integration will use this network driver to determine how to assign the `ansible_network_os` Ansible variable in the IAG inventory.

Additional device variables can be assigned to IAG inventories by utilizing Nautobot config contexts. Config contexts will be added to the IAG Ansible inventory as a one-to-one mapping. These config contexts can also be used to override variables for a device, such as the `ansible_network_os`.

### Ansible Default Group Modeling

Ansible uses a default group called `all` to define variables that are common across all devices. More specific groups and devices can override the variables defined in the `all` group. The Itential SSoT integration uses the `all` group to define the `ansible_username` and `ansible_password` variables, which IAG uses to communicate with remote devices. The Itential SSoT integration consumes the device secrets defined in the Itential Setup in the admin section of this documentation.
