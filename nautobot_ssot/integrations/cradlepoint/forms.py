"""Forms implementation for SSOT Cradlepoint."""
from nautobot.extras.forms import NautobotFilterForm, NautobotModelForm

from .models import SSOTCradlepointConfig


class SSOTCradlepointConfigForm(
    NautobotModelForm
):  # pylint: disable=too-many-ancestors
    """SSOTvSphereConfig creation/edit form."""

    class Meta:
        """Meta attributes for the SSOTvSpereConfigForm class."""

        model = SSOTCradlepointConfig
        fields = "__all__"


class SSOTCradlepointConfigFilterForm(
    NautobotFilterForm
):  # pylint: disable=too-many-ancestors
    """Filter form for SSOTInfobloxConfig filter searches."""

    model = SSOTCradlepointConfig

    class Meta:
        """Meta attributes for the SSOTvSphereConfigFilterForm class."""

        model = SSOTCradlepointConfig
        fields = "__all__"
