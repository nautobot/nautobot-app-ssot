"""Jobs for ACI SSoT plugin."""
from distutils.util import strtobool
from django.templatetags.static import static
from django.urls import reverse
from nautobot.extras.jobs import BooleanVar, ChoiceVar, Job
from nautobot_ssot.jobs.base import DataMapping, DataSource
from nautobot_ssot_aci.diffsync.adapters.aci import AciAdapter
from nautobot_ssot_aci.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot_aci.constant import PLUGIN_CFG

name = "Cisco ACI SSoT"  # pylint: disable=invalid-name, abstract-method

aci_creds = {}
for key in PLUGIN_CFG["apics"]:
    subkey = key[key.rfind("_") + 1 :].lower()  # noqa: E203
    aci_creds.setdefault(subkey, {})
    if "USERNAME" in key:
        aci_creds[subkey]["username"] = PLUGIN_CFG["apics"][key]
    if "PASSWORD" in key:
        aci_creds[subkey]["password"] = PLUGIN_CFG["apics"][key]
    if "URI" in key:
        aci_creds[subkey]["base_uri"] = PLUGIN_CFG["apics"][key]
    if "VERIFY" in key:
        aci_creds[subkey]["verify"] = bool(strtobool(PLUGIN_CFG["apics"][key]))
    if "SITE" in key:
        aci_creds[subkey]["site"] = PLUGIN_CFG["apics"][key]
    if "STAGE" in key:
        aci_creds[subkey]["stage"] = PLUGIN_CFG["apics"][key]
    if "TENANT" in key:
        aci_creds[subkey]["tenant_prefix"] = PLUGIN_CFG["apics"][key]


class AciDataSource(DataSource, Job):  # pylint: disable=abstract-method
    """ACI SSoT Data Source."""

    apic_choices = [(key, key) for key in aci_creds]

    apic = ChoiceVar(choices=apic_choices, label="Select APIC")

    debug = BooleanVar(description="Enable for verbose debug logging.")

    class Meta:  # pylint: disable=too-few-public-methods
        """Information about the Job."""

        name = "Cisco ACI Data Source"
        data_source = "ACI"
        data_source_icon = static("nautobot_ssot_aci/aci.png")
        description = "Sync information from ACI to Nautobot"

    def __init__(self):
        """Initialize AciDataSource."""
        super().__init__()

    @classmethod
    def data_mappings(cls):
        """Shows mapping of models between ACI and Nautobot."""
        return (
            DataMapping("Tenant", None, "Tenant", reverse("tenancy:tenant_list")),
            DataMapping("Node", None, "Device", reverse("dcim:device_list")),
            DataMapping("Model", None, "Device Type", reverse("dcim:devicetype_list")),
            DataMapping("Controller/Leaf/Spine OOB Mgmt IP", None, "IP Address", reverse("ipam:ipaddress_list")),
            DataMapping("Subnet", None, "Prefix", reverse("ipam:prefix_list")),
            DataMapping("Interface", None, "Interface", reverse("dcim:interface_list")),
            DataMapping("VRF", None, "VRF", reverse("ipam:vrf_list")),
        )

    def load_source_adapter(self):
        """Method to instantiate and load the ACI adapter into `self.source_adapter`."""
        self.source_adapter = AciAdapter(job=self, sync=self.sync, client=aci_creds[self.kwargs["apic"]])
        self.source_adapter.load()

    def load_target_adapter(self):
        """Method to instantiate and load the Nautobot adapter into `self.target_adapter`."""
        self.target_adapter = NautobotAdapter(job=self, sync=self.sync, client=aci_creds[self.kwargs["apic"]])
        self.target_adapter.load()


jobs = [AciDataSource]
