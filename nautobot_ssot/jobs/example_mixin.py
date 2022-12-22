"""Sample data-source and data-target Jobs."""
# Skip colon check for multiple statements on one line.
# flake8: noqa: E701

import re
from typing import List, Optional

from django.templatetags.static import static

from diffsync import DiffSync, DiffSyncModel

from nautobot.dcim import models as dcim_models
from nautobot.ipam import models as ipam_models
from nautobot.extras import models as extras_models
from nautobot.extras.jobs import Job
from nautobot.core.graphql import execute_query

from nautobot_ssot.jobs.base import DataMapping, DataSource
from nautobot_ssot.mixins import DiffSyncModelMixIn


from nautobot_ssot.tests.mock.basic import data as example_data


# In a more complex Job, you would probably want to move the DiffSyncModel subclasses into a separate Python module(s).

name = "SSoT MixIn Examples"  # pylint: disable=invalid-name



SITE_QUERY = """{
  sites {
    name
    slug
    id
    devices {
      name
      id
      interfaces {
        name
        id
        mode
        description
        type
        tagged_vlans {
          id
          name
          vid
        }
        untagged_vlan {
          id
          name
          vid
        }
        status {
          slug
          id
        }
        tags {
          name
        }
      }
      status {
        slug
        id
      }
      tags {
        name
        id
      }
    }
    vlans {
      id
      vid
      name
      status {
        slug
        id
      }
      tags {
        name
      }
    }
    tags {
      name
      id
    }
  }
}"""

class Site(DiffSyncModel):
    """Site Model based on DiffSyncModel.

    A site must have a unique name and can be composed of Vlans.
    """

    _modelname = "site"
    _identifiers = ("slug",)
    _attributes = ("name",)
    _children = { "vlan": "vlans", "device": "devices"}

    slug: str
    name: str
    vlans: List[str] = []
    devices: List = []


class Device(DiffSyncModel):
    """Device Model based on DiffSyncModel.

    A device must have a unique name and can be part of a site.
    """

    _modelname = "device"
    _identifiers = ("name",)
    _attributes = ("site",)
    _children = {"interface": "interfaces"}

    name: str
    site: Optional[str]
    interfaces: List = []


class Interface(DiffSyncModel):  # pylint: disable=too-many-instance-attributes
    """Interface Model based on DiffSyncModel.

    An interface must be attached to a device and the name must be unique per device.
    """

    _modelname = "interface"
    _identifiers = ("device", "name")
    _shortname = ("name",)
    _attributes = (
        "description",
        "mode",
        "tagged_vlans",
        "untagged_vlan",
        "type",
        "status",
    )
    _children = {}

    device: str
    name: str

    description: Optional[str]
    mode: Optional[str]
    tagged_vlans: List[str] = []
    untagged_vlan: Optional[str]
    type: str

    status: str


class Vlan(DiffSyncModel):
    """Vlan Model based on DiffSyncModel.

    An Vlan must be associated with a Site and the vlan_id msut be unique within a site.
    """
    _attributes = ("name", "status")
    _modelname = "vlan"
    _identifiers = ("site", "vid")

    site: str
    vid: int
    name: Optional[str]
    status: str

class Status(DiffSyncModel):
    """Status Model based on DiffSyncModel.

    A status must have a unique name and can be composed of Vlans and Prefixes.
    """

    _modelname = "status"
    _identifiers = ("slug",)
    _attributes = ("name",)

    slug: str
    name: str

class NautobotSite(DiffSyncModelMixIn, Site):
    """Simple pass2 docstring."""

    _orm_model = dcim_models.Site
    pk: Optional[str]


class NautobotDevice(DiffSyncModelMixIn, Device):
    """Simple pass3 docstring."""

    _orm_model = dcim_models.Device
    pk: Optional[str]


class NautobotInterface(DiffSyncModelMixIn, Interface):
    """Simple pass4 docstring."""

    _orm_model = dcim_models.Interface
    _foreign_key = {"device": "device", "untagged_vlan": "vlan", "status": "status"}
    _many_to_many = {"tagged_vlans": "vlan"}
    pk: Optional[str]

class NautobotVlan(DiffSyncModelMixIn, Vlan):
    """Simple pass5 docstring."""

    _orm_model = ipam_models.VLAN
    _foreign_key = {"site": "site", "status": "status"}
    pk: Optional[str]

class NautobotStatus(Status):
    """Extension of the Status model."""

    _orm_model = extras_models.Status
    _unique_fields = ("pk",)
    _attributes = ("pk", "name")
    pk: Optional[str]


# In a more complex Job, you would probably want to move each DiffSync subclass into a separate Python module.


class NautobotLocal(DiffSync):
    """DiffSync adapter class for loading data from the local Nautobot instance."""

    # Model classes used by this adapter class
    site = NautobotSite
    device = NautobotDevice
    interface = NautobotInterface
    vlan = NautobotVlan
    status = NautobotStatus

    # Top-level class labels, i.e. those classes that are handled directly rather than as children of other models
    top_level = ("status", "site")

    def __init__(self, *args, job=None, request, **kwargs):
        """Instantiate this class, but do not load data immediately from the local system."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.request = request

    def load(self):
        """Load Region and Site data from the local Nautobot instance."""

        for status in extras_models.Status.objects.all():
            _st = self.status(slug=status.slug, name=status.name, pk=str(status.pk))
            self.add(_st)

        for site_gql in execute_query(query=SITE_QUERY, request=self.request).data["sites"]:
            site = self.site(slug=site_gql["slug"], name=site_gql["name"], pk=site_gql["id"])
            self.add(site)
            for vlan_gql in site_gql["vlans"]:
                vlan = self.vlan(
                    vid=vlan_gql["vid"],
                    name=vlan_gql["name"],
                    status=vlan_gql["status"]["slug"],
                    pk=vlan_gql["id"],
                    site=site_gql["slug"]
                )
                self.add(vlan)
                site.add_child(vlan)
            for device_gql in site_gql["devices"]:
                device = self.device(name=device_gql["name"], pk=device_gql["id"], site=site_gql["slug"])
                self.add(device)
                site.add_child(device)
                for interface_gql in device_gql["interfaces"]:
                    interface = self.interface(
                        name=interface_gql["name"],
                        description=interface_gql["description"],
                        mode=interface_gql["mode"].lower(),
                        tagged_vlans=[vlan["vid"] for vlan in interface_gql.get("tagged_vlans", [])],
                        untagged_vlan=interface_gql["untagged_vlan"]["vid"] if interface_gql.get("untagged_vlan") else None,
                        status=interface_gql["status"]["slug"],
                        pk=interface_gql["id"],
                        device=device_gql["name"],
                        type=re.sub(r'^A_', '', interface_gql["type"]).lower().replace("_", "-"),
                    )
                    self.add(interface)
                    device.add_child(interface)

        # self.job.log_debug(message=f"Loaded {site_model} from local Nautobot instance")


class DictionaryLocal(DiffSync):
    """DiffSync adapter class for loading data from the local Nautobot instance."""

    # Model classes used by this adapter class
    site = Site
    device = Device
    interface = Interface
    vlan = Vlan

    top_level = ("site",)

    def __init__(self, *args, job=None, data, **kwargs):
        """Instantiate this class, but do not load data immediately from the local system."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.data = data

    def load(self):
        """Simple pass7 docstring."""
        self.load_from_dict(self.data)


class SyncFromDictionary(DataSource, Job):
    """Sync Region and Site data from a remote Nautobot instance into the local Nautobot instance."""

    class Meta:
        """Metaclass attributes of ExampleDataSource."""

        name = "Sync from Dictionary to local instance"
        description = 'Example "data source" Job for loading data into Nautobot from a Python dictionary.'
        data_source = "Python Dictionary"
        data_source_icon = static("nautobot_ssot/dictionary_logo.png")
        data_target = "Nautobot (orm)"
        data_target_icon = static("img/nautobot_logo.png")

    # @classmethod
    # def data_mappings(cls):
    #     """This Job maps Region and Site objects from the remote system to the local system."""
    #     return (
    #         DataMapping("Region (remote)", None, "Region (local)", reverse("dcim:region_list")),
    #         DataMapping("Site (remote)", None, "Site (local)", reverse("dcim:site_list")),
    #         DataMapping("Prefix (remote)", None, "Prefix (local)", reverse("ipam:prefix_list")),
    #     )

    def load_source_adapter(self):
        """Method to instantiate and load the SOURCE adapter into `self.source_adapter`."""
        self.source_adapter = DictionaryLocal(job=self, data=example_data)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Method to instantiate and load the TARGET adapter into `self.target_adapter`."""
        self.target_adapter = NautobotLocal(job=self, request=self.request)
        self.target_adapter.load()

    # def lookup_object(self, model_name, unique_id):
    #     """Look up a Nautobot object based on the DiffSync model name and unique ID."""
    #     if model_name == "region":
    #         try:
    #             return Region.objects.get(name=unique_id)
    #         except Region.DoesNotExist:
    #             pass
    #     elif model_name == "site":
    #         try:
    #             return Site.objects.get(name=unique_id)
    #         except Site.DoesNotExist:
    #             pass
    #     elif model_name == "prefix":
    #         try:
    #             return Prefix.objects.get(
    #                 prefix=unique_id.split("__")[0], tenant__slug=unique_id.split("__")[1] or None
    #             )
    #         except Prefix.DoesNotExist:
    #             pass
    #     return None


