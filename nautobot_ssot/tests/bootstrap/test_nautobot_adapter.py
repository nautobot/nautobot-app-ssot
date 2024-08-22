"""Testing that objects are properly loaded from Nautobot into Nautobot adapter."""

# test_nautobot_adapter.py

from django.test import TransactionTestCase
from .test_setup import NautobotTestSetup, GLOBAL_JSON_SETTINGS


def remove_object_keys(data):
    """Remove DiffSync model_flags and system_of_record from objects."""
    if isinstance(data, list):
        return [remove_object_keys(item) for item in data]
    if isinstance(data, dict):
        return {
            key: remove_object_keys(value)
            for key, value in data.items()
            if key not in ["model_flags", "system_of_record", "terminations", "uuid"]
        }
    return data


class TestNautobotAdapterTestCase(TransactionTestCase):
    """Test NautobotAdapter class."""

    databases = ("default", "job_logs")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_diff = None

    def setUp(self):
        """Initialize test case."""
        super().setUp()
        self.setup = NautobotTestSetup()
        self.nb_adapter = self.setup.nb_adapter

    def test_data_loading(self):
        """Test Bootstrap Nautobot load() function."""
        self.nb_adapter.load()
        self.max_diff = None

        self.assertEqual(sorted(self.nb_adapter.dict()["tenant_group"]), sorted(GLOBAL_JSON_SETTINGS["tenant_group"]))
        self.assertEqual(
            sorted(self.nb_adapter.dict()["tenant"], key=lambda x: x[1]),
            sorted(GLOBAL_JSON_SETTINGS["tenant"], key=lambda x: x[1]),
        )
        filtered_adapter_roles = remove_object_keys(self.nb_adapter.dict()["role"])
        self.assertEqual(
            sorted(filtered_adapter_roles.values(), key=lambda x: x["name"]),
            sorted(GLOBAL_JSON_SETTINGS["role"].values(), key=lambda x: x["name"]),
        )
        self.assertEqual(
            sorted(self.nb_adapter.dict()["manufacturer"], key=lambda x: x[1]),
            sorted(GLOBAL_JSON_SETTINGS["manufacturer"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.nb_adapter.dict()["platform"], key=lambda x: x[1]),
            sorted(GLOBAL_JSON_SETTINGS["platform"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.nb_adapter.dict()["location_type"], key=lambda x: x[1]),
            sorted(GLOBAL_JSON_SETTINGS["location_type"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.nb_adapter.dict()["location"], key=lambda x: x[1]),
            sorted(GLOBAL_JSON_SETTINGS["location"], key=lambda x: x[1]),
        )
        filtered_adapter_teams = remove_object_keys(self.nb_adapter.dict()["team"])
        self.assertEqual(
            sorted(filtered_adapter_teams.values(), key=lambda x: x["name"]),
            sorted(GLOBAL_JSON_SETTINGS["team"].values(), key=lambda x: x["name"]),
        )
        filtered_adapter_contacts = remove_object_keys(self.nb_adapter.dict()["contact"])
        self.assertEqual(
            sorted(filtered_adapter_contacts.values(), key=lambda x: x["name"]),
            sorted(GLOBAL_JSON_SETTINGS["contact"].values(), key=lambda x: x["name"]),
        )
        filtered_adapter_providers = remove_object_keys(self.nb_adapter.dict()["provider"])
        self.assertEqual(
            sorted(filtered_adapter_providers.values(), key=lambda x: x["name"]),
            sorted(GLOBAL_JSON_SETTINGS["provider"].values(), key=lambda x: x["name"]),
        )
        filtered_adapter_provider_networks = remove_object_keys(self.nb_adapter.dict()["provider_network"])
        self.assertEqual(
            sorted(filtered_adapter_provider_networks.values(), key=lambda x: x["name"]),
            sorted(GLOBAL_JSON_SETTINGS["provider_network"].values(), key=lambda x: x["name"]),
        )
        filtered_adapter_circuit_types = remove_object_keys(self.nb_adapter.dict()["circuit_type"])
        self.assertEqual(
            sorted(filtered_adapter_circuit_types.values(), key=lambda x: x["name"]),
            sorted(GLOBAL_JSON_SETTINGS["circuit_type"].values(), key=lambda x: x["name"]),
        )
        filtered_adapter_circuits = remove_object_keys(self.nb_adapter.dict()["circuit"])
        self.assertEqual(
            sorted(filtered_adapter_circuits.values(), key=lambda x: x["circuit_id"]),
            sorted(GLOBAL_JSON_SETTINGS["circuit"].values(), key=lambda x: x["circuit_id"]),
        )
        filtered_adapter_circuit_terminations = remove_object_keys(self.nb_adapter.dict()["circuit_termination"])
        self.assertEqual(
            sorted(filtered_adapter_circuit_terminations.values(), key=lambda x: x["name"]),
            sorted(GLOBAL_JSON_SETTINGS["circuit_termination"].values(), key=lambda x: x["name"]),
        )
        self.assertEqual(
            sorted(self.nb_adapter.dict()["secret"], key=lambda x: x[1]),
            sorted(GLOBAL_JSON_SETTINGS["secret"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.nb_adapter.dict()["secrets_group"], key=lambda x: x[1]),
            sorted(GLOBAL_JSON_SETTINGS["secrets_group"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.nb_adapter.dict()["computed_field"], key=lambda x: x[1]),
            sorted(GLOBAL_JSON_SETTINGS["computed_field"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.nb_adapter.dict()["graph_ql_query"], key=lambda x: x[1]),
            sorted(GLOBAL_JSON_SETTINGS["graph_ql_query"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.nb_adapter.dict()["git_repository"], key=lambda x: x[1]),
            sorted(GLOBAL_JSON_SETTINGS["git_repository"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.nb_adapter.dict()["dynamic_group"], key=lambda x: x[1]),
            sorted(GLOBAL_JSON_SETTINGS["dynamic_group"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.nb_adapter.dict()["tag"], key=lambda x: x[1]),
            sorted(GLOBAL_JSON_SETTINGS["tag"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.nb_adapter.dict()["software"], key=lambda x: x[1]),
            sorted(GLOBAL_JSON_SETTINGS["software"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.nb_adapter.dict()["software_image"], key=lambda x: x[1]),
            sorted(GLOBAL_JSON_SETTINGS["software_image"], key=lambda x: x[1]),
        )
        self.assertEqual(
            set(GLOBAL_JSON_SETTINGS["validated_software"]),
            {_val_soft.get_unique_id() for _val_soft in self.nb_adapter.get_all("validated_software")},
        )
        self.assertEqual(
            set(GLOBAL_JSON_SETTINGS["namespace"]),
            {_val_soft.get_unique_id() for _val_soft in self.nb_adapter.get_all("namespace")},
        )
        self.assertEqual(
            set(GLOBAL_JSON_SETTINGS["rir"]),
            {_val_soft.get_unique_id() for _val_soft in self.nb_adapter.get_all("rir")},
        )
        self.assertEqual(
            set(GLOBAL_JSON_SETTINGS["vlan_group"]),
            {_val_soft.get_unique_id() for _val_soft in self.nb_adapter.get_all("vlan_group")},
        )
        self.assertEqual(
            set(GLOBAL_JSON_SETTINGS["vlan"]),
            {_val_soft.get_unique_id() for _val_soft in self.nb_adapter.get_all("vlan")},
        )
        self.assertEqual(
            set(GLOBAL_JSON_SETTINGS["vrf"]),
            {_val_soft.get_unique_id() for _val_soft in self.nb_adapter.get_all("vrf")},
        )
        self.assertEqual(
            set(GLOBAL_JSON_SETTINGS["prefix"]),
            {_val_soft.get_unique_id() for _val_soft in self.nb_adapter.get_all("prefix")},
        )
