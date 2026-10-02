"""Interactions with ServiceNow APIs."""

import logging

import requests  # pylint: disable=wrong-import-order

from nautobot_ssot.integrations.servicenow.exceptions import AmbiguousReferenceError

# from pysnow import Client
from nautobot_ssot.integrations.servicenow.third_party.pysnow import Client

# from pysnow.exceptions import MultipleResults
from nautobot_ssot.integrations.servicenow.third_party.pysnow.exceptions import MultipleResults

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

    @property
    def logger(self):
        """Prefer the Job logger when a Job is attached; fallback to the module logger."""
        return self.worker.logger if self.worker is not None else logger

    def all_table_entries(self, table, query=None, fields=None, limit=10000):
        """Iterator over all records in a given table, paginating through the full result set.

        Args:
            table (str): ServiceNow table name.
            query (dict): Optional query filter.
            fields (list): Optional columns to request via `sysparm_fields`; all columns are returned when omitted.
            limit (int): Requested page size (`sysparm_limit`). ServiceNow may return fewer records per response
                than requested, so pages advance by the number of records actually returned and stop on an empty page.
        """
        if not query:
            query = {}
        fields = fields or []
        if self.worker and self.worker.debug:
            self.logger.debug("Getting all entries in table %s matching query %s", table, query)
        offset = 0
        while True:
            count = 0
            page = (
                self.resource(api_path=f"/table/{table}")
                .get(query=query, fields=fields, limit=limit, offset=offset, stream=True)
                .all()
            )
            for record in page:
                count += 1
                yield record
            if count == 0:
                break
            offset += count

    def get_by_sys_id(self, table, sys_id):
        """Get a record with a given sys_id from a given table."""
        return self.get_by_query(table, {"sys_id": sys_id})

    def get_by_query(self, table, query):
        """Get a specific record from a given table.

        Returns None if the query matched nothing, or if ServiceNow rejected the request.

        Raises:
            AmbiguousReferenceError: If more than one record matched. Callers that write a reference field
                must not silently skip the field, so ambiguity is surfaced rather than collapsed to None.
        """
        if self.worker and self.worker.debug:
            self.logger.debug("Querying table %s with query %s", table, query)
        try:
            result = self.resource(api_path=f"/table/{table}").get(query=query).one_or_none()
        except requests.exceptions.HTTPError as exc:
            # Raised if for example we get a 400 response because we're querying a nonexistent table
            self.logger.error("HTTP error encountered: %s", exc)
            return None
        except MultipleResults as exc:
            column, value = next(iter(query.items())) if len(query) == 1 else (str(sorted(query)), query)
            raise AmbiguousReferenceError(table=table, column=column, value=value) from exc

        if not result:
            self.logger.warning("Query %s did not match an object in table %s", query, table)
        return result

    def get_all_by_query(self, table, query, limit=100):
        """Get every record matching a query in a given table.

        Unlike `get_by_query`, this never raises on ambiguity: it is used by the write path, which needs to
        report *which* records collided. The limit is intentionally small; callers only need to distinguish
        zero from one from many, and to name a handful of candidates in an error message.

        Returns:
            list: Matching records, or an empty list if ServiceNow rejected the request.
        """
        if self.worker and self.worker.debug:
            self.logger.debug("Querying table %s for all records matching query %s", table, query)
        try:
            return list(self.resource(api_path=f"/table/{table}").get(query=query, limit=limit).all())
        except requests.exceptions.HTTPError as exc:
            self.logger.error("HTTP error encountered: %s", exc)
            return []
