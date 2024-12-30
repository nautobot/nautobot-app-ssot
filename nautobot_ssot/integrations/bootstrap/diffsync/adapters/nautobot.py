"""Nautobot Adapter for bootstrap SSoT plugin."""

from diffsync import Adapter
from diffsync.enum import DiffSyncModelFlags
from diffsync.exceptions import ObjectAlreadyExists, ObjectNotFound
from django.conf import settings
from nautobot.circuits.models import (
    Circuit,
    CircuitTermination,
    CircuitType,
    Provider,
    ProviderNetwork,
)
from nautobot.dcim.models import (
    Location,
    LocationType,
    Manufacturer,
    Platform,
)
from nautobot.extras.models import (
    ComputedField,
    Contact,
    DynamicGroup,
    GitRepository,
    GraphQLQuery,
    Role,
    Secret,
    SecretsGroup,
    Status,
    Tag,
    Team,
)
from nautobot.ipam.models import (
    RIR,
    VLAN,
    VRF,
    Namespace,
    Prefix,
    VLANGroup,
)
from nautobot.tenancy.models import Tenant, TenantGroup

from nautobot_ssot.integrations.bootstrap.diffsync.models.nautobot import (
    NautobotCircuit,
    NautobotCircuitTermination,
    NautobotCircuitType,
    NautobotComputedField,
    NautobotContact,
    NautobotDynamicGroup,
    NautobotGitRepository,
    NautobotGraphQLQuery,
    NautobotLocation,
    NautobotLocationType,
    NautobotManufacturer,
    NautobotNamespace,
    NautobotPlatform,
    NautobotPrefix,
    NautobotProvider,
    NautobotProviderNetwork,
    NautobotRiR,
    NautobotRole,
    NautobotSecret,
    NautobotSecretsGroup,
    NautobotTag,
    NautobotTeam,
    NautobotTenant,
    NautobotTenantGroup,
    NautobotVLAN,
    NautobotVLANGroup,
    NautobotVRF,
)
from nautobot_ssot.integrations.bootstrap.utils import (
    check_sor_field,
    get_sor_field_nautobot_object,
    lookup_content_type_model_path,
    lookup_model_for_role_id,
    lookup_model_for_taggable_class_id,
)
from nautobot_ssot.integrations.bootstrap.utils.nautobot import (
    get_prefix_location_assignments,
    get_vrf_prefix_assignments,
)

try:
    # noqa: F401
    from nautobot_device_lifecycle_mgmt.models import (
        SoftwareLCM as ORMSoftware,
    )

    from nautobot_ssot.integrations.bootstrap.diffsync.models.nautobot import NautobotSoftware

    SOFTWARE_LIFECYCLE_MGMT = True
except (ImportError, RuntimeError):
    SOFTWARE_LIFECYCLE_MGMT = False

try:
    # noqa: F401
    from nautobot_device_lifecycle_mgmt.models import (
        SoftwareImageLCM as ORMSoftwareImage,
    )

    from nautobot_ssot.integrations.bootstrap.diffsync.models.nautobot import NautobotSoftwareImage

    SOFTWARE_IMAGE_LIFECYCLE_MGMT = True
except (ImportError, RuntimeError):
    SOFTWARE_IMAGE_LIFECYCLE_MGMT = False

try:
    # noqa: F401
    from nautobot_device_lifecycle_mgmt.models import (
        ValidatedSoftwareLCM as ORMValidatedSoftware,
    )

    from nautobot_ssot.integrations.bootstrap.diffsync.models.nautobot import NautobotValidatedSoftware

    VALID_SOFTWARE_LIFECYCLE_MGMT = True
except (ImportError, RuntimeError):
    VALID_SOFTWARE_LIFECYCLE_MGMT = False


class NautobotAdapter(Adapter):
    """DiffSync adapter for Nautobot."""

    tenant_group = NautobotTenantGroup
    tenant = NautobotTenant
    role = NautobotRole
    manufacturer = NautobotManufacturer
    platform = NautobotPlatform
    location_type = NautobotLocationType
    location = NautobotLocation
    team = NautobotTeam
    contact = NautobotContact
    provider = NautobotProvider
    provider_network = NautobotProviderNetwork
    circuit_type = NautobotCircuitType
    circuit = NautobotCircuit
    circuit_termination = NautobotCircuitTermination
    namespace = NautobotNamespace
    rir = NautobotRiR
    vlan_group = NautobotVLANGroup
    vlan = NautobotVLAN
    vrf = NautobotVRF
    prefix = NautobotPrefix
    secret = NautobotSecret
    secrets_group = NautobotSecretsGroup
    git_repository = NautobotGitRepository
    dynamic_group = NautobotDynamicGroup
    computed_field = NautobotComputedField
    tag = NautobotTag
    graph_ql_query = NautobotGraphQLQuery

    if SOFTWARE_LIFECYCLE_MGMT:
        software = NautobotSoftware
    if SOFTWARE_IMAGE_LIFECYCLE_MGMT:
        software_image = NautobotSoftwareImage
    if VALID_SOFTWARE_LIFECYCLE_MGMT:
        validated_software = NautobotValidatedSoftware

    top_level = [
        "tag",
        "tenant_group",
        "tenant",
        "role",
        "manufacturer",
        "platform",
        "location_type",
        "location",
        "team",
        "contact",
        "provider",
        "provider_network",
        "circuit_type",
        "circuit",
        "namespace",
        "rir",
        "vlan_group",
        "vlan",
        "vrf",
        "prefix",
        "secret",
        "secrets_group",
        "git_repository",
        "dynamic_group",
        "computed_field",
        "graph_ql_query",
    ]

    if SOFTWARE_LIFECYCLE_MGMT:
        top_level.append("software")
    if SOFTWARE_IMAGE_LIFECYCLE_MGMT:
        top_level.append("software_image")
    if VALID_SOFTWARE_LIFECYCLE_MGMT:
        top_level.append("validated_software")

    def __init__(self, *args, job=None, sync=None, **kwargs):  # noqa: D417
        """Initialize Nautobot.

        Args:
            job (object, optional): Nautobot job. Defaults to None.
            sync (object, optional): Nautobot DiffSync. Defaults to None.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync

    def load_tenant_group(self):
        """Method to load TenantGroup objects from Nautobot into NautobotTenantGroup DiffSync models."""
        for nb_tenant_group in TenantGroup.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot TenantGroup: {nb_tenant_group}, with ID: {nb_tenant_group.id}")
            try:
                self.get(self.tenant_group, nb_tenant_group.name)
            except ObjectNotFound:
                try:
                    _parent = nb_tenant_group.parent.name
                except AttributeError:
                    _parent = ""
                _sor = ""
                if "system_of_record" in nb_tenant_group.custom_field_data:
                    _sor = (
                        nb_tenant_group.custom_field_data["system_of_record"]
                        if nb_tenant_group.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_tenant_group = self.tenant_group(
                    name=nb_tenant_group.name,
                    parent=_parent,
                    description=nb_tenant_group.description,
                    system_of_record=_sor,
                    uuid=nb_tenant_group.id,
                )
                self.job.logger.info(f"Loading Nautobot Tenant Group - {nb_tenant_group.name}")

                if not check_sor_field(nb_tenant_group):
                    new_tenant_group.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_tenant_group)

    def load_tenant(self):
        """Method to load Tenant objects from Nautobot into NautobotTenant DiffSync models."""
        for nb_tenant in Tenant.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot Tenant: {nb_tenant}, with ID: {nb_tenant.id}")
            _tags = sorted(list(nb_tenant.tags.all().values_list("name", flat=True)))
            try:
                self.get(self.tenant, nb_tenant.name)
            except ObjectNotFound:
                try:
                    _tenant_group = nb_tenant.tenant_group.name
                except AttributeError:
                    _tenant_group = None
                _sor = ""
                if "system_of_record" in nb_tenant.custom_field_data:
                    _sor = (
                        nb_tenant.custom_field_data["system_of_record"]
                        if nb_tenant.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_tenant = self.tenant(
                    name=nb_tenant.name,
                    tenant_group=_tenant_group,
                    description=nb_tenant.description,
                    tags=_tags,
                    system_of_record=_sor,
                    uuid=nb_tenant.id,
                )
                self.job.logger.info(f"Loading Nautobot Tenant - {nb_tenant.name}")

                if not check_sor_field(nb_tenant):
                    new_tenant.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_tenant)

    def load_role(self):
        """Method to load Role objects from Nautobot into NautobotRole DiffSync models."""
        for nb_role in Role.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot Role: {nb_role}, with ID {nb_role.id}")
            try:
                self.get(self.role, nb_role.name)
            except ObjectNotFound:
                _content_types = []
                _content_uuids = nb_role.content_types.values_list("model", "id")
                for _uuid in _content_uuids:
                    _content_types.append(lookup_model_for_role_id(_uuid[1]))
                    _content_types.sort()
                _sor = ""
                if "system_of_record" in nb_role.custom_field_data:
                    _sor = (
                        nb_role.custom_field_data["system_of_record"]
                        if nb_role.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_role = self.role(
                    name=nb_role.name,
                    weight=nb_role.weight,
                    description=nb_role.description,
                    color=nb_role.color,
                    content_types=_content_types,
                    system_of_record=_sor,
                )

                if not check_sor_field(nb_role):
                    new_role.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_role)
                _content_types.clear()

    def load_manufacturer(self):
        """Method to load Manufacturer objects from Nautobot into NautobotManufacturer DiffSync models."""
        for nb_manufacturer in Manufacturer.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot Manufacturer: {nb_manufacturer}, with ID {nb_manufacturer.id}")
            try:
                self.get(self.manufacturer, nb_manufacturer.name)
            except ObjectNotFound:
                _sor = ""
                if "system_of_record" in nb_manufacturer.custom_field_data:
                    _sor = (
                        nb_manufacturer.custom_field_data["system_of_record"]
                        if nb_manufacturer.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_manufacturer = self.manufacturer(
                    name=nb_manufacturer.name,
                    description=nb_manufacturer.description,
                    uuid=nb_manufacturer.id,
                    system_of_record=_sor,
                )

                if not check_sor_field(nb_manufacturer):
                    new_manufacturer.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_manufacturer)

    def load_platform(self):
        """Method to load Platform objects from Nautobot into NautobotPlatform DiffSync models."""
        for nb_platform in Platform.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot Platform: {nb_platform}, with ID {nb_platform.id}")
            try:
                self.get(self.platform, nb_platform.name)
            except ObjectNotFound:
                if isinstance(nb_platform.napalm_args, str):
                    _napalm_args = {}
                else:
                    _napalm_args = nb_platform.napalm_args

                _manufacturer = ""
                if nb_platform.manufacturer is not None:
                    _manufacturer = nb_platform.manufacturer.name

                _sor = ""
                if "system_of_record" in nb_platform.custom_field_data:
                    _sor = (
                        nb_platform.custom_field_data["system_of_record"]
                        if nb_platform.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_platform = self.platform(
                    name=nb_platform.name,
                    manufacturer=_manufacturer,
                    network_driver=nb_platform.network_driver,
                    napalm_driver=nb_platform.napalm_driver,
                    napalm_arguments=_napalm_args,
                    description=nb_platform.description,
                    system_of_record=_sor,
                    uuid=nb_platform.id,
                )

                if not check_sor_field(nb_platform):
                    new_platform.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_platform)

    def load_location_type(self):
        """Method to load LocationType objects from Nautobot into NautobotLocationType DiffSync models."""
        for nb_location_type in LocationType.objects.all():
            if self.job.debug:
                self.job.logger.debug(
                    f"Loading Nautobot LocationType: {nb_location_type}, with ID {nb_location_type.id}"
                )
            try:
                self.get(self.location_type, nb_location_type.name)
            except ObjectNotFound:
                _content_types = []
                _content_uuids = nb_location_type.content_types.values_list("id", flat=True)
                if nb_location_type.parent is not None:
                    _parent = nb_location_type.parent.name
                else:
                    _parent = None
                for _uuid in _content_uuids:
                    _content_types.append(lookup_content_type_model_path(nb_model="locations", content_id=_uuid))
                if len(_content_types) > 1:
                    try:
                        _content_types.sort()
                    except TypeError:
                        self.job.logger.warning(
                            f"One of your content types is not able to be associated with LocationType {nb_location_type}. Please check and try again. {_content_types}"
                        )
                _sor = ""
                if "system_of_record" in nb_location_type.custom_field_data:
                    _sor = (
                        nb_location_type.custom_field_data["system_of_record"]
                        if nb_location_type.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_location_type = self.location_type(
                    name=nb_location_type.name,
                    parent=_parent,
                    nestable=nb_location_type.nestable if not None else False,
                    description=nb_location_type.description,
                    content_types=_content_types,
                    system_of_record=_sor,
                    uuid=nb_location_type.id,
                )

                if not check_sor_field(nb_location_type):
                    new_location_type.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_location_type)
                _content_types.clear()

    def load_location(self):
        """Method to load Location objects from Nautobot into NautobotLocation DiffSync models."""
        for nb_location in Location.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot Location: {nb_location}, with ID {nb_location.id}")
            try:
                self.get(self.location, nb_location.name)
            except ObjectNotFound:
                _tags = []
                if nb_location.parent is not None:
                    _parent = nb_location.parent.name
                else:
                    _parent = None
                if nb_location.time_zone is not None:
                    try:
                        _time_zone = nb_location.time_zone.zone
                    except AttributeError:
                        _time_zone = nb_location.time_zone
                else:
                    _time_zone = ""
                if nb_location.tenant is not None:
                    _tenant = nb_location.tenant.name
                else:
                    _tenant = None
                if nb_location.tags is not None:
                    for _tag in nb_location.tags.values_list("name", flat=True):
                        _tags.append(_tag)
                _sor = ""
                if "system_of_record" in nb_location.custom_field_data:
                    _sor = (
                        nb_location.custom_field_data["system_of_record"]
                        if nb_location.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_location = self.location(
                    name=nb_location.name,
                    location_type=nb_location.location_type.name,
                    parent=_parent,
                    status=nb_location.status.name,
                    facility=nb_location.facility,
                    asn=nb_location.asn,
                    time_zone=str(_time_zone),
                    description=nb_location.description,
                    tenant=_tenant,
                    physical_address=nb_location.physical_address,
                    shipping_address=nb_location.shipping_address,
                    latitude=nb_location.latitude,
                    longitude=nb_location.longitude,
                    contact_name=nb_location.contact_name,
                    contact_phone=nb_location.contact_phone,
                    contact_email=nb_location.contact_email,
                    tags=_tags,
                    system_of_record=_sor,
                    uuid=nb_location.id,
                )

                if not check_sor_field(nb_location):
                    new_location.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_location)

    def load_team(self):
        """Method to load Team objects from Nautobot into NautobotTeam DiffSync models."""
        for nb_team in Team.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot Team: {nb_team}, with ID: {nb_team.id}")
            try:
                self.get(self.team, nb_team.name)
            except ObjectNotFound:
                if nb_team.contacts is not None:
                    _contacts = []
                    for _contact in nb_team.contacts.values_list("name", flat=True):
                        _contacts.append(_contact)
                        _contacts.sort()
                _sor = ""
                if "system_of_record" in nb_team.custom_field_data:
                    _sor = (
                        nb_team.custom_field_data["system_of_record"]
                        if nb_team.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_team = self.team(
                    name=nb_team.name,
                    phone=nb_team.phone,
                    email=nb_team.email,
                    address=nb_team.address,
                    # TODO: Need to consider how to allow loading from teams or contacts models.
                    # contacts=_contacts,
                    system_of_record=_sor,
                    uuid=nb_team.id,
                )

                if not check_sor_field(nb_team):
                    new_team.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_team)

    def load_contact(self):
        """Method to load Contact Objects from Nautobot into NautobotContact DiffSync models."""
        for nb_contact in Contact.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot contact: {nb_contact}, with ID: {nb_contact.id}")
            try:
                self.get(self.contact, nb_contact.name)
            except ObjectNotFound:
                if nb_contact.teams is not None:
                    _teams = []
                    for _team in nb_contact.teams.values_list("name", flat=True):
                        _teams.append(_team)
                        _teams.sort()
                _sor = ""
                if "system_of_record" in nb_contact.custom_field_data:
                    _sor = (
                        nb_contact.custom_field_data["system_of_record"]
                        if nb_contact.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_contact = self.contact(
                    name=nb_contact.name,
                    phone=nb_contact.phone,
                    email=nb_contact.email,
                    address=nb_contact.address,
                    teams=_teams,
                    system_of_record=_sor,
                    uuid=nb_contact.id,
                )

                if not check_sor_field(nb_contact):
                    new_contact.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_contact)

    def load_provider(self):
        """Method to load Provider objects from Nautobot into NautobotProvider DiffSync models."""
        for nb_provider in Provider.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot Provider: {nb_provider}, with ID {nb_provider.id}")
            try:
                self.get(self.provider, nb_provider.name)
            except ObjectNotFound:
                if nb_provider.tags is not None:
                    _tags = []
                    for _tag in nb_provider.tags.values_list("name", flat=True):
                        _tags.append(_tag)
                        _tags.sort()
                else:
                    _tags = None
                _sor = ""
                if "system_of_record" in nb_provider.custom_field_data:
                    _sor = (
                        nb_provider.custom_field_data["system_of_record"]
                        if nb_provider.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_provider = self.provider(
                    name=nb_provider.name,
                    asn=nb_provider.asn,
                    account_number=nb_provider.account,
                    portal_url=nb_provider.portal_url,
                    noc_contact=nb_provider.noc_contact,
                    admin_contact=nb_provider.admin_contact,
                    tags=_tags,
                    system_of_record=_sor,
                    uuid=nb_provider.id,
                )

                if not check_sor_field(nb_provider):
                    new_provider.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_provider)

    def load_provider_network(self):
        """Method to load ProviderNetwork objects from Nautobot into NautobotProviderNetwork DiffSync models."""
        for nb_provider_network in ProviderNetwork.objects.all():
            if self.job.debug:
                self.job.logger.debug(
                    f"Loading Nautobot ProviderNetwork: {nb_provider_network}, with ID {nb_provider_network.id}"
                )
            try:
                self.get(self.provider_network, nb_provider_network.name)
            except ObjectNotFound:
                if nb_provider_network.tags is not None:
                    _tags = []
                    for _tag in nb_provider_network.tags.values_list("name", flat=True):
                        _tags.append(_tag)
                        _tags.sort()
                else:
                    _tags = None
                _sor = ""
                if "system_of_record" in nb_provider_network.custom_field_data:
                    _sor = (
                        nb_provider_network.custom_field_data["system_of_record"]
                        if nb_provider_network.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_provider_network = self.provider_network(
                    name=nb_provider_network.name,
                    provider=nb_provider_network.provider.name,
                    description=nb_provider_network.description,
                    comments=nb_provider_network.comments,
                    tags=_tags,
                    system_of_record=_sor,
                    uuid=nb_provider_network.id,
                )

                if not check_sor_field(nb_provider_network):
                    new_provider_network.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_provider_network)

    def load_circuit_type(self):
        """Method to load CircuitType objects from Nautobot into NautobotCircuitType DiffSync models."""
        for nb_circuit_type in CircuitType.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot CircuitType: {nb_circuit_type}, with ID {nb_circuit_type.id}")
            try:
                self.get(self.circuit_type, nb_circuit_type.name)
            except ObjectNotFound:
                _sor = ""
                if "system_of_record" in nb_circuit_type.custom_field_data:
                    _sor = (
                        nb_circuit_type.custom_field_data["system_of_record"]
                        if nb_circuit_type.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_circuit_type = self.circuit_type(
                    name=nb_circuit_type.name,
                    description=nb_circuit_type.description,
                    system_of_record=_sor,
                    uuid=nb_circuit_type.id,
                )

                if not check_sor_field(nb_circuit_type):
                    new_circuit_type.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_circuit_type)

    def load_circuit(self):
        """Method to load Circuit objects from Nautobot into NautobotCircuit DiffSync models."""
        for nb_circuit in Circuit.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot Circuit: {nb_circuit}, with ID {nb_circuit.id}")
            try:
                self.get(self.circuit, nb_circuit.cid)
            except ObjectNotFound:
                if nb_circuit.tags is not None:
                    _tags = []
                    for _tag in nb_circuit.tags.values_list("name", flat=True):
                        _tags.append(_tag)
                        _tags.sort()
                else:
                    _tags = None
                _sor = ""
                if "system_of_record" in nb_circuit.custom_field_data:
                    _sor = (
                        nb_circuit.custom_field_data["system_of_record"]
                        if nb_circuit.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_circuit = self.circuit(
                    circuit_id=nb_circuit.cid,
                    provider=nb_circuit.provider.name,
                    circuit_type=nb_circuit.circuit_type.name,
                    status=nb_circuit.status.name,
                    date_installed=nb_circuit.install_date,
                    commit_rate_kbps=nb_circuit.commit_rate,
                    description=nb_circuit.description,
                    tenant=(nb_circuit.tenant.name if nb_circuit.tenant is not None else None),
                    tags=_tags,
                    system_of_record=_sor,
                    uuid=nb_circuit.id,
                )

                if not check_sor_field(nb_circuit):
                    new_circuit.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_circuit)

    def load_circuit_termination(self):
        """Method to load CircuitTermination objects from Nautobot into NautobotCircuitTermination DiffSync models."""
        for nb_circuit_termination in CircuitTermination.objects.all():
            if self.job.debug:
                self.job.logger.debug(
                    f"Loading Nautobot CircuitTermination {nb_circuit_termination}, with ID: {nb_circuit_termination.id}"
                )
            _term_name = f"{nb_circuit_termination.circuit.cid}__{nb_circuit_termination.circuit.provider.name}__{nb_circuit_termination.term_side}"
            try:
                self.get(self.circuit_termination, _term_name)
            except ObjectNotFound:
                if nb_circuit_termination.tags is not None:
                    _tags = []
                    for _tag in nb_circuit_termination.tags.values_list("name", flat=True):
                        _tags.append(_tag)
                        _tags.sort()
                else:
                    _tags = None
                _sor = ""
                if "system_of_record" in nb_circuit_termination.custom_field_data:
                    _sor = (
                        nb_circuit_termination.custom_field_data["system_of_record"]
                        if nb_circuit_termination.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                if nb_circuit_termination.provider_network:
                    _termination_type = "Provider Network"
                if nb_circuit_termination.location:
                    _termination_type = "Location"
                new_circuit_termination = self.circuit_termination(
                    name=_term_name,
                    termination_type=_termination_type,
                    termination_side=nb_circuit_termination.term_side,
                    circuit_id=nb_circuit_termination.circuit.cid,
                    provider_network=(
                        nb_circuit_termination.provider_network.name
                        if nb_circuit_termination.provider_network is not None
                        else None
                    ),
                    location=(
                        nb_circuit_termination.location.name if nb_circuit_termination.location is not None else None
                    ),
                    port_speed_kbps=nb_circuit_termination.port_speed,
                    upstream_speed_kbps=nb_circuit_termination.upstream_speed,
                    cross_connect_id=nb_circuit_termination.xconnect_id,
                    patch_panel_or_ports=nb_circuit_termination.pp_info,
                    description=nb_circuit_termination.description,
                    tags=_tags,
                    system_of_record=_sor,
                    uuid=nb_circuit_termination.id,
                )

                if not check_sor_field(nb_circuit_termination):
                    new_circuit_termination.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_circuit_termination)
                try:
                    _circuit = self.get(
                        self.circuit,
                        {
                            "circuit_id": nb_circuit_termination.circuit.cid,
                            "provider": nb_circuit_termination.circuit.provider.name,
                        },
                    )
                    _circuit.add_child(new_circuit_termination)
                except ObjectAlreadyExists as err:
                    self.job.logger.warning(f"CircuitTermination for {_circuit} already exists. {err}")

    def load_namespace(self):
        """Method to load Namespace objects from Nautobot into NautobotNamespace DiffSync models."""
        for nb_namespace in Namespace.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot Namespace {nb_namespace}, with ID: {nb_namespace.id}")
            try:
                self.get(self.namespace, nb_namespace.name)
            except ObjectNotFound:
                _sor = get_sor_field_nautobot_object(nb_namespace)
                try:
                    _location = Location.objects.get(id=nb_namespace.location_id).name
                except Location.DoesNotExist:
                    _location = ""
                new_namespace = self.namespace(
                    name=nb_namespace.name,
                    description=nb_namespace.description,
                    location=_location,
                    system_of_record=_sor,
                    uuid=nb_namespace.id,
                )
                if not check_sor_field(nb_namespace):
                    new_namespace.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
                self.add(new_namespace)

    def load_rir(self):
        """Method to load RiR objects from Nautobot into NautobotRiR DiffSync models."""
        for nb_rir in RIR.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot RiR {nb_rir}, with ID {nb_rir.id}")
            try:
                self.get(self.rir, nb_rir.name)
            except ObjectNotFound:
                _sor = get_sor_field_nautobot_object(nb_rir)
                new_rir = self.rir(
                    name=nb_rir.name,
                    private=nb_rir.is_private,
                    description=nb_rir.description,
                    system_of_record=_sor,
                    uuid=nb_rir.id,
                )
                if not check_sor_field(nb_rir):
                    new_rir.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
                self.add(new_rir)

    def load_vlan_group(self):
        """Method to load VLANGroup objects from Nautobot into NautobotVLANGroup DiffSync models."""
        for nb_vlan_group in VLANGroup.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot VLANGroup {nb_vlan_group}, with ID {nb_vlan_group.id}")
            try:
                self.get(self.vlan_group, nb_vlan_group.name)
            except ObjectNotFound:
                _sor = get_sor_field_nautobot_object(nb_vlan_group)
                if nb_vlan_group.location:
                    _location = nb_vlan_group.location.name
                else:
                    _location = ""
                new_vlan_group = self.vlan_group(
                    name=nb_vlan_group.name,
                    description=nb_vlan_group.description,
                    location=_location,
                    system_of_record=_sor,
                    uuid=nb_vlan_group.id,
                )
                if not check_sor_field(nb_vlan_group):
                    new_vlan_group.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
                self.add(new_vlan_group)

    def load_vlan(self):
        """Method to load VLAN objects from Nautobot into NautobotVLAN DiffSync models."""
        for nb_vlan in VLAN.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot VLAN {nb_vlan}, with ID {nb_vlan.id}")
            try:
                self.get(
                    self.vlan,
                    {
                        "name": nb_vlan.name,
                        "vid": nb_vlan.vid,
                        "vlan_group": (nb_vlan.vlan_group.name if nb_vlan.vlan_group else ""),
                    },
                )
            except ObjectNotFound:
                _locations = []
                _tags = []
                _sor = get_sor_field_nautobot_object(nb_vlan)
                if nb_vlan.locations:
                    for _location in nb_vlan.locations.values_list("name", flat=True):
                        _locations.append(_location)
                if nb_vlan.tags:
                    for _tag in nb_vlan.tags.values_list("name", flat=True):
                        _tags.append(_tag)
                new_vlan = self.vlan(
                    name=nb_vlan.name,
                    vid=nb_vlan.vid,
                    vlan_group=nb_vlan.vlan_group.name if nb_vlan.vlan_group else None,
                    role=nb_vlan.role.name if nb_vlan.role else None,
                    description=nb_vlan.description,
                    status=nb_vlan.status.name,
                    locations=_locations,
                    tenant=nb_vlan.tenant.name if nb_vlan.tenant else None,
                    tags=_tags,
                    system_of_record=_sor,
                    uuid=nb_vlan.id,
                )
                if not check_sor_field(nb_vlan):
                    new_vlan.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
                self.add(new_vlan)

    def load_vrf(self):
        """Method to load VRF objects from Nautobot into NautobotVRF DiffSync models."""
        for nb_vrf in VRF.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot VRF {nb_vrf}, with ID {nb_vrf.id}")
            try:
                self.get(
                    self.vrf,
                    {"name": nb_vrf.name, "namespace": {nb_vrf.namespace.name}},
                )
            except ObjectNotFound:
                _tags = []
                _sor = get_sor_field_nautobot_object(nb_vrf)
                if nb_vrf.tags:
                    for _tag in nb_vrf.tags.values_list("name", flat=True):
                        _tags.append(_tag)
                new_vrf = self.vrf(
                    name=nb_vrf.name,
                    namespace=Namespace.objects.get(id=nb_vrf.namespace_id).name,
                    route_distinguisher=nb_vrf.rd,
                    description=nb_vrf.description,
                    tenant=(Tenant.objects.get(id=nb_vrf.tenant_id).name if nb_vrf.tenant_id else None),
                    tags=_tags,
                    system_of_record=_sor,
                    uuid=nb_vrf.id,
                )
                if not check_sor_field(nb_vrf):
                    new_vrf.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
                self.add(new_vrf)

    def load_prefix(self):
        """Method to load Prefix objects from Nautobot into NautobotPrefix DiffSync models."""
        for nb_prefix in Prefix.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot Prefix {nb_prefix}, with ID {nb_prefix.id}")
            try:
                self.get(
                    self.prefix,
                    {
                        "network": nb_prefix.network,
                        "namespace": nb_prefix.namespace.name,
                    },
                )
            except ObjectNotFound:
                _tags = []
                _vlan = None
                _sor = get_sor_field_nautobot_object(nb_prefix)
                if nb_prefix.tags:
                    for _tag in nb_prefix.tags.values_list("name", flat=True):
                        _tags.append(_tag)
                if nb_prefix.vlan:
                    if nb_prefix.vlan.vlan_group:
                        _group = nb_prefix.vlan.vlan_group.name
                    else:
                        _group = "None"
                    _vlan = f"{nb_prefix.vlan.name}__{nb_prefix.vlan.vid}__{_group}"
                _vrfs = get_vrf_prefix_assignments(prefix=nb_prefix)
                _locations = get_prefix_location_assignments(prefix=nb_prefix)
                new_prefix = self.prefix(
                    network=f"{nb_prefix.network}/{nb_prefix.prefix_length}",
                    namespace=Namespace.objects.get(id=nb_prefix.namespace_id).name,
                    prefix_type=nb_prefix.type,
                    status=Status.objects.get(id=nb_prefix.status_id).name,
                    role=nb_prefix.role.name if nb_prefix.role else None,
                    rir=(RIR.objects.get(id=nb_prefix.rir_id).name if nb_prefix.rir_id else None),
                    date_allocated=(
                        nb_prefix.date_allocated.replace(tzinfo=None) if nb_prefix.date_allocated else None
                    ),
                    description=nb_prefix.description,
                    vrfs=_vrfs,
                    locations=_locations,
                    vlan=_vlan,
                    tenant=(Tenant.objects.get(id=nb_prefix.tenant_id).name if nb_prefix.tenant_id else None),
                    tags=_tags,
                    system_of_record=_sor,
                    uuid=nb_prefix.id,
                )
                if not check_sor_field(nb_prefix):
                    new_prefix.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
                self.add(new_prefix)

    def load_secret(self):
        """Method to load Secrets objects from Nautobot into NautobotSecrets DiffSync models."""
        for nb_secret in Secret.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot Secret: {nb_secret}, with ID: {nb_secret.id}")
            try:
                self.get(self.secret, nb_secret.name)
            except ObjectNotFound:
                _sor = ""
                if "system_of_record" in nb_secret.custom_field_data:
                    _sor = (
                        nb_secret.custom_field_data["system_of_record"]
                        if nb_secret.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_secret = self.secret(
                    name=nb_secret.name,
                    provider=nb_secret.provider,
                    parameters=nb_secret.parameters,
                    system_of_record=_sor,
                    uuid=nb_secret.id,
                )
                self.job.logger.info(f"Loading Nautobot secret - {nb_secret.name}")

                if not check_sor_field(nb_secret):
                    new_secret.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_secret)

    def load_secrets_group(self):
        """Method to load SecretsGroup objects from Nautobot into NautobotSecretsGroup DiffSync models."""
        _secrets = []
        for nb_sg in SecretsGroup.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot SecretsGroup: {nb_sg}")
            for nb_secret in nb_sg.secrets_group_associations.all():
                _secrets.append(
                    {
                        "name": nb_secret.secret.name,
                        "secret_type": nb_secret.secret_type,
                        "access_type": nb_secret.access_type,
                    }
                )
            _secrets = sorted(_secrets, key=lambda x: x["name"])
            try:
                self.get(self.secrets_group, nb_sg.name)
            except ObjectNotFound:
                _sor = ""
                if "system_of_record" in nb_sg.custom_field_data:
                    _sor = (
                        nb_sg.custom_field_data["system_of_record"]
                        if nb_sg.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_sg = self.secrets_group(
                    name=nb_sg.name,
                    secrets=_secrets,
                    system_of_record=_sor,
                    uuid=nb_sg.id,
                )
                self.job.logger.info(f"Loading Nautobot secret - {nb_sg.name}")

                if not check_sor_field(nb_sg):
                    new_sg.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_sg)
            _secrets.clear()

    def load_git_repository(self):
        """Method to load GitRepository objects from Nautobot into NautobotGitRepository DiffSync models."""
        for nb_gr in GitRepository.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot GitRepository: {nb_gr}")
            try:
                self.get(self.git_repository, nb_gr.name)
            except ObjectNotFound:
                try:
                    _secrets_group = nb_gr.secrets_group.name
                except AttributeError:
                    _secrets_group = None
                _sor = ""
                if "system_of_record" in nb_gr.custom_field_data:
                    _sor = (
                        nb_gr.custom_field_data["system_of_record"]
                        if nb_gr.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_gr = self.git_repository(
                    name=nb_gr.name,
                    url=nb_gr.remote_url,
                    branch=nb_gr.branch,
                    secrets_group=_secrets_group,
                    provided_contents=nb_gr.provided_contents,
                    system_of_record=_sor,
                    uuid=nb_gr.id,
                )

                if not check_sor_field(nb_gr):
                    new_gr.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_gr)

    def load_dynamic_group(self):
        """Method to load DynamicGroup objects from Nautobot into NautobotDynamicGroup DiffSync models."""
        for nb_dyn_group in DynamicGroup.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot DynamicGroup {nb_dyn_group}")
            try:
                self.get(self.dynamic_group, nb_dyn_group.name)
            except ObjectNotFound:
                _content_type = lookup_content_type_model_path(
                    nb_model="dynamic_groups", content_id=nb_dyn_group.content_type.id
                )
                if _content_type is None:
                    self.job.logger.warning(
                        f"Could not find ContentType for {nb_dyn_group.name} with ContentType ID {nb_dyn_group.content_type.id}"
                    )
                _sor = ""
                if "system_of_record" in nb_dyn_group.custom_field_data:
                    _sor = (
                        nb_dyn_group.custom_field_data["system_of_record"]
                        if nb_dyn_group.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_dyn_group = self.dynamic_group(
                    name=nb_dyn_group.name,
                    content_type=_content_type,
                    dynamic_filter=nb_dyn_group.filter,
                    description=nb_dyn_group.description,
                    system_of_record=_sor,
                    uuid=nb_dyn_group.id,
                )

                if not check_sor_field(nb_dyn_group):
                    new_dyn_group.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_dyn_group)

    def load_computed_field(self):
        """Method to load ComputedField objects from Nautobot into NautobotComputedField DiffSync models."""
        for nb_comp_field in ComputedField.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot ComputedField {nb_comp_field}")
            try:
                self.get(self.computed_field, nb_comp_field.label)
            except ObjectNotFound:
                _content_type = lookup_content_type_model_path(
                    nb_model="custom_fields", content_id=nb_comp_field.content_type.id
                )
                if _content_type is None:
                    self.job.logger.warning(
                        f"Could not find ContentType for {nb_comp_field.label} with ContentType {nb_comp_field.content_type}, and ContentType ID {nb_comp_field.content_type.id}"
                    )
                new_computed_field = self.computed_field(
                    label=nb_comp_field.label,
                    content_type=_content_type,
                    template=nb_comp_field.template,
                )
                new_computed_field.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
                self.add(new_computed_field)

    def load_tag(self):
        """Method to load Tag objects from Nautobot into NautobotTag DiffSync Models."""
        for nb_tag in Tag.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot Tag {nb_tag}")
            try:
                self.get(self.tag, nb_tag.name)
            except ObjectNotFound:
                _content_types = []
                _content_uuids = nb_tag.content_types.values_list("model", "id")
                for _uuid in _content_uuids:
                    _content_types.append(lookup_model_for_taggable_class_id(_uuid[1]))
                    _content_types.sort()
                _sor = ""
                if "system_of_record" in nb_tag.custom_field_data:
                    _sor = (
                        nb_tag.custom_field_data["system_of_record"]
                        if nb_tag.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_tag = self.tag(
                    name=nb_tag.name,
                    color=nb_tag.color,
                    content_types=_content_types,
                    description=nb_tag.description,
                    system_of_record=_sor,
                    uuid=nb_tag.id,
                )

                if not check_sor_field(nb_tag):
                    new_tag.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_tag)
                _content_types.clear()

    def load_graph_ql_query(self):
        """Method to load GraphQLQuery objects from Nautobot into NautobotGraphQLQuery Models."""
        for query in GraphQLQuery.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot GraphQLQuery {query}")
            try:
                self.get(self.graph_ql_query, query.name)
            except ObjectNotFound:
                new_query = self.graph_ql_query(name=query.name, query=query.query)
            new_query.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
            self.add(new_query)

    def load_software(self):
        """Method to load Software objects from Nautobot into NautobotSoftware Models."""
        for nb_software in ORMSoftware.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot SoftwareLCM {nb_software}")
            try:
                self.get(
                    self.software,
                    {
                        "version": nb_software.version,
                        "platform": nb_software.device_platform.name,
                    },
                )
            except ObjectNotFound:
                _tags = list(
                    ORMSoftware.objects.get(
                        version=nb_software.version,
                        device_platform=nb_software.device_platform.id,
                    )
                    .tags.all()
                    .values_list("name", flat=True)
                )
                _sor = ""
                if "system_of_record" in nb_software.custom_field_data:
                    _sor = (
                        nb_software.custom_field_data["system_of_record"]
                        if nb_software.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_software = self.software(
                    version=nb_software.version,
                    platform=nb_software.device_platform.name,
                    alias=nb_software.alias,
                    release_date=nb_software.release_date,
                    eos_date=nb_software.end_of_support,
                    documentation_url=nb_software.documentation_url,
                    long_term_support=nb_software.long_term_support,
                    pre_release=nb_software.pre_release,
                    tags=_tags,
                    system_of_record=_sor,
                    uuid=nb_software.id,
                )

                if not check_sor_field(nb_software):
                    new_software.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_software)

    def load_software_image(self):
        """Method to load SoftwareImage objects from Nautobot into NautobotSoftwareImage Models."""
        for nb_software_image in ORMSoftwareImage.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot SoftwareImageLCM {nb_software_image}")
            try:
                self.get(self.software_image, nb_software_image.image_file_name)
            except ObjectNotFound:
                _tags = list(
                    ORMSoftwareImage.objects.get(image_file_name=nb_software_image.image_file_name)
                    .tags.all()
                    .values_list("name", flat=True)
                )
                _sor = ""
                if "system_of_record" in nb_software_image.custom_field_data:
                    _sor = (
                        nb_software_image.custom_field_data["system_of_record"]
                        if nb_software_image.custom_field_data["system_of_record"] is not None
                        else ""
                    )
                new_software_image = self.software_image(
                    file_name=nb_software_image.image_file_name,
                    software=f"{nb_software_image.software.device_platform} - {nb_software_image.software.version}",
                    platform=nb_software_image.software.device_platform.name,
                    software_version=nb_software_image.software.version,
                    download_url=nb_software_image.download_url,
                    image_file_checksum=nb_software_image.image_file_checksum,
                    hashing_algorithm=nb_software_image.hashing_algorithm,
                    default_image=nb_software_image.default_image,
                    tags=_tags,
                    system_of_record=_sor,
                    uuid=nb_software_image.id,
                )

                if not check_sor_field(nb_software_image):
                    new_software_image.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_software_image)

    def load_validated_software(self):
        """Method to load ValidatedSoftware objects from Nautobot into NautobotValidatedSoftware Models."""
        for nb_validated_software in ORMValidatedSoftware.objects.all():
            if self.job.debug:
                self.job.logger.debug(f"Loading Nautobot ValidatedSoftwareLCM {nb_validated_software}")

            _tags = sorted(list(nb_validated_software.tags.all().values_list("name", flat=True)))
            _devices = sorted(list(nb_validated_software.devices.all().values_list("name", flat=True)))
            _device_types = sorted(list(nb_validated_software.device_types.all().values_list("model", flat=True)))
            _device_roles = sorted(list(nb_validated_software.device_roles.all().values_list("name", flat=True)))
            _inventory_items = sorted(list(nb_validated_software.inventory_items.all().values_list("name", flat=True)))
            _object_tags = sorted(list(nb_validated_software.object_tags.all().values_list("name", flat=True)))
            _sor = ""
            if "system_of_record" in nb_validated_software.custom_field_data:
                _sor = (
                    nb_validated_software.custom_field_data["system_of_record"]
                    if nb_validated_software.custom_field_data["system_of_record"] is not None
                    else ""
                )
            if hasattr(nb_validated_software.software, "device_platform"):
                platform = nb_validated_software.software.device_platform.name
            else:
                platform = nb_validated_software.software.platform.name
            new_validated_software, _ = self.get_or_instantiate(
                self.validated_software,
                ids={
                    "software": str(nb_validated_software.software),
                    "valid_since": nb_validated_software.start,
                    "valid_until": nb_validated_software.end,
                },
                attrs={
                    "software_version": nb_validated_software.software.version,
                    "platform": platform,
                    "preferred_version": nb_validated_software.preferred,
                    "devices": _devices,
                    "device_types": _device_types,
                    "device_roles": _device_roles,
                    "inventory_items": _inventory_items,
                    "object_tags": _object_tags,
                    "tags": _tags,
                    "system_of_record": _sor,
                    "uuid": nb_validated_software.id,
                },
            )

            if not check_sor_field(nb_validated_software):
                new_validated_software.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    def load(self):
        """Load data from Nautobot into DiffSync models."""
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["tenant_group"]:
            self.load_tenant_group()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["tenant"]:
            self.load_tenant()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["role"]:
            self.load_role()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["manufacturer"]:
            self.load_manufacturer()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["platform"]:
            self.load_platform()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["location_type"]:
            self.load_location_type()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["location"]:
            self.load_location()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["team"]:
            self.load_team()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["contact"]:
            self.load_contact()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["provider"]:
            self.load_provider()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["provider_network"]:
            self.load_provider_network()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["circuit_type"]:
            self.load_circuit_type()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["circuit"]:
            self.load_circuit()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["circuit_termination"]:
            self.load_circuit_termination()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["namespace"]:
            self.load_namespace()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["rir"]:
            self.load_rir()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["vlan_group"]:
            self.load_vlan_group()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["vlan"]:
            self.load_vlan()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["vrf"]:
            self.load_vrf()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["prefix"]:
            self.load_prefix()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["secret"]:
            self.load_secret()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["secrets_group"]:
            self.load_secrets_group()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["git_repository"]:
            self.load_git_repository()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["dynamic_group"]:
            self.load_dynamic_group()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["computed_field"]:
            self.load_computed_field()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["tag"]:
            self.load_tag()
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["graph_ql_query"]:
            self.load_graph_ql_query()
        if SOFTWARE_LIFECYCLE_MGMT:
            if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["software"]:
                self.load_software()
        if SOFTWARE_IMAGE_LIFECYCLE_MGMT:
            if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["software_image"]:
                self.load_software_image()
        if VALID_SOFTWARE_LIFECYCLE_MGMT:
            if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["validated_software"]:
                self.load_validated_software()
