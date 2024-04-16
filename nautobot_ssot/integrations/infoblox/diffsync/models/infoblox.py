"""Infoblox Models for Infoblox integration with SSoT app."""

from requests.exceptions import HTTPError
from nautobot_ssot.integrations.infoblox.diffsync.models.base import Network, IPAddress, Vlan, VlanView


class InfobloxNetwork(Network):
    """Infoblox implementation of the Network Model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Network object in Infoblox."""
        status = attrs.get("status")
        network = ids["network"]
        try:
            if status != "container":
                adapter.conn.create_network(prefix=network, comment=attrs.get("description", ""))
            else:
                adapter.conn.create_network_container(prefix=network, comment=attrs.get("description", ""))
        except HTTPError as err:
            adapter.job.logger.warning(f"Failed to create {ids['network']} due to {err.response.text}")
        dhcp_ranges = attrs.get("ranges")
        if dhcp_ranges:
            for dhcp_range in dhcp_ranges:
                start, end = dhcp_range.split("-")
                try:
                    adapter.conn.create_range(
                        prefix=network,
                        start=start.strip(),
                        end=end.strip(),
                    )
                except HTTPError as err:
                    adapter.job.logger.warning(f"Failed to create {dhcp_range} due to {err.response.text}")
        return super().create(ids=ids, adapter=adapter, attrs=attrs)

    def update(self, attrs):
        """Update Network object in Infoblox."""
        self.adapter.conn.update_network(
            prefix=self.get_identifiers()["network"], comment=attrs.get("description", "")
        )
        if attrs.get("ranges"):
            self.adapter.job.logger.warning(
                f"Prefix, {self.network}, has a change of Ranges in Nautobot, but"
                "updating InfoBlox with Ranges is currently not supported."
            )
        return super().update(attrs)

    # def delete(self):
    #     """Delete Network object in Infoblox."""
    #     self.adapter.conn.delete_network(self.get_identifiers()["network"])
    #     return super().delete()


class InfobloxVLANView(VlanView):
    """Infoblox implementation of the VLANView Model."""

    # @classmethod
    # def create(cls, adapter, ids, attrs):
    #     """Create VLANView object in Infoblox."""
    #     adapter.conn.create_vlan(
    #         vlan_id=ids["vid"],
    #         vlan_name=attrs["vlan_name"],
    #         vlan_view=attrs["vlangroup"] if attrs.get("vlangroup") else "nautobot",
    #     )
    #     return super().create(ids=ids, adapter=adapter, attrs=attrs)


class InfobloxVLAN(Vlan):
    """Infoblox implementation of the VLAN Model."""


#     @classmethod
#     def create(cls, adapter, ids, attrs):
#         """Create VLAN object in Infoblox."""
#         adapter.conn.create_vlan_view(name=ids.name)
#         return super().create(ids=ids, adapter=adapter, attrs=attrs)


class InfobloxIPAddress(IPAddress):
    """Infoblox implementation of the VLAN Model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create either a host record or fixed address (Not implemented).

        This requires the IP Address to either have a DNS name
        """
        if attrs["dns_name"]:
            adapter.conn.create_host_record(attrs["dns_name"], ids["address"])
        return super().create(ids=ids, adapter=adapter, attrs=attrs)

    def update(self, attrs):
        """Update IP Address object in Infoblox."""
        json = {"configure_for_dns": False}
        if attrs.get("description"):
            json.update({"comment": attrs["description"]})
        if attrs.get("dns_name"):
            json.update({"name": attrs["dns_name"]})
        if json:
            self.adapter.conn.update_ipaddress(ip_address=self.get_identifiers()["address"], data=json)
        return super().update(attrs)

    # def delete(self):
    #     """Delete an IP Address from Infoblox."""
    #     self.adapter.conn.delete_host_record(self.get_identifiers()["address"])
    #     return super().delete()
