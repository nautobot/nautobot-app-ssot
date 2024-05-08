"""Infoblox Fixtures."""

# Ignoring docstrings on fixtures  pylint: disable=missing-function-docstring
# Ignoring using fixtures in other fixtures  pylint: disable=redefined-outer-name
import json
import os

from django.contrib.contenttypes.models import ContentType
from nautobot.extras.choices import RelationshipTypeChoices
from nautobot.extras.models import Relationship
from nautobot.ipam.models import Prefix, VLAN

from nautobot_ssot.integrations.infoblox.utils import client

FIXTURES = os.environ.get("FIXTURE_DIR", "nautobot_ssot/tests/infoblox/fixtures")

LOCALHOST = os.environ.get("TEST_LOCALHOST_URL", "https://localhost:4440/wapi/v2.12")


def _json_read_fixture(name):
    """Return JSON fixture."""
    with open(f"{FIXTURES}/{name}", encoding="utf8") as fixture:
        return json.load(fixture)


def localhost_client_infoblox(localhost_url):
    """Return InfobloxAPI client for testing."""
    return client.InfobloxApi(  # nosec
        url=localhost_url, username="test-user", password="test-password", verify_ssl=False, cookie=None
    )


def create_prefix_relationship():
    """Create Relationship for Prefix -> VLAN."""
    relationship_dict = {  # pylint: disable=duplicate-code
        "label": "Prefix -> VLAN",
        "key": "prefix_to_vlan",
        "type": RelationshipTypeChoices.TYPE_ONE_TO_MANY,
        "source_type": ContentType.objects.get_for_model(Prefix),
        "source_label": "Prefix",
        "destination_type": ContentType.objects.get_for_model(VLAN),
        "destination_label": "VLAN",
    }
    return Relationship.objects.get_or_create(label=relationship_dict["label"], defaults=relationship_dict)[0]


def get_all_ipv4address_networks():
    """Return all IPv4Address networks."""
    return _json_read_fixture("get_all_ipv4address_networks.json")


def get_all_ipv4address_networks_medium():
    """Return all IPv4Address networks from medium size network."""
    return _json_read_fixture("get_all_ipv4address_networks_medium.json")


def get_all_ipv4address_networks_large():
    """Return all IPv4Address networks from large size network."""
    return _json_read_fixture("get_all_ipv4address_networks_large.json")


def get_all_ipv4address_networks_bulk():
    """Return all IPv4Address networks from multiple medium networks that result in over 1k addresses."""
    return _json_read_fixture("get_all_ipv4address_networks_bulk.json")


def create_ptr_record():
    """Return a PTR record."""
    return _json_read_fixture("create_ptr_record.json")


def create_a_record():
    """Return A record creation."""
    return _json_read_fixture("create_a_record.json")


def create_host_record():
    """Return a Host record creation."""
    return _json_read_fixture("create_host_record.json")


def get_host_by_ip():
    """Return a get Host by IP response."""
    return _json_read_fixture("get_host_by_ip.json")


def get_a_record_by_ip():
    """Return a get A record by IP response."""
    return _json_read_fixture("get_a_record_by_ip.json")


def get_a_record_by_name():
    """Return a get A record by name response."""
    return _json_read_fixture("get_a_record_by_name.json")


def get_host_record_by_name():
    """Return a get Host record by name response."""
    return _json_read_fixture("get_host_record_by_name.json")


def get_all_dns_views():
    """Return a get all DNS views response."""
    return _json_read_fixture("get_all_dns_views.json")


def get_dhcp_lease_from_ipv4():
    """Return a get DHCP lease from IPv4 response."""
    return _json_read_fixture("get_dhcp_lease_from_ipv4.json")


def get_dhcp_lease_from_hostname():
    """Return a get DHCP lease from IPv4 response."""
    return _json_read_fixture("get_dhcp_lease_from_hostname.json")


def get_all_subnets():
    """Return a get all subnets response."""
    return _json_read_fixture("get_all_subnets.json")


def get_authoritative_zone():
    """Return a get authoritative zone response."""
    return _json_read_fixture("get_authoritative_zone.json")


def find_network_reference():
    """Return a find network reference response."""
    return _json_read_fixture("find_network_reference.json")


def get_ptr_record_by_name():
    """Return a get PTR record by name response."""
    return _json_read_fixture("get_ptr_record_by_name.json")


def find_next_available_ip():
    """Return a next available IP response."""
    return _json_read_fixture("find_next_available_ip.json")


def search_ipv4_address():
    """Return a search IPv4 address response."""
    return _json_read_fixture("search_ipv4_address.json")


def get_network_containers():
    """Return a get_all_containers response."""
    return _json_read_fixture("get_network_containers.json")


def get_network_containers_ipv6():
    """Return a get_all_containers IPv6 response."""
    return _json_read_fixture("get_network_containers_ipv6.json")


def get_all_ranges():
    """Return a get all ranges response."""
    return _json_read_fixture("get_all_ranges.json")
