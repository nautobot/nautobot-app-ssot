"""Nautobot Ssot Bootstrap DiffSync models for Nautobot Ssot Bootstrap SSoT."""

from nautobot_ssot.integrations.bootstrap.diffsync.models.base import (
    VLAN,
    VRF,
    Circuit,
    CircuitTermination,
    CircuitType,
    ComputedField,
    Contact,
    CustomField,
    DynamicGroup,
    ExternalIntegration,
    GitRepository,
    GraphQLQuery,
    Location,
    LocationType,
    Manufacturer,
    Namespace,
    Platform,
    Prefix,
    Provider,
    ProviderNetwork,
    RiR,
    Role,
    ScheduledJob,
    Secret,
    SecretsGroup,
    Tag,
    Team,
    Tenant,
    TenantGroup,
    VLANGroup,
)
from nautobot_ssot.utils import core_supports_softwareversion, dlm_supports_softwarelcm, validate_dlm_installed

if core_supports_softwareversion():
    from nautobot_ssot.integrations.bootstrap.diffsync.models.base import SoftwareImageFile, SoftwareVersion

    _Software_Base_Class = SoftwareVersion
    _SoftwareImage_Base_Class = SoftwareImageFile

    if validate_dlm_installed():
        import nautobot_device_lifecycle_mgmt  # noqa: F401

        from nautobot_ssot.integrations.bootstrap.diffsync.models.base import ValidatedSoftware

elif dlm_supports_softwarelcm():
    from nautobot_ssot.integrations.bootstrap.diffsync.models.base import Software, SoftwareImage, ValidatedSoftware

    _Software_Base_Class = Software
    _SoftwareImage_Base_Class = SoftwareImage


class BootstrapTenantGroup(TenantGroup):
    """Bootstrap implementation of TenantGroup DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create TenantGroup in Bootstrap from BootstrapTenantGroup object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update TenantGroup in Bootstrap from BootstrapTenantGroup object."""
        return super().update(attrs)

    def delete(self):
        """Delete TenantGroup in Bootstrap from BootstrapTenantGroup object."""
        return self


class BootstrapTenant(Tenant):
    """Bootstrap implementation of TenantGroup DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Tenant in Bootstrap from BootstrapTenant object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Tenant in Bootstrap from BootstrapTenant object."""
        return super().update(attrs)

    def delete(self):
        """Delete Tenant in Bootstrap from BootstrapTenant object."""
        return self


class BootstrapRole(Role):
    """Bootstrap implementation of Role DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Role in Bootstrap from BootstrapRole object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Role in Bootstrap from BootstrapRole object."""
        return super().update(attrs)

    def delete(self):
        """Delete Role in Bootstrap from BootstrapRole object."""
        return self


class BootstrapManufacturer(Manufacturer):
    """Bootstrap implementation of Manufacturer DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Manufacturer in Bootstrap from BootstrapManufacturer object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Manufacturer in Bootstrap from BootstrapManufacturer object."""
        return super().update(attrs)

    def delete(self):
        """Delete Manufacturer in Bootstrap from BootstrapManufacturer object."""
        return self


class BootstrapPlatform(Platform):
    """Bootstrap implementation of Platform DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Platform in Bootstrap from BootstrapPlatform object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Platform in Bootstrap from BootstrapPlatform object."""
        return super().update(attrs)

    def delete(self):
        """Delete Platform in Bootstrap from BootstrapPlatform object."""
        return self


class BootstrapLocationType(LocationType):
    """Bootstrap implementation of LocationType DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create LocationType in Bootstrap from BootstrapLocationType object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update LocationType in Bootstrap from BootstrapLocationType object."""
        return super().update(attrs)

    def delete(self):
        """Delete LocationType in Bootstrap from BootstrapLocationType object."""
        return self


class BootstrapLocation(Location):
    """Bootstrap implementation of Location DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Location in Bootstrap from BootstrapLocation object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Location in Bootstrap from BootstrapLocation object."""
        return super().update(attrs)

    def delete(self):
        """Delete Location in Bootstrap from BootstrapLocation object."""
        return self


class BootstrapTeam(Team):
    """Bootstrap implementation of Team DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Team in Bootstrap from BootstrapTeam object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Team in Bootstrap from BootstrapTeam object."""
        return super().update(attrs)

    def delete(self):
        """Delete Team in Bootstrap from BootstrapTeam object."""
        return self


class BootstrapContact(Contact):
    """Bootstrap implementation of Contact DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Contact in Bootstrap from BootstrapContact object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Contact in Bootstrap from BootstrapContact object."""
        return super().update(attrs)

    def delete(self):
        """Delete Contact in Bootstrap from BootstrapContact object."""
        return self


class BootstrapProvider(Provider):
    """Bootstrap implementation of Provider DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Provider in Bootstrap from BootstrapProvider object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Provider in Bootstrap from BootstrapProvider object."""
        return super().update(attrs)

    def delete(self):
        """Delete Provider in Bootstrap from BootstrapProvider object."""
        return self


class BootstrapProviderNetwork(ProviderNetwork):
    """Bootstrap implementation of ProviderNetwork DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create ProviderNetwork in Bootstrap from BootstrapProviderNetwork object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update ProviderNetwork in Bootstrap from BootstrapProviderNetwork object."""
        return super().update(attrs)

    def delete(self):
        """Delete ProviderNetwork in Bootstrap from BootstrapProviderNetwork object."""
        return self


class BootstrapCircuitType(CircuitType):
    """Bootstrap implementation of CircuitType DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create CircuitType in Bootstrap from BootstrapCircuitType object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update CircuitType in Bootstrap from BootstrapCircuitType object."""
        return super().update(attrs)

    def delete(self):
        """Delete CircuitType in Bootstrap from BootstrapCircuitType object."""
        return self


class BootstrapCircuit(Circuit):
    """Bootstrap implementation of Circuit DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Circuit in Bootstrap from BootstrapCircuit object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Circuit in Bootstrap from BootstrapCircuit object."""
        return super().update(attrs)

    def delete(self):
        """Delete Circuit in Bootstrap from BootstrapCircuit object."""
        return self


class BootstrapCircuitTermination(CircuitTermination):
    """Bootstrap implementation of CircuitTermination DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create CircuitTermination in Bootstrap from BootstrapCircuitTermination object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update CircuitTermination in Bootstrap from BootstrapCircuitTermination object."""
        return super().update(attrs)

    def delete(self):
        """Delete CircuitTermination in Bootstrap from BootstrapCircuitTermination object."""
        return self


class BootstrapSecret(Secret):
    """Bootstrap implementation of Secret DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Secret in Bootstrap from BootstrapSecret object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Secret in Bootstrap from BootstrapSecret object."""
        return super().update(attrs)

    def delete(self):
        """Delete Secret in Bootstrap from BootstrapSecret object."""
        return self


class BootstrapSecretsGroup(SecretsGroup):
    """Bootstrap implementation of Secret DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Secret in Bootstrap from BootstrapDevice object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Secret in Bootstrap from BootstrapSecret object."""
        return super().update(attrs)

    def delete(self):
        """Delete Secret in Bootstrap from BootstrapSecret object."""
        return self


class BootstrapGitRepository(GitRepository):
    """Bootstrap implementation of GitRepository DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create GitRepository in Bootstrap from BootstrapGitRepository object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update GitRepository in Bootstrap from BootstrapGitRepository object."""
        return super().update(attrs)

    def delete(self):
        """Delete GitRepository in Bootstrap from BootstrapGitRepository object."""
        return self


class BootstrapDynamicGroup(DynamicGroup):
    """Bootstrap implementation of DynamicGroup DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create DynamicGroup in Bootstrap from BootstrapDynamicGroup object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update DynamicGroup in Bootstrap from BootstrapDynamicGroup object."""
        return super().update(attrs)

    def delete(self):
        """Delete DynamicGroup in Bootstrap from BootstrapDynamicGroup object."""
        return self


class BootstrapComputedField(ComputedField):
    """Bootstrap implementation of ComputedField DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create ComputedField in Bootstrap from BootstrapComputedField object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update ComputedField in Bootstrap from BootstrapComputedField object."""
        return super().update(attrs)

    def delete(self):
        """Delete ComputedField in Bootstrap from BootstrapComputedField object."""
        return self


class BootstrapCustomField(CustomField):
    """Bootstrap implementation of CustomField DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create CustomField in Bootstrap from BootstrapCustomField object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update CustomField in Bootstrap from BootstrapCustomField object."""
        return super().update(attrs)

    def delete(self):
        """Delete CustomField in Bootstrap from BootstrapCustomField object."""
        return self


class BootstrapTag(Tag):
    """Bootstrap implementation of Bootstrap Tag model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Tag in Bootstrap from BootstrapTag object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Tag in Bootstrap from BootstrapTag object."""
        return super().update(attrs)

    def delete(self):
        """Delete Tag in Bootstrap from BootstrapTag object."""
        return self


class BootstrapGraphQLQuery(GraphQLQuery):
    """Bootstrap implementation of Bootstrap GraphQLQuery model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create GraphQLQuery in Bootstrap from BootstrapTag object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update GraphQLQuery in Bootstrap from BootstrapGraphQLQuery object."""
        return super().update(attrs)

    def delete(self):
        """Delete GraphQLQuery in Bootstrap from BootstrapTag object."""
        return self


class BootstrapNamespace(Namespace):
    """Bootstrap implementation of Bootstrap Namespace model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Namespace in Bootstrap from BootstrapNamespace object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Namespace in Bootstrap from BootstrapNamespace object."""
        return super().update(attrs)

    def delete(self):
        """Delete Namespace in Bootstrap from BootstrapNamespace object."""
        return self


class BootstrapRiR(RiR):
    """Bootstrap implementation of Bootstrap RiR model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create RiR in Bootstrap from BootstrapRiR object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update RiR in Bootstrap from BootstrapRiR object."""
        return super().update(attrs)

    def delete(self):
        """Delete RiR in Bootstrap from BootstrapRiR object."""
        return self


class BootstrapVLANGroup(VLANGroup):
    """Bootstrap implementation of Bootstrap VLANGroup model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create VLANGroup in Bootstrap from BootstrapVLANGroup object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update VLANGroup in Bootstrap from BootstrapVLANGroup object."""
        return super().update(attrs)

    def delete(self):
        """Delete VLANGroup in Bootstrap from BootstrapVLANGroup object."""
        return self


class BootstrapVLAN(VLAN):
    """Bootstrap implementation of Bootstrap VLAN model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create VLAN in Bootstrap from BootstrapVLAN object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update VLAN in Bootstrap from BootstrapVLAN object."""
        return super().update(attrs)

    def delete(self):
        """Delete VLAN in Bootstrap from BootstrapVLAN object."""
        return self


class BootstrapVRF(VRF):
    """Bootstrap implementation of Bootstrap VRF model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create VRF in Bootstrap from BootstrapVRF object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update VRF in Bootstrap from BootstrapVRF object."""
        return super().update(attrs)

    def delete(self):
        """Delete VRF in Bootstrap from BootstrapVRF object."""
        return self


class BootstrapPrefix(Prefix):
    """Bootstrap implementation of Bootstrap Prefix model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Prefix in Bootstrap from BootstrapPrefix object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Prefix in Bootstrap from BootstrapPrefix object."""
        return super().update(attrs)

    def delete(self):
        """Delete Prefix in Bootstrap from BootstrapPrefix object."""
        return self


class BootstrapScheduledJob(ScheduledJob):
    """Bootstrap implementation of Bootstrap ScheduledJob model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create ScheduledJob in Bootstrap from BootstrapValidatedSoftware object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update ScheduledJob in Bootstrap from BootstrapValidatedSoftware object."""
        return super().update(attrs)

    def delete(self):
        """Delete ScheduledJob in Bootstrap from BootstrapValidatedSoftware object."""
        return self


if core_supports_softwareversion() and not validate_dlm_installed():

    class BootstrapSoftwareVersion(SoftwareVersion):
        """Bootstrap implementation of Bootstrap Software model."""

        @classmethod
        def create(cls, diffsync, ids, attrs):
            """Create Software in Bootstrap from BootstrapSoftware object."""
            return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

        def update(self, attrs):
            """Update Software in Bootstrap from BootstrapSoftware object."""
            return super().update(attrs)

        def delete(self):
            """Delete Software in Bootstrap from BootstrapSoftware object."""
            return self

    class BootstrapSoftwareImageFile(SoftwareImageFile):
        """Bootstrap implementation of Bootstrap SoftwareImage model."""

        @classmethod
        def create(cls, diffsync, ids, attrs):
            """Create SoftwareImage in Bootstrap from BootstrapSoftwareImage object."""
            return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

        def update(self, attrs):
            """Update SoftwareImage in Bootstrap from BootstrapSoftwareImage object."""
            return super().update(attrs)

        def delete(self):
            """Delete SoftwareImage in Bootstrap from BootstrapSoftwareImage object."""
            return self


class BootstrapSoftware(_Software_Base_Class):
    """Bootstrap implementation of Bootstrap Software model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Software in Bootstrap from BootstrapSoftware object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Software in Bootstrap from BootstrapSoftware object."""
        return super().update(attrs)

    def delete(self):
        """Delete Software in Bootstrap from BootstrapSoftware object."""
        return self


class BootstrapSoftwareImage(_SoftwareImage_Base_Class):
    """Bootstrap implementation of Bootstrap SoftwareImage model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create SoftwareImage in Bootstrap from BootstrapSoftwareImage object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update SoftwareImage in Bootstrap from BootstrapSoftwareImage object."""
        return super().update(attrs)

    def delete(self):
        """Delete SoftwareImage in Bootstrap from BootstrapSoftwareImage object."""
        return self


if validate_dlm_installed:

    class BootstrapValidatedSoftware(ValidatedSoftware):
        """Bootstrap implementation of Bootstrap ValidatedSoftware model."""

        @classmethod
        def create(cls, diffsync, ids, attrs):
            """Create ValidatedSoftware in Bootstrap from BootstrapValidatedSoftware object."""
            return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

        def update(self, attrs):
            """Update ValidatedSoftware in Bootstrap from BootstrapValidatedSoftware object."""
            return super().update(attrs)

        def delete(self):
            """Delete ValidatedSoftware in Bootstrap from BootstrapValidatedSoftware object."""
            return self


class BootstrapExternalIntegration(ExternalIntegration):
    """Bootstrap implementation of ExternalIntegration DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create ExternalIntegration in Bootstrap from BootstrapExternalIntegration object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update ExternalIntegration in Bootstrap from BootstrapExternalIntegration object."""
        return super().update(attrs)

    def delete(self):
        """Delete ExternalIntegration in Bootstrap from BootstrapExternalIntegration object."""
        return self
