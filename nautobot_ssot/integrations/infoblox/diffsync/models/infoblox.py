"""Infoblox Models for Infoblox integration with SSoT plugin."""
from requests.exceptions import HTTPError
from nautobot_ssot_infoblox.diffsync.models.base import Aggregate, Network, IPAddress, Vlan, VlanView


class InfobloxNetwork(Network):
    """Infoblox implementation of the Network Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Network object in Infoblox."""
        status = attrs.get("status")
        try:
            if status != "container":
                diffsync.conn.create_network(prefix=ids["network"], comment=attrs.get("description", ""))
            else:
                diffsync.conn.create_network_container(prefix=ids["network"], comment=attrs.get("description", ""))
        except HTTPError as err:
            diffsync.job.log_warning(f"Failed to create {ids['network']} due to {err.response.text}")
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Network object in Infoblox."""
        self.diffsync.conn.update_network(
            prefix=self.get_identifiers()["network"], comment=attrs.get("description", "")
        )
        return super().update(attrs)

    # def delete(self):
    #     """Delete Network object in Infoblox."""
    #     self.diffsync.conn.delete_network(self.get_identifiers()["network"])
    #     return super().delete()


class InfobloxVLANView(VlanView):
    """Infoblox implementation of the VLANView Model."""

    # @classmethod
    # def create(cls, diffsync, ids, attrs):
    #     """Create VLANView object in Infoblox."""
    #     diffsync.conn.create_vlan(
    #         vlan_id=ids["vid"],
    #         vlan_name=attrs["vlan_name"],
    #         vlan_view=attrs["vlangroup"] if attrs.get("vlangroup") else "nautobot",
    #     )
    #     return super().create(ids=ids, diffsync=diffsync, attrs=attrs)


class InfobloxVLAN(Vlan):
    """Infoblox implementation of the VLAN Model."""


#     @classmethod
#     def create(cls, diffsync, ids, attrs):
#         """Create VLAN object in Infoblox."""
#         diffsync.conn.create_vlan_view(name=ids.name)
#         return super().create(ids=ids, diffsync=diffsync, attrs=attrs)


class InfobloxIPAddress(IPAddress):
    """Infoblox implementation of the VLAN Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create either a host record or fixed address (Not implemented).

        This requires the IP Address to either have a DNS name
        """
        if attrs["dns_name"]:
            diffsync.conn.create_host_record(attrs["dns_name"], ids["address"])
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update IP Address object in Infoblox."""
        json = {"configure_for_dns": False}
        if attrs.get("description"):
            json.update({"comment": attrs["description"]})
        if attrs.get("dns_name"):
            json.update({"name": attrs["dns_name"]})
        if json:
            self.diffsync.conn.update_ipaddress(ip_address=self.get_identifiers()["address"], data=json)
        return super().update(attrs)

    # def delete(self):
    #     """Delete an IP Address from Infoblox."""
    #     self.diffsync.conn.delete_host_record(self.get_identifiers()["address"])
    #     return super().delete()


class InfobloxAggregate(Aggregate):
    """Infoblox implementation of the Aggregate Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Network Container object in Infoblox."""
        diffsync.conn.create_network_container(
            prefix=ids["network"], comment=attrs["description"] if attrs.get("description") else ""
        )
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Network Container object in Infoblox."""
        self.diffsync.conn.update_network_container(
            prefix=self.get_identifiers()["network"], comment=attrs["description"] if attrs.get("description") else ""
        )
        return super().update(attrs)

    def delete(self):
        """Delete Network Container object in Infoblox."""
        self.diffsync.conn.delete_network_container(self.get_identifiers()["network"])
        return super().delete()
