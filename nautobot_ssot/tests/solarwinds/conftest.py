"""Params for testing."""

import json

from nautobot_ssot.integrations.solarwinds.utils.solarwinds import SolarWindsClient


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


GET_TOP_LEVEL_CONTAINERS_FIXTURE = load_json("./nautobot_ssot/tests/solarwinds/fixtures/get_top_level_containers.json")
NODE_DETAILS_FIXTURE = load_json("./nautobot_ssot/tests/solarwinds/fixtures/node_details.json")
GET_CONTAINER_NODES_FIXTURE = load_json("./nautobot_ssot/tests/solarwinds/fixtures/get_container_nodes.json")
GET_CONTAINER_NODES_CUSTOM_PROPERTY_FIXTURE = load_json(
    "./nautobot_ssot/tests/solarwinds/fixtures/get_container_nodes_custom_property.json"
)


def create_solarwinds_client(**kwargs) -> SolarWindsClient:
    """Function to initialize a SolarWindsClient object."""
    return SolarWindsClient(  # nosec: B106
        hostname=kwargs.pop("hostname", "https://test.solarwinds.com"),
        username=kwargs.pop("username", "admin"),
        password=kwargs.pop("password", "admin"),
        port=kwargs.pop("port", 443),
        retries=kwargs.pop("retries", 5),
        timeout=kwargs.pop("timeout", 60),
        verify=kwargs.pop("verify", True),
        job=kwargs.pop("job", None),
    )


def get_container_nodes(container_ids=None, custom_property=None, location_name=None):  # pylint: disable=W0613
    """Function to return nodes based on inputs."""
    if custom_property:
        return GET_CONTAINER_NODES_CUSTOM_PROPERTY_FIXTURE
    return GET_CONTAINER_NODES_FIXTURE
