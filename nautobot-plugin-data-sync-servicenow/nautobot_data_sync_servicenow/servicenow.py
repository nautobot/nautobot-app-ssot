"""Interactions with ServiceNow APIs."""
import logging
import os

from pysnow import Client
import requests


logger = logging.getLogger(__name__)


def python_value_to_string(value):
    """The ServiceNow REST API represents everything as a string, so map Python values to their API representation."""
    if value is None:
        value = ""
    elif isinstance(value, bool):
        value = str(value).lower()
    else:
        value = str(value)
    return value


class ServiceNowClient(Client):
    """Extend the pysnow Client with additional use-case-specific functionality."""

    def __init__(self, instance="", username="", password="", app_prefix="", worker=None):
        """Create a ServiceNowClient with the appropriate environment parameters."""
        super().__init__(instance=instance, user=username, password=password)

        self.worker = worker
        self.app_prefix = app_prefix

        # When getting records from ServiceNow, for reference fields, only return the sys_id value of the reference,
        # rather than returning a dict of {"link": "https://<instance>.servicenow.com/...", "value": <sys_id>}
        # We don't need the link for our purposes, and including it makes it harder to preserve idempotence.
        self.parameters.exclude_reference_link = True

    def all_table_entries(self, table, query=None):
        """Iterator over all records in a given table."""
        if not query:
            query = {}
        logger.debug("Getting all entries in table %s matching query %s", table, query)
        yield from self.resource(api_path=f"/table/{table}").get(query=query, stream=True).all()

    def get_by_sys_id(self, table, sys_id):
        """Get a record with a given sys_id from a given table."""
        return self.get_by_query(table, {"sys_id": sys_id})

    def get_by_query(self, table, query):
        """Get a specific record from a given table."""
        logger.debug("Querying table %s with query %s", table, query)
        try:
            result = self.resource(api_path=f"/table/{table}").get(query=query).one_or_none()
        except requests.exceptions.HTTPError as exc:
            # Raised if for example we get a 400 response because we're querying a nonexistent table
            logger.error("HTTP error encountered: %s", exc)
            result = None

        if not result:
            logger.warning("Query %s did not match an object in table %s", query, table)
        return result

    def ensure_choice(self, table, element, label, value=None):
        """Ensure that the given choice value exists for the given element of the given table.

        Args:
          table (str): Name of the table this choice belongs to
          element (str): Name of the table field this choice belongs to
          label (str): Human-readable label for this choice value.
          value (str): Backend value of this choice.
        """
        if not value:
            value = label

        sys_choice = self.resource(api_path="/table/sys_choice")
        query = {"name": table, "element": element, "label": label, "value": value}
        record = sys_choice.get(query=query).one_or_none()
        if record:
            self.worker.unchanged("No changes to choice %r for field %r in table %r", label, element, table)
        else:
            if not self.worker.dry_run:
                sys_choice.create(payload=query)
            self.worker.created("Created choice %r for field %r in table %r", label, element, table)

    def ensure_field(self, table, field, datatype, **kwargs):
        """Ensure that the given custom field exists in the given table.

        Args:
          table (str): Name of the table to inspect/modify
          field (str): Slug of the field to ensure
          datatype (str): Datatype human-readable name ("string", "longint", etc.) as defined by ServiceNow.
          **kwargs: Additional parameters to set on the field (``column_label``, ``max_length``, etc.)
        """
        if "column_label" not in kwargs:
            kwargs["column_label"] = field.replace("_", " ").title()

        # In all the examples I've found online, people are setting `internal_type` to a sys_id value.
        # The below is how to find the sys_id for a given type such as string, longint, reference, etc.
        # However, in my experimentation, just using the type name string seems to work just as well
        # and is less error-prone.
        #
        # sys_glide = self.resource(api_path="/table/sys_glide_object")
        # datatype_sys_id_record = sys_glide.get(query={"label": datatype.title()}).one_or_none()
        # if not datatype_sys_id_record:
        #     logger.error("No datatype %r found", datatype)
        #     return
        # datatype_sys_id = datatype_sys_id_record["sys_id"]

        sys_dict = self.resource(api_path="/table/sys_dictionary")
        query = {"name": table, "element": field}
        updates = {"internal_type": datatype, **kwargs}
        record = sys_dict.get(query=query).one_or_none()
        if record:
            changed = update(record, updates)
            if changed:
                if not self.worker.dry_run:
                    record = sys_dict.update(query=query, payload=record)
                self.worker.updated("Updated existing field %r in table %r", field, table)
            else:
                self.worker.unchanged("No changes to field %r in table %r", field, table)
        else:
            if not self.worker.dry_run:
                record = sys_dict.create(payload={**query, **updates})
            self.worker.created("Added field %r to table %r", field, table)

        # TODO: can we also automatically add this field to the form layout for this table?

    def ensure_table(self, table_name, label=None, fields=()):
        """Ensure that the given custom table exists and is correctly defined.

        Args:
          table_name (str): Table slug
          label (str): Human-readable label for this table
          fields (list): List of (name, type, kwargs, choices) to pass through to :meth:`ensure_field`
        """
        if not label:
            label = table_name.upper()

        sys_db = self.resource(api_path="/table/sys_db_object")
        query = {"name": table_name}
        updates = {"label": label}
        record = sys_db.get(query=query).one_or_none()
        if record:
            changed = update(record, updates)
            if changed:
                if not self.worker.dry_run:
                    record = sys_db.update(query=query, payload=record)
                self.worker.updated("Updated existing table %r", table_name)
            else:
                self.worker.unchanged("No changes to definition of table %r", table_name)
        else:
            if not self.worker.dry_run:
                record = sys_db.create(payload={**query, **updates})
            self.worker.created("Created table %s", table_name)

        for slug, datatype, kwargs, choices in fields:
            # Create fields in this table.
            self.ensure_field(table_name, slug, datatype, **kwargs)
            if datatype == "choice":
                for choice in choices:
                    self.ensure_choice(table_name, slug, choice)
            elif choices:
                logger.error("Choices are specified for non-choice field %r of type %s", slug, datatype)

        # TODO: can we also automatically add a link to this table view?
