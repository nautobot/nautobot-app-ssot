"""Tests for contrib.NautobotModel."""

from unittest.mock import patch

from nautobot.core.testing import TestCase
from nautobot.ipam import models as ipam_models

from nautobot_ssot.contrib import NautobotModel


class QuerySetPrefetchRelatedTest(TestCase):
    """Test that _get_queryset adds expected prefetch_related params to the queryset."""

    @patch("django.db.models.query.QuerySet.prefetch_related")
    def test__get_queryset(self, prefetch_related_mock):
        """Test that _get_queryset adds expected prefetch_related params to the queryset."""

        class BaseIPAddressModel(NautobotModel):
            """Test contrib model."""

            _model = ipam_models.IPAddress
            _modelname = "ipaddress"
            _identifiers = ("host", "mask_length", "parent__namespace__name")
            _attributes = ("status__name", "tenant__name")

            host: str
            mask_length: int
            parent__namespace__name: str
            status__name: str
            tenant__name: str

        BaseIPAddressModel._get_queryset()  # pylint: disable=protected-access
        prefetch_related_mock.assert_called_with("parent__namespace", "status", "tenant")
