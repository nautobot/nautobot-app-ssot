# pylint: disable=no-member
"""Nautobot DiffSync models for SolarWinds SSoT."""

from nautobot.dcim.models import Interface
from nautobot.ipam.models import IPAddress, IPAddressToInterface

from nautobot_ssot.integrations.solarwinds.diffsync.models.base import IPAddressToInterfaceModel


class NautobotIPAddressToInterfaceModel(IPAddressToInterfaceModel):
    """IPAddressToInterface model for Nautobot."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddressToInterface in Nautobot."""
        if adapter.job.debug:
            adapter.job.logger.debug(f"Creating IPAddressToInterface {ids} {attrs}")
        intf = Interface.objects.get(name=ids["interface__name"], device__name=ids["interface__device__name"])

        # try:
        obj = IPAddressToInterface(
            ip_address=IPAddress.objects.get(host=ids["ip_address__host"], tenant=intf.device.tenant),
            interface=intf,
        )
        obj.validated_save()
        # except IPAddress.DoesNotExist as e:
        #     print(f"IP: {ids=}, {intf=}, {intf.device=}")

        if (
            attrs.get("interface__device__primary_ip4__host")
            and ids["ip_address__host"] == attrs["interface__device__primary_ip4__host"]
        ):
            obj.interface.device.primary_ip4 = IPAddress.objects.get(
                host=attrs["interface__device__primary_ip4__host"],
                tenant=obj.interface.device.tenant,
            )
            obj.interface.device.validated_save()
        if (
            attrs.get("interface__device__primary_ip6__host")
            and ids["ip_address__host"] == attrs["interface__device__primary_ip6__host"]
        ):
            obj.interface.device.primary_ip6 = IPAddress.objects.get(
                host=attrs["interface__device__primary_ip6__host"],
                tenant=obj.interface.device.tenant,
            )
            obj.interface.device.validated_save()
        return super().create_base(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update IPAddressToInterface in Nautobot."""
        obj = self.get_from_db()
        if (
            attrs.get("interface__device__primary_ip4__host")
            and self.ip_address__host == attrs["interface__device__primary_ip4__host"]
        ):
            obj.interface.device.primary_ip4 = IPAddress.objects.get(
                host=attrs["interface__device__primary_ip4__host"], tenant=obj.interface.device.tenant
            )
            obj.interface.device.validated_save()
        if (
            attrs.get("interface__device__primary_ip6__host")
            and self.ip_address__host == attrs["interface__device__primary_ip6__host"]
        ):
            obj.interface.device.primary_ip6 = IPAddress.objects.get(
                host=attrs["interface__device__primary_ip6__host"], tenant=obj.interface.device.tenant
            )
            obj.interface.device.validated_save()
        return super().update_base(attrs)

    def delete(self):
        """Delete IPAddressToInterface in Nautobot."""
        return super().delete_base()
