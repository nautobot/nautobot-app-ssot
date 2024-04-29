"""Interactions with ServiceNow APIs."""

import logging

# from pysnow import Client
from nautobot_ssot.integrations.servicenow.third_party.pysnow import Client

# from pysnow.exceptions import MultipleResults
from nautobot_ssot.integrations.servicenow.third_party.pysnow.exceptions import MultipleResults
import requests  # pylint: disable=wrong-import-order


logger = logging.getLogger(__name__)


class ServiceNowClient(Client):
    """Extend the pysnow Client with additional use-case-specific functionality."""

    def __init__(self, instance=None, username=None, password=None, worker=None):
        """Create a ServiceNowClient with the appropriate environment parameters."""
        super().__init__(instance=instance, user=username, password=password)

        self.worker = worker

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
            return None
        except MultipleResults:
            logger.error('Multiple results unexpectedly returned when querying table "%s" with "%s"', table, query)
            return None

        if not result:
            logger.warning("Query %s did not match an object in table %s", query, table)
        return result
