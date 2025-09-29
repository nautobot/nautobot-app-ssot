"""Tests for contrib.NautobotModel."""

from nautobot.core.testing import TestCase

from nautobot_ssot.contrib.model import NautobotModel


class TestMethodGetSyncedParameters(TestCase):
    """Tests for manipulating custom relationships through the shared base model code."""

    def test_single_identifer(self):
        """Test a single identifier."""

        class LocalModel(NautobotModel):
            _identifiers = ("name",)
            _attributes = ()

            name: str

        result = LocalModel.get_synced_attributes()
        self.assertEqual(len(result), 1)
        self.assertIn("name", result)

    def test_multiple_identifiers(self):
        """Test multiple identifiers, including a related field."""

        class LocalModel(NautobotModel):
            _identifiers = (
                "name",
                "parent__name",
            )
            _attributes = ()

            name: str
            parent__name: str

        result = LocalModel.get_synced_attributes()
        self.assertEqual(len(result), 2)
        self.assertIn("name", result)
        self.assertIn("parent__name", result)

    def test_only_attributes(self):
        """Test only attributes."""

        class LocalModel(NautobotModel):
            _identifiers = ()
            _attributes = ("description", "status")

            description: str
            status: str

        result = LocalModel.get_synced_attributes()
        self.assertEqual(len(result), 2)
        self.assertIn("description", result)
        self.assertIn("status", result)

    def test_identifiers_and_attributes(self):
        """Test both identifiers and attributes."""

        class LocalModel(NautobotModel):
            _identifiers = ("name",)
            _attributes = ("description", "status")

            name: str
            description: str
            status: str

        result = LocalModel.get_synced_attributes()
        self.assertEqual(len(result), 3)
        self.assertIn("name", result)
        self.assertIn("description", result)
        self.assertIn("status", result)

    def test_empty_identifiers_and_attributes(self):
        """Test empty identifiers and attributes."""

        class LocalModel(NautobotModel):
            _identifiers = ()
            _attributes = ()

        result = LocalModel.get_synced_attributes()
        self.assertEqual(len(result), 0)
        self.assertEqual(LocalModel.get_synced_attributes(), [])
