"""Exceptions specific to the ServiceNow SSoT integration."""


class ServiceNowReferenceError(Exception):  # pylint: disable=too-many-instance-attributes
    """A ServiceNow reference (foreign key) field could not be resolved to exactly one record.

    Raising rather than returning None is deliberate: a swallowed lookup failure used to leave the
    reference column unwritten while the sync still reported success.
    """

    cause = "could not be resolved"
    remedy = ""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        table,
        column,
        value,
        modelname=None,
        unique_id=None,
        field=None,
        candidates=None,
        unapplied=None,
    ):
        """Record everything needed to tell the user which write was skipped and why.

        Args:
            table (str): ServiceNow table that was queried.
            column (str): Column of `table` used as the lookup key.
            value: Value that was looked up in `column`.
            modelname (str): DiffSync model name of the record being written, if known.
            unique_id (str): DiffSync unique ID of the record being written, if known.
            field (str): DiffSync field whose value could not be resolved, if known.
            candidates (list): sys_ids of the records that matched, when more than one did.
            unapplied (list): Disambiguating fields that were unavailable, and so were not applied.
        """
        self.table = table
        self.column = column
        self.value = value
        self.modelname = modelname
        self.unique_id = unique_id
        self.field = field
        self.candidates = list(candidates or [])
        self.unapplied = list(unapplied or [])
        super().__init__(self._describe())

    def _describe(self):
        """Render the single-line diagnostic used for log messages."""
        subject = "Reference lookup"
        if self.modelname:
            subject = self.modelname
            if self.unique_id:
                subject += f' "{self.unique_id}"'
            if self.field:
                subject += f' field "{self.field}"'
        message = f'{subject}: {self.cause} in ServiceNow table "{self.table}" for {self.column}="{self.value}"'
        if self.candidates:
            message += f" (candidate sys_ids: {', '.join(self.candidates)})"
        if self.unapplied:
            message += (
                f"; could not narrow the lookup by {', '.join(self.unapplied)} "
                "because those values were not available"
            )
        if self.remedy:
            message += f". {self.remedy}"
        return message

    def as_csv_row(self):
        """Render as a row for the `unresolved_references.txt` job artifact."""
        fields = [
            self.modelname or "",
            self.unique_id or "",
            self.field or "",
            str(self.value),
            self.table,
            self.column,
            self.cause,
            " ".join(self.candidates),
        ]
        return ",".join(f'"{field}"' for field in fields)

    @staticmethod
    def csv_header():
        """Header row matching `as_csv_row`."""
        return "modelname,unique_id,field,value,table,column,cause,candidate_sys_ids"


class AmbiguousReferenceError(ServiceNowReferenceError):
    """More than one record in the referenced ServiceNow table matched the lookup."""

    cause = "matched more than one record"
    remedy = "Add a `match` clause to this reference in mappings.yaml, or de-duplicate the ServiceNow records"


class MissingReferenceError(ServiceNowReferenceError):
    """No record in the referenced ServiceNow table matched the lookup."""

    cause = "matched no record"
    remedy = "Create the referenced record in ServiceNow, or sync it before the record that references it"
