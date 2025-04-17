"""Test Cradlepoint Jobs."""

from unittest import TestCase

from nautobot_ssot.integrations.cradlepoint.utilities.helpers import (
    get_id_from_url,
)



class TestGetIdFromurl(TestCase):
    """Test the Cradlepoint Sync job."""

    def test_valid_url(self):
        """Test get ID function using valid URL."""
        test = get_id_from_url("https://www.cradlepointcm.com/api/v2/products/32/")
        self.assertTrue(test == 32)

    def test_invalid_url(self):
        """Test get ID function using invalid URL."""
        test = get_id_from_url("https://www.cradlepointcm.com/api/v2/products/")
        self.assertTrue(test == None)
