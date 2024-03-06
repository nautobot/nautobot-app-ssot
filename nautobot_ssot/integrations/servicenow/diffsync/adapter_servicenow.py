# pylint: disable=duplicate-code
"""DiffSync adapter for ServiceNow."""
from base64 import b64encode
import json
import os

from collections import defaultdict
from diffsync import DiffSync
from diffsync.enum import DiffSyncFlags
from diffsync.exceptions import ObjectAlreadyExists, ObjectNotFound
from jinja2 import Environment, FileSystemLoader
import yaml

from . import models


class ServiceNowDiffSync(DiffSync):
    """DiffSync adapter using pysnow to communicate with a ServiceNow server."""

    # create defaultdict object to store objects that should be deleted from ServiceNow if they do not
    # exist in Nautobot
    objects_to_delete = defaultdict(list)

    company = models.Company
    device = models.Device  # child of location
    interface = models.Interface  # child of device
    location = models.Location
    product_model = models.ProductModel  # child of company

    top_level = [
        "company",
        "location",
    ]

    DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))

    def __init__(self, *args, client=None, job=None, sync=None, site_filter=None, **kwargs):
        """Initialize the ServiceNowDiffSync adapter."""
        super().__init__(*args, **kwargs)
        self.client = client
        self.job = job
        self.sync = sync
        self.site_filter = site_filter
        self.sys_ids = {}
        self.mapping_data = []

        # Since a device may contain dozens or hundreds of interfaces,
        # to improve performance when a device is created, we use ServiceNow's bulk/batch API to
        # create all of these interfaces in a single API call.
        self.interfaces_to_create_per_device = {}

    def load(self):
        """Load data via pysnow."""
        self.mapping_data = self.load_yaml_datafile("mappings.yaml")

        for modelname, entry in self.mapping_data.items():
            if modelname == "location" and self.site_filter is not None:
                # Load the specific record, if any, corresponding to the site_filter
                record = (
                    self.client.resource(api_path=f"/table/{entry['table']}")
                    .get(query={"name": self.site_filter.name})
                    .one_or_none()
                )
                if record:
                    location = self.load_record(entry["table"], record, self.location, entry["mappings"])
                    # Load all of its ServiceNow ancestors as well
                    name_tokens = location.full_name.split("/")
                    ancestor_full_name = ""
                    for name_token in name_tokens[:-1]:
                        if ancestor_full_name:
                            ancestor_full_name += "/"
                        ancestor_full_name += name_token
                        record = (
                            self.client.resource(api_path=f"/table/{entry['table']}")
                            .get(query={"full_name": ancestor_full_name})
                            .one_or_none()
                        )
                        if record:
                            self.load_record(entry["table"], record, self.location, entry["mappings"])
                # Load all Nautobot ancestor records as well
                # This is so in case the Nautobot ancestors exist in ServiceNow but aren't linked to the record,
                # we link them together instead of creating new, redundant ancestor records in ServiceNow.
                ancestor = self.site_filter.region
                while ancestor is not None:
                    try:
                        self.get(self.location, ancestor.name)
                    except ObjectNotFound:
                        record = (
                            self.client.resource(api_path=f"/table/{entry['table']}")
                            .get(query={"name": ancestor.name})
                            .one_or_none()
                        )
                        if record:
                            self.load_record(entry["table"], record, self.location, entry["mappings"])
                    ancestor = ancestor.parent

                self.job.logger.info(
                    f"Loaded a total of {len(self.get_all('location'))} location records from ServiceNow."
                )

            else:
                self.load_table(modelname, **entry)

    @classmethod
    def load_yaml_datafile(cls, filename, config=None):
        """Get the contents of the given YAML data file.

        Args:
          filename (str): Filename within the 'data' directory.
          config (dict): Data for Jinja2 templating.
        """
        file_path = os.path.join(cls.DATA_DIR, filename)
        if not os.path.isfile(file_path):
            raise RuntimeError(f"No data file found at {file_path}")
        if not config:
            config = {}
        env = Environment(loader=FileSystemLoader(cls.DATA_DIR), autoescape=True)
        template = env.get_template(filename)
        populated = template.render(config)
        return yaml.safe_load(populated)

    def load_table(self, modelname, table, mappings, **kwargs):
        """Load data from the ServiceNow "table" into the DiffSync model.

        Args:
          modelname (str): DiffSync model class identifier, such as "location" or "device".
          table (str): ServiceNow table name, such as "cmdb_ci_ip_switch"
          mappings (list): List of dicts, each stating how to populate a field in the model.
          **kwargs: Optional arguments, all of which default to False if unset:

            - parent (dict): Dict of {"modelname": ..., "field": ...} used to link table records back to their parents
        """
        model_cls = getattr(self, modelname)
        self.job.logger.info(f"Loading ServiceNow table `{table}` into {modelname} instances...")

        if "parent" not in kwargs:
            # Load the entire table
            for record in self.client.all_table_entries(table):
                self.load_record(table, record, model_cls, mappings, **kwargs)
        else:
            # Load items per parent object that we know/care about
            # This is necessary because, for example, the cmdb_ci_network_adapter table contains network interfaces
            # for ALL types of devices (servers, switches, firewalls, etc.) but we only have switches as parent objects
            for parent in self.get_all(kwargs["parent"]["modelname"]):
                for record in self.client.all_table_entries(table, {kwargs["parent"]["column"]: parent.sys_id}):
                    self.load_record(table, record, model_cls, mappings, **kwargs)

        self.job.logger.info(
            f"Loaded {len(self.get_all(modelname))} {modelname} records from ServiceNow table `{table}`."
        )

    def load_record(self, table, record, model_cls, mappings, **kwargs):
        """Helper method to load_table()."""
        self.sys_ids.setdefault(table, {})[record["sys_id"]] = record

        ids_attrs = self.map_record_to_attrs(record, mappings)
        model = model_cls(**ids_attrs)
        modelname = model.get_type()

        try:
            self.add(model)
        except ObjectAlreadyExists:
            # The baseline data in a standard ServiceNow developer instance has a number of duplicate Location entries.
            # For now, ignore the duplicate entry and continue
            self.job.logger.warning(f'Ignoring apparent duplicate record for {modelname} "{model.get_unique_id()}".')

        if "parent" in kwargs:
            parent_uid = getattr(model, kwargs["parent"]["field"])
            if parent_uid is None:
                self.job.logger.warning(
                    f'Model {modelname} "{model.get_unique_id}" does not have a parent uid value '
                    f"in field {kwargs['parent']['field']}"
                )
            else:
                parent_model = self.get(kwargs["parent"]["modelname"], parent_uid)
                parent_model.add_child(model)

        return model

    def map_record_to_attrs(self, record, mappings):  # TODO pylint: disable=too-many-branches
        """Helper method to load_table()."""
        attrs = {"sys_id": record["sys_id"]}
        for mapping in mappings:
            value = None
            if "column" in mapping:
                value = record[mapping["column"]]
            elif "reference" in mapping:
                # Reference by sys_id to a field in a record in another table
                table = mapping["reference"]["table"]
                if "key" in mapping["reference"]:
                    key = mapping["reference"]["key"]
                    if key not in record:
                        self.job.logger.warning(f"Key `{key}` is not present in record `{record}`")
                    else:
                        sys_id = record[key]
                else:
                    raise NotImplementedError

                if sys_id:
                    if sys_id not in self.sys_ids.get(table, {}):
                        referenced_record = self.client.get_by_sys_id(table, sys_id)
                        if referenced_record is None:
                            self.job.logger.warning(
                                f"Record `{record.get('name', record)}` field `{mapping['field']}` "
                                f"references sys_id `{sys_id}`, but that was not found in table `{table}`"
                            )
                        else:
                            self.sys_ids.setdefault(table, {})[sys_id] = referenced_record

                    if sys_id in self.sys_ids.get(table, {}):
                        value = self.sys_ids[table][sys_id][mapping["reference"]["column"]]
            else:
                raise NotImplementedError

            attrs[mapping["field"]] = value

        return attrs

    def bulk_create_interfaces(self):
        """Bulk-create interfaces for any newly created devices as a performance optimization."""
        if not self.interfaces_to_create_per_device:
            return

        self.job.logger.info("Beginning bulk creation of interfaces in ServiceNow for newly added devices...")

        sn_resource = self.client.resource(api_path="/v1/batch")
        sn_mapping_entry = self.mapping_data["interface"]

        # One batch API request per new device, consisting of requests to create each interface that the device has
        for request_id, device_name in enumerate(self.interfaces_to_create_per_device.keys()):
            if not self.interfaces_to_create_per_device[device_name]:
                self.job.logger.info("No interfaces to create for this device, continuing")
                continue

            request_data = {
                "batch_request_id": str(request_id),
                "rest_requests": [],
            }

            for inner_request_id, interface in enumerate(self.interfaces_to_create_per_device[device_name]):
                inner_request_payload = interface.map_data_to_sn_record(
                    data={**interface.get_identifiers(), **interface.get_attrs()},
                    mapping_entry=sn_mapping_entry,
                )
                inner_request_body = b64encode(json.dumps(inner_request_payload).encode("utf-8")).decode("utf-8")
                inner_request_data = {
                    "id": str(inner_request_id),
                    "exclude_response_headers": True,
                    "headers": [
                        {"name": "Content-Type", "value": "application/json"},
                        {"name": "Accept", "value": "application/json"},
                    ],
                    "url": f"/api/now/table/{sn_mapping_entry['table']}",
                    "method": "POST",
                    "body": inner_request_body,
                }
                request_data["rest_requests"].append(inner_request_data)

            self.job.logger.debug(
                f'Sending bulk API request to ServiceNow to create interfaces for device "{device_name}":'
                f"\n```\n{json.dumps(request_data, indent=4)}\n```"
            )

            sn_response = sn_resource.request(
                "POST",
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                data=json.dumps(request_data),
            )

            # Get the wrapped requests.Response object from the returned pysnow.Response object
            response = sn_response._response  # pylint: disable=protected-access
            response_data = response.json()

            if response.status_code != 200:
                self.job.logger.error(
                    f"Got status code {response.status_code} from ServiceNow when bulk-creating interfaces:"
                    f"\n```\n{json.dumps(response_data, indent=4)}\n```",
                )
            elif response_data["unserviced_requests"]:
                self.job.logger.warning(
                    "ServiceNow indicated that parts of the bulk request for interface creation "
                    f"were not serviced:\n```\n{json.dumps(response_data['unserviced_requests'], indent=4)}\n```",
                )
            else:
                self.job.logger.debug(
                    f"ServiceNow response: {response.status_code}\n```\n{json.dumps(response_data, indent=4)}\n```"
                )
                self.job.logger.info("Interfaces successfully bulk-created.")

        self.job.logger.info("Bulk creation of interfaces completed.")

    def sync_complete(self, source, diff, flags=DiffSyncFlags.NONE, logger=None):
        """Callback after the `sync_from` operation has completed and updated this instance.

        Note that this callback is **only** triggered if the sync actually resulted in data changes.
        If there are no detected changes, this callback will **not** be called.
        """
        self.bulk_create_interfaces()

        source.tag_involved_objects(target=self)

        # If there are objects inside any of the lists in objects_to_delete then iterate over those objects
        # and remove them from ServiceNow
        if (
            self.objects_to_delete["interface"]
            or self.objects_to_delete["device"]
            or self.objects_to_delete["product_model"]
            or self.objects_to_delete["location"]
            or self.objects_to_delete["company"]
        ):
            for grouping in (
                "interface",
                "device",
                "product_model",
                "location",
                "company",
            ):
                for sn_object in self.objects_to_delete[grouping]:
                    sn_object.delete()
                self.objects_to_delete[grouping] = []
