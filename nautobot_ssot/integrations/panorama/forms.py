"""Plugin forms."""

from django import forms
from nautobot.apps.forms import BootstrapMixin, DynamicModelChoiceField, DynamicModelMultipleChoiceField
from nautobot.dcim.models import Controller, Device, Interface
from nautobot.extras.forms import NautobotModelForm

from nautobot_ssot.integrations.panorama.models import LogicalGroup, VirtualSystem


class VirtualSystemFilterForm(BootstrapMixin, forms.Form):
    """Filtering/search form for `VirtualSystem` objects."""

    model = VirtualSystem
    q = forms.CharField(required=False, label="Search")
    name = forms.CharField(max_length=20, required=False)
    system_id = forms.IntegerField(required=False)
    device = DynamicModelChoiceField(queryset=Device.objects.all(), label="Parent Device", required=False)


class VirtualSystemForm(NautobotModelForm):  # pylint: disable=too-many-ancestors
    """Generic create/update form for `VirtualSystem` objects."""

    device = DynamicModelChoiceField(queryset=Device.objects.all(), label="Parent Device", required=True)
    interfaces = DynamicModelMultipleChoiceField(
        queryset=Interface.objects.all(),
        label="Assigned Interfaces",
        required=True,
        query_params={"device_id": "$device"},
    )

    class Meta:
        """Meta class."""

        model = VirtualSystem
        fields = ["name", "system_id", "device", "interfaces"]  # pylint: disable=nb-use-fields-all


class LogicalGroupFilterForm(BootstrapMixin, forms.Form):
    """Filtering/search form for `LogicalGroup` objects."""

    model = LogicalGroup
    q = forms.CharField(required=False, label="Search")
    name = forms.CharField(max_length=20, required=False)


class LogicalGroupForm(NautobotModelForm):  # pylint: disable=too-many-ancestors
    """Generic create/update form for `LogicalGroup` objects."""

    devices = DynamicModelMultipleChoiceField(queryset=Device.objects.all(), label="Assigned Devices", required=False)
    virtual_systems = DynamicModelMultipleChoiceField(
        queryset=VirtualSystem.objects.all(), label="Assigned Virtual Systems", required=False
    )
    control_plane = DynamicModelChoiceField(queryset=Controller.objects.all(), required=False)

    class Meta:
        """Meta class."""

        model = LogicalGroup
        fields = ["name", "parent", "devices", "virtual_systems", "control_plane"]  # pylint: disable=nb-use-fields-all
