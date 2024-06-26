"""Models implementation for SSOT Infoblox."""

import ipaddress

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

try:
    from nautobot.apps.constants import CHARFIELD_MAX_LENGTH
except ImportError:
    CHARFIELD_MAX_LENGTH = 255

from nautobot.core.models.generics import PrimaryModel
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import SecretsGroupAssociation

from nautobot_ssot.integrations.infoblox.choices import (
    DNSRecordTypeChoices,
    FixedAddressTypeChoices,
    InfobloxDeletableModelChoices,
    NautobotDeletableModelChoices,
)


def _get_default_sync_filters():
    """Provides default value for SSOTInfobloxConfig infoblox_sync_filters field."""
    return [{"network_view": "default"}]


def _get_default_cf_fields_ignore():
    """Provides default value for SSOTInfobloxConfig cf_fields_ignore field."""
    return {"extensible_attributes": [], "custom_fields": []}


class SSOTInfobloxConfig(PrimaryModel):  # pylint: disable=too-many-ancestors
    """SSOT Infoblox Configuration model."""

    name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, unique=True)
    description = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH,
        blank=True,
    )
    default_status = models.ForeignKey(
        to="extras.Status",
        on_delete=models.PROTECT,
        verbose_name="Default Object Status",
        help_text="Default Object Status",
    )
    infoblox_instance = models.ForeignKey(
        to="extras.ExternalIntegration",
        on_delete=models.PROTECT,
        verbose_name="Infoblox Instance Config",
        help_text="Infoblox Instance",
    )
    infoblox_wapi_version = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH,
        default="v2.12",
        verbose_name="Infoblox WAPI version",
    )
    enable_sync_to_infoblox = models.BooleanField(
        default=False, verbose_name="Sync to Infoblox", help_text="Enable syncing of data from Nautobot to Infoblox."
    )
    enable_sync_to_nautobot = models.BooleanField(
        default=True, verbose_name="Sync to Nautobot", help_text="Enable syncing of data from Infoblox to Nautobot."
    )
    import_ip_addresses = models.BooleanField(
        default=False,
        verbose_name="Import IP Addresses",
    )
    import_subnets = models.BooleanField(
        default=False,
        verbose_name="Import Networks",
    )
    import_vlan_views = models.BooleanField(
        default=False,
        verbose_name="Import VLAN Views",
    )
    import_vlans = models.BooleanField(
        default=False,
        verbose_name="Import VLANs",
    )
    infoblox_sync_filters = models.JSONField(default=_get_default_sync_filters, encoder=DjangoJSONEncoder)
    infoblox_dns_view_mapping = models.JSONField(default=dict, encoder=DjangoJSONEncoder, blank=True)
    cf_fields_ignore = models.JSONField(default=_get_default_cf_fields_ignore, encoder=DjangoJSONEncoder, blank=True)
    import_ipv4 = models.BooleanField(
        default=True,
        verbose_name="Import IPv4",
    )
    import_ipv6 = models.BooleanField(
        default=False,
        verbose_name="Import IPv6",
    )
    dns_record_type = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH,
        default=DNSRecordTypeChoices.HOST_RECORD,
        choices=DNSRecordTypeChoices,
        verbose_name="DBS record type",
        help_text="Choose what type of Infoblox DNS record to create for IP Addresses.",
    )
    fixed_address_type = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH,
        default=FixedAddressTypeChoices.DONT_CREATE_RECORD,
        choices=FixedAddressTypeChoices,
        help_text="Choose what type of Infoblox fixed IP Address record to create.",
    )
    job_enabled = models.BooleanField(
        default=False,
        verbose_name="Enabled for Sync Job",
        help_text="Enable use of this configuration in the sync jobs.",
    )
    infoblox_deletable_models = models.JSONField(
        encoder=DjangoJSONEncoder,
        default=list,
        blank=True,
        help_text="Model types that can be deleted in Infoblox.",
    )
    nautobot_deletable_models = models.JSONField(
        encoder=DjangoJSONEncoder, default=list, blank=True, help_text="Model types that can be deleted in Nautobot."
    )

    class Meta:
        """Meta class for SSOTInfobloxConfig."""

        verbose_name = "SSOT Infoblox Config"
        verbose_name_plural = "SSOT Infoblox Configs"

    def __str__(self):
        """String representation of singleton instance."""
        return self.name

    def _clean_infoblox_sync_filters(self):  # pylint: disable=too-many-branches
        """Performs validation of the infoblox_sync_filters field."""
        allowed_keys = {"network_view", "prefixes_ipv4", "prefixes_ipv6"}

        if not isinstance(self.infoblox_sync_filters, list):
            raise ValidationError({"infoblox_sync_filters": "Sync filters must be a list."})

        if len(self.infoblox_sync_filters) == 0:
            raise ValidationError(
                {
                    "infoblox_sync_filters": 'At least one filter must be defined. You can use the default one: [{"network_view": "default"}]'
                }
            )

        network_views = set()
        for sync_filter in self.infoblox_sync_filters:
            if not isinstance(sync_filter, dict):
                raise ValidationError({"infoblox_sync_filters": "Sync filter must be a dict."})
            invalid_keys = set(sync_filter.keys()) - allowed_keys
            if invalid_keys:
                raise ValidationError(
                    {"infoblox_sync_filters": f"Invalid keys found in the sync filter: {', '.join(invalid_keys)}."}
                )

            if "network_view" not in sync_filter:
                raise ValidationError({"infoblox_sync_filters": "Sync filter must have `network_view` key defined."})
            network_view = sync_filter["network_view"]
            if not isinstance(network_view, str):
                raise ValidationError({"infoblox_sync_filters": "Value of the `network_view` key must be a string."})

            if network_view in network_views:
                raise ValidationError(
                    {
                        "infoblox_sync_filters": f"Duplicate value for the `network_view` found: {sync_filter['network_view']}."
                    }
                )
            network_views.add(network_view)

            if "prefixes_ipv4" in sync_filter:
                if not isinstance(sync_filter["prefixes_ipv4"], list):
                    raise ValidationError({"infoblox_sync_filters": "Value of the `prefixes_ipv4` key must be a list."})
                if not sync_filter["prefixes_ipv4"]:
                    raise ValidationError(
                        {"infoblox_sync_filters": "Value of the `prefixes_ipv4` key must not be an empty list."}
                    )
                for prefix in sync_filter["prefixes_ipv4"]:
                    try:
                        if "/" not in prefix:
                            raise ValidationError(
                                {
                                    "infoblox_sync_filters": f"IPv4 prefix must have a prefix length defined using `/` format: {prefix}."
                                }
                            )
                        ipaddress.IPv4Network(prefix)
                    except (ValueError, TypeError) as error:
                        raise ValidationError(  # pylint: disable=raise-missing-from
                            {"infoblox_sync_filters": f"IPv4 prefix parsing error: {str(error)}."}
                        )

            if "prefixes_ipv6" in sync_filter:
                if not isinstance(sync_filter["prefixes_ipv6"], list):
                    raise ValidationError({"infoblox_sync_filters": "Value of the `prefixes_ipv6` key must be a list."})
                if not sync_filter["prefixes_ipv6"]:
                    raise ValidationError(
                        {"infoblox_sync_filters": "Value of the `prefixes_ipv6` key must not be an empty list."}
                    )
                for prefix in sync_filter["prefixes_ipv6"]:
                    try:
                        if "/" not in prefix:
                            raise ValidationError(
                                {
                                    "infoblox_sync_filters": f"IPv6 prefix must have a prefix length defined using `/` format: {prefix}."
                                }
                            )
                        ipaddress.IPv6Network(prefix)
                    except (ValueError, TypeError) as error:
                        raise ValidationError(  # pylint: disable=raise-missing-from
                            {"infoblox_sync_filters": f"IPv6 prefix parsing error: {str(error)}."}
                        )

    def _clean_infoblox_instance(self):
        """Performs validation of the infoblox_instance field."""
        if not self.infoblox_instance.secrets_group:
            raise ValidationError({"infoblox_instance": "Infoblox instance must have Secrets groups assigned."})
        try:
            self.infoblox_instance.secrets_group.get_secret_value(
                access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
                secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
            )
        except SecretsGroupAssociation.DoesNotExist:
            raise ValidationError(  # pylint: disable=raise-missing-from
                {
                    "infoblox_instance": "Secrets group for the Infoblox instance must have secret with type Username and access type REST."
                }
            )
        try:
            self.infoblox_instance.secrets_group.get_secret_value(
                access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
                secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
            )
        except SecretsGroupAssociation.DoesNotExist:
            raise ValidationError(  # pylint: disable=raise-missing-from
                {
                    "infoblox_instance": "Secrets group for the Infoblox instance must have secret with type Password and access type REST."
                }
            )

    def _clean_import_ip(self):
        """Performs validation of the import_ipv* fields."""
        if not (self.import_ipv4 or self.import_ipv6):
            raise ValidationError(
                {
                    "import_ipv4": "At least one of `import_ipv4` or `import_ipv6` must be set to True.",
                    "import_ipv6": "At least one of `import_ipv4` or `import_ipv6` must be set to True.",
                }
            )

    def _clean_infoblox_dns_view_mapping(self):
        """Performs validation of the infoblox_dns_view_mapping field."""
        if not isinstance(self.infoblox_dns_view_mapping, dict):
            raise ValidationError(
                {
                    "infoblox_dns_view_mapping": "`infoblox_dns_view_mapping` must be a dictionary mapping network view names to dns view names.",
                },
            )

    def _clean_cf_fields_ignore(self):
        """Performs validation of the cf_fields_ignore field."""
        if not isinstance(self.cf_fields_ignore, dict):
            raise ValidationError(
                {
                    "cf_fields_ignore": "`cf_fields_ignore` must be a dictionary.",
                },
            )
        for key, value in self.cf_fields_ignore.items():
            if key not in (
                "extensible_attributes",
                "custom_fields",
            ):
                raise ValidationError(
                    {
                        "cf_fields_ignore": f"Invalid key name `{key}`. Only `extensible_attributes` and `custom_fields` are allowed.",
                    },
                )
            if not isinstance(value, list) or {type(el) for el in value} - {str}:
                raise ValidationError(
                    {
                        "cf_fields_ignore": f"Value of key `{key}` must be a list of strings.",
                    },
                )

    def _clean_deletable_model_types(self):
        """Performs validation of infoblox_deletable_models and nautobot_deletable_models."""
        for model in self.infoblox_deletable_models:
            if model not in InfobloxDeletableModelChoices.values():
                raise ValidationError(
                    {
                        "infoblox_deletable_models": f"Model `{model}` is not a valid choice.",
                    },
                )

        for model in self.nautobot_deletable_models:
            if model not in NautobotDeletableModelChoices.values():
                raise ValidationError(
                    {
                        "nautobot_deletable_models": f"Model `{model}` is not a valid choice.",
                    },
                )

    def clean(self):
        """Clean method for SSOTInfobloxConfig."""
        super().clean()

        self._clean_infoblox_sync_filters()
        self._clean_infoblox_instance()
        self._clean_import_ip()
        self._clean_infoblox_dns_view_mapping()
        self._clean_cf_fields_ignore()
        self._clean_deletable_model_types()
