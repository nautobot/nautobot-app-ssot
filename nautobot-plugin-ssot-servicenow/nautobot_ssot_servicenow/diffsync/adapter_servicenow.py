"""DiffSync adapter for ServiceNow."""
import os

from diffsync import DiffSync
from diffsync.exceptions import ObjectAlreadyExists
from jinja2 import Environment, FileSystemLoader
import yaml

from . import models


class ServiceNowDiffSync(DiffSync):
    """DiffSync adapter using pysnow to communicate with a ServiceNow server."""

    location = models.Location
    device = models.Device
    interface = models.Interface

    top_level = [
        "location",
    ]

    DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))

    def __init__(self, *args, client=None, worker=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = client
        self.worker = worker
        self.sys_ids = {}
        self.mapping_data = []

    def load(self):
        """Load data via pysnow."""
        self.mapping_data = self.load_yaml_datafile("mappings.yaml", {"app_prefix": self.client.app_prefix})

        for entry in self.mapping_data:
            self.load_table(**entry)

    @classmethod
    def load_yaml_datafile(cls, filename, config):
        """Get the contents of the given YAML data file.

        Args:
          filename (str): Filename within the 'data' directory.
          config (dict): Data for Jinja2 templating.
        """
        file_path = os.path.join(cls.DATA_DIR, filename)
        if not os.path.isfile(file_path):
            raise RuntimeError(f"No data file found at {file_path}")
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
        self.worker.job_log(f"Loading table {table} into {modelname} instances...")

        if "parent" not in kwargs:
            # Load the entire table
            for record in self.client.all_table_entries(table):
                self.load_record(table, record, model_cls, mappings, **kwargs)
        else:
            # Load items per parent object that we know/care about
            # This is necessary because, for example, the cmdb_ci_network_adapter table contains network interfaces
            # for ALL types of devices (servers, switches, firewalls, etc.) but we only have switches as parent objects
            for parent in self.get_all(kwargs["parent"]["modelname"]):
                self.worker.job_log(f"Loading children of {parent}")
                for record in self.client.all_table_entries(table, {kwargs["parent"]["column"]: parent.sys_id}):
                    self.load_record(table, record, model_cls, mappings, **kwargs)

    def load_record(self, table, record, model_cls, mappings, **kwargs):
        """Helper method to load_table()."""
        self.sys_ids.setdefault(table, {})[record["sys_id"]] = record

        ids_attrs = self.map_record_to_attrs(record, mappings)
        model = model_cls(**ids_attrs)
        modelname = model.get_type()

        try:
            self.add(model)
            self.worker.job_log(f"Added {modelname} {model.get_unique_id()}")
        except ObjectAlreadyExists:
            # TODO: the baseline data in ServiceNow has a number of duplicate Location entries. For now, continue
            self.worker.job_log(f"Duplicate object encountered for {modelname} {model.get_unique_id()}")

        if "parent" in kwargs:
            parent_uid = getattr(model, kwargs["parent"]["field"])
            if parent_uid is None:
                self.worker.job_log(
                    f"Model {modelname} {model.get_unique_id} does not have a parent uid value in field {kwargs['parent']['field']}"
                )
            else:
                parent_model = self.get(kwargs["parent"]["modelname"], parent_uid)
                parent_model.add_child(model)
                self.worker.job_log(
                    f"Added {modelname} {model.get_unique_id} as a child of {parent_model.get_type()} {parent_model.get_unique_id()}"
                )

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
                        self.worker.job_log(f"Key {key} is not present in record {record}")
                    else:
                        sys_id = record[key]
                else:
                    raise NotImplementedError

                if sys_id:
                    if sys_id not in self.sys_ids.get(table, {}):
                        referenced_record = self.client.get_by_sys_id(table, sys_id)
                        if referenced_record is None:
                            self.worker.job_log(
                                f"Record references sys_id {sys_id}, but that was not found in table {table}"
                            )
                        else:
                            self.sys_ids.setdefault(table, {})[sys_id] = referenced_record

                    if sys_id in self.sys_ids.get(table, {}):
                        value = self.sys_ids[table][sys_id][mapping["reference"]["column"]]
            else:
                raise NotImplementedError

            attrs[mapping["field"]] = value

        return attrs
