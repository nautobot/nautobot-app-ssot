"""Utility functions for working with Nautobot."""

from ipaddress import ip_network

from django.core.exceptions import ObjectDoesNotExist
from nautobot.extras.models import Status
from nautobot.ipam.choices import IPAddressTypeChoices, PrefixTypeChoices
from nautobot.ipam.models import VRF, IPAddress, Namespace, Prefix


def get_or_create_prefix(adapter, address):
    """Given an address, attempt to get or create the parent Nautobot Prefix object."""
    try:
        network_with_prefixlen = str(ip_network(address, strict=False))
        network, prefix_length = network_with_prefixlen.split("/", maxsplit=1)
        try:
            prefix = Prefix.objects.get(
                network=network,
                prefix_length=prefix_length,
                namespace=Namespace.objects.get(name="Global"),
            )
            return prefix
        except ObjectDoesNotExist:
            # Create the Prefix if it does not exist
            if adapter.job.debug:
                adapter.job.logger.debug(f"Creating Prefix {network_with_prefixlen}")
            prefix = Prefix(
                network=network,
                prefix_length=prefix_length,
                namespace=Namespace.objects.get(name="Global"),
                status=Status.objects.get(name="Active"),
                type=PrefixTypeChoices.TYPE_NETWORK,
            )
            prefix.validated_save()
            return prefix
    except Exception as err:  # pylint: disable=broad-exception-caught
        adapter.job.logger.error(f"Error getting or creating Prefix for address {address}, {err}")
        return None


def get_or_create_ip_address(adapter, address, status):  # pylint: disable=inconsistent-return-statements,too-many-return-statements
    """Given an address, attempt to get or create a Nautobot IPAddress object.

    If the IPAddress must be created, also create a valid parent Prefix if required.
    """
    host, mask_length = str(address).split("/", maxsplit=1)
    try:
        # Attempt to get an existing IP Address, update the mask length if necessary
        addr = IPAddress.objects.get(host=host, parent__namespace=Namespace.objects.get(name="Global"))
        # If the existing IP Address has a different mask length, update it
        if str(addr.mask_length) != mask_length:
            if adapter.job.ignore_address_mask:
                adapter.job.logger.warning(
                    f"IP address {address} already exists with mask /{addr.mask_length}; "
                    f"cannot create it with mask /{mask_length}",
                    extra={"object": addr},
                )
                return (None, None)
            # Verify the necessary Prefix exists, create if necessary
            prefix = get_or_create_prefix(adapter, address)
            if not prefix:  # A valid prefix must exist to continue
                return (None, None)
            if adapter.job.debug:
                adapter.job.logger.debug(
                    f"Updating IP Address {addr} mask length from {addr.mask_length} to {mask_length}"
                )
            addr.mask_length = mask_length
            addr.parent = prefix
            addr.validated_save()
        return (addr, "ip_address")
    # Create an IP Address if one does not exist
    except ObjectDoesNotExist:
        prefix = get_or_create_prefix(adapter, address)
        if not prefix:  # A valid prefix must exist to continue
            return (None, None)
        try:
            if adapter.job.debug:
                adapter.job.logger.debug(f"Creating IPAddress {address}")
            addr = IPAddress(address=address, status=status, type=IPAddressTypeChoices.TYPE_HOST)
            addr.validated_save()
            return (addr, "ip_address")
        except Exception as err:  # pylint: disable=broad-exception-caught
            adapter.job.logger.error(f"Unable to create IPAddress: {address}, {err}")
            return (None, None)
    except Exception as err:  # pylint: disable=broad-exception-caught
        adapter.job.logger.error(f"Error getting or creating IPAddress for address {address}, {err}")
        return (None, None)


def get_or_create_vrf(adapter, vrf_name):
    """Attempt to get or create a Nautobot VRF object."""
    try:
        vrf = VRF.objects.get(name=vrf_name)
    except ObjectDoesNotExist:
        if adapter and adapter.job.debug:
            adapter.job.logger.debug(f"Creating VRF {vrf_name}")
        vrf = VRF(name=vrf_name)
        vrf.validated_save()
    return vrf
