"""Signal handlers for Infoblox integration."""

# pylint: disable=duplicate-code

import ipaddress

from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import (
    CustomFieldTypeChoices,
    RelationshipTypeChoices,
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)
from django.conf import settings
from nautobot_ssot.integrations.infoblox.constant import TAG_COLOR
from nautobot_ssot.integrations.infoblox.choices import DNSRecordTypeChoices, FixedAddressTypeChoices


config = settings.PLUGINS_CONFIG["nautobot_ssot"]


def register_signals(sender):
    """Register signals for Infoblox integration."""
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)


def nautobot_database_ready_callback(
    sender, *, apps, **kwargs
):  # pylint: disable=unused-argument,too-many-locals,too-many-statements
    """Create Tag and CustomField to note System of Record for SSoT.

    Callback function triggered by the nautobot_database_ready signal when the Nautobot database is fully ready.
    """
    # pylint: disable=invalid-name
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    Prefix = apps.get_model("ipam", "Prefix")
    IPAddress = apps.get_model("ipam", "IPAddress")
    Namespace = apps.get_model("ipam", "Namespace")
    Tag = apps.get_model("extras", "Tag")
    Relationship = apps.get_model("extras", "Relationship")
    ExternalIntegration = apps.get_model("extras", "ExternalIntegration")
    Secret = apps.get_model("extras", "Secret")
    SecretsGroup = apps.get_model("extras", "SecretsGroup")
    SecretsGroupAssociation = apps.get_model("extras", "SecretsGroupAssociation")
    Status = apps.get_model("extras", "Status")
    VLAN = apps.get_model("ipam", "VLAN")
    VLANGroup = apps.get_model("ipam", "VLANGroup")
    SSOTInfobloxConfig = apps.get_model("nautobot_ssot", "SSOTInfobloxConfig")

    tag_sync_from_infoblox, _ = Tag.objects.get_or_create(
        name="SSoT Synced from Infoblox",
        defaults={
            "name": "SSoT Synced from Infoblox",
            "description": "Object synced at some point from Infoblox",
            "color": TAG_COLOR,
        },
    )
    for model in [IPAddress, Namespace, Prefix, VLAN]:
        tag_sync_from_infoblox.content_types.add(ContentType.objects.get_for_model(model))
    tag_sync_to_infoblox, _ = Tag.objects.get_or_create(
        name="SSoT Synced to Infoblox",
        defaults={
            "name": "SSoT Synced to Infoblox",
            "description": "Object synced at some point to Infoblox",
            "color": TAG_COLOR,
        },
    )
    for model in [IPAddress, Prefix, VLAN]:
        tag_sync_to_infoblox.content_types.add(ContentType.objects.get_for_model(model))
    custom_field, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_DATE,
        key="ssot_synced_to_infoblox",
        defaults={
            "label": "Last synced to Infoblox on",
        },
    )
    for model in [IPAddress, Prefix, VLAN, VLANGroup]:
        custom_field.content_types.add(ContentType.objects.get_for_model(model))
    range_custom_field, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_TEXT,
        key="dhcp_ranges",
        defaults={
            "label": "DHCP Ranges",
        },
    )
    range_custom_field.content_types.add(ContentType.objects.get_for_model(Prefix))

    mac_address_custom_field, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_TEXT,
        key="mac_address",
        defaults={
            "label": "MAC Address",
        },
    )
    mac_address_custom_field.content_types.add(ContentType.objects.get_for_model(IPAddress))

    fixed_address_comment_custom_field, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_TEXT,
        key="fixed_address_comment",
        defaults={
            "label": "Fixed Address Comment",
        },
    )
    fixed_address_comment_custom_field.content_types.add(ContentType.objects.get_for_model(IPAddress))

    dns_a_record_comment_custom_field, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_TEXT,
        key="dns_a_record_comment",
        defaults={
            "label": "DNS A Record Comment",
        },
    )
    dns_a_record_comment_custom_field.content_types.add(ContentType.objects.get_for_model(IPAddress))

    dns_host_record_comment_custom_field, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_TEXT,
        key="dns_host_record_comment",
        defaults={
            "label": "DNS Host Record Comment",
        },
    )
    dns_host_record_comment_custom_field.content_types.add(ContentType.objects.get_for_model(IPAddress))

    dns_ptr_record_comment_custom_field, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_TEXT,
        key="dns_ptr_record_comment",
        defaults={
            "label": "DNS PTR Record Comment",
        },
    )
    dns_ptr_record_comment_custom_field.content_types.add(ContentType.objects.get_for_model(IPAddress))

    # add Prefix -> VLAN Relationship
    relationship_dict = {
        "label": "Prefix -> VLAN",
        "key": "prefix_to_vlan",
        "type": RelationshipTypeChoices.TYPE_ONE_TO_MANY,
        "source_type": ContentType.objects.get_for_model(Prefix),
        "source_label": "Prefix",
        "destination_type": ContentType.objects.get_for_model(VLAN),
        "destination_label": "VLAN",
    }
    Relationship.objects.get_or_create(label=relationship_dict["label"], defaults=relationship_dict)

    # Migrate existing configuration to a configuration object
    if not SSOTInfobloxConfig.objects.exists():
        default_status_name = str(config.get("infoblox_default_status", ""))
        found_status = Status.objects.filter(name=default_status_name)
        if found_status.exists():
            default_status = found_status.first()
        else:
            default_status, _ = Status.objects.get_or_create(name="Active")

        try:
            infoblox_request_timeout = int(config.get("infoblox_request_timeout", 60))
        except ValueError:
            infoblox_request_timeout = 60

        infoblox_sync_filters = _get_sync_filters()

        secrets_group, _ = SecretsGroup.objects.get_or_create(name="InfobloxSSOTDefaultSecretGroup")
        infoblox_username, _ = Secret.objects.get_or_create(
            name="Infoblox Username - Default",
            defaults={
                "provider": "environment-variable",
                "parameters": {"variable": "NAUTOBOT_SSOT_INFOBLOX_USERNAME"},
            },
        )
        infoblox_password, _ = Secret.objects.get_or_create(
            name="Infoblox Password - Default",
            defaults={
                "provider": "environment-variable",
                "parameters": {"variable": "NAUTOBOT_SSOT_INFOBLOX_PASSWORD"},
            },
        )
        SecretsGroupAssociation.objects.get_or_create(
            secrets_group=secrets_group,
            access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
            defaults={
                "secret": infoblox_username,
            },
        )
        SecretsGroupAssociation.objects.get_or_create(
            secrets_group=secrets_group,
            access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
            defaults={
                "secret": infoblox_password,
            },
        )
        external_integration, _ = ExternalIntegration.objects.get_or_create(
            name="DefaultInfobloxInstance",
            defaults={
                "remote_url": str(config.get("infoblox_url", "https://replace.me.local")),
                "secrets_group": secrets_group,
                "verify_ssl": bool(config.get("infoblox_verify_ssl", True)),
                "timeout": infoblox_request_timeout,
            },
        )

        SSOTInfobloxConfig.objects.create(
            name="InfobloxConfigDefault",
            description="Auto-generated default configuration.",
            default_status=default_status,
            infoblox_wapi_version=str(config.get("infoblox_wapi_version", "v2.12")),
            infoblox_instance=external_integration,
            enable_sync_to_infoblox=bool(config.get("infoblox_enable_sync_to_infoblox", False)),
            enable_sync_to_nautobot=True,
            import_ip_addresses=bool(config.get("infoblox_import_objects_ip_addresses", False)),
            import_subnets=bool(config.get("infoblox_import_objects_subnets", False)),
            import_vlan_views=bool(config.get("infoblox_import_objects_vlan_views", False)),
            import_vlans=bool(config.get("infoblox_import_objects_vlans", False)),
            import_ipv4=True,
            import_ipv6=bool(config.get("infoblox_import_objects_subnets_ipv6", False)),
            job_enabled=True,
            infoblox_sync_filters=infoblox_sync_filters,
            infoblox_dns_view_mapping={},
            cf_fields_ignore={"extensible_attributes": [], "custom_fields": []},
            fixed_address_type=FixedAddressTypeChoices.DONT_CREATE_RECORD,
            dns_record_type=DNSRecordTypeChoices.HOST_RECORD,
        )


def _get_sync_filters():
    """Build sync filters from the existing config."""
    subnets_to_import = config.get("infoblox_import_subnets", [])
    default_sync_filters = [{"network_view": "default"}]
    ipv4_subnets = []
    ipv6_subnets = []
    if not subnets_to_import:
        return default_sync_filters
    if not isinstance(subnets_to_import, list):
        return default_sync_filters
    for subnet in subnets_to_import:
        try:
            ipaddress.IPv4Network(subnet)
            ipv4_subnets.append(subnet)
        except (ValueError, TypeError):
            pass
        try:
            ipaddress.IPv6Network(subnet)
            ipv6_subnets.append(subnet)
        except (ValueError, TypeError):
            pass

    sync_filter = {}
    if ipv4_subnets:
        sync_filter["prefixes_ipv4"] = ipv4_subnets
    if ipv6_subnets:
        sync_filter["prefixes_ipv6"] = ipv6_subnets

    network_view = str(config.get("infoblox_network_view", ""))
    if network_view:
        sync_filter["network_view"] = network_view
    else:
        sync_filter["network_view"] = "default"

    sync_filters = [sync_filter]

    return sync_filters
