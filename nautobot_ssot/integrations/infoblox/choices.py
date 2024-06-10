"""Choicesets for Infoblox integration."""

from nautobot.apps.choices import ChoiceSet


class FixedAddressTypeChoices(ChoiceSet):
    """Choiceset used by SSOTInfobloxConfig.

    Infoblox supports the below values for `match_client` field in the `fixed_address` object:

        CIRCUIT_ID
        CLIENT_ID
        MAC_ADDRESS
        REMOTE_ID
        RESERVED

    We currently support creation of MAC_ADDRESS and RESERVED types only.
    """

    DONT_CREATE_RECORD = "do-not-create-record"
    MAC_ADDRESS = "create-fixed-with-mac-address"
    RESERVED = "create-reservation-no-mac-address"

    CHOICES = (
        (DONT_CREATE_RECORD, "Do not create fixed address"),
        (MAC_ADDRESS, "Create record with MAC adddres"),
        (RESERVED, "Create reservation with no MAC address"),
    )


class DNSRecordTypeChoices(ChoiceSet):
    """Choiceset used by SSOTInfobloxConfig."""

    DONT_CREATE_RECORD = "do-not-create-dns-record"
    HOST_RECORD = "create-host-record"
    A_RECORD = "create-a-record"
    A_AND_PTR_RECORD = "create-a-and-ptr-records"

    CHOICES = (
        (DONT_CREATE_RECORD, "Do not create DNS record"),
        (HOST_RECORD, "Create Host record"),
        (A_RECORD, "Create A record"),
        (A_AND_PTR_RECORD, "Create A and PTR records"),
    )
