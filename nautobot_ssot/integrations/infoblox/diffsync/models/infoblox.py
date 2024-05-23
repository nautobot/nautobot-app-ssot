"""Infoblox Models for Infoblox integration with SSoT app."""

from requests.exceptions import HTTPError
from nautobot_ssot.integrations.infoblox.diffsync.models.base import Namespace, Network, IPAddress, Vlan, VlanView
from nautobot_ssot.integrations.infoblox.utils.diffsync import map_network_view_to_namespace, validate_dns_name


class InfobloxNetwork(Network):
    """Infoblox implementation of the Network Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Network object in Infoblox."""
        status = attrs.get("status")
        network = ids["network"]
        try:
            if status != "container":
                diffsync.conn.create_network(prefix=network, comment=attrs.get("description", ""))
            else:
                diffsync.conn.create_network_container(prefix=network, comment=attrs.get("description", ""))
        except HTTPError as err:
            diffsync.job.logger.warning(f"Failed to create {ids['network']} due to {err.response.text}")
        dhcp_ranges = attrs.get("ranges")
        if dhcp_ranges:
            for dhcp_range in dhcp_ranges:
                start, end = dhcp_range.split("-")
                try:
                    diffsync.conn.create_range(
                        prefix=network,
                        start=start.strip(),
                        end=end.strip(),
                    )
                except HTTPError as err:
                    diffsync.job.logger.warning(f"Failed to create {dhcp_range} due to {err.response.text}")
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Network object in Infoblox."""
        self.diffsync.conn.update_network(
            prefix=self.get_identifiers()["network"], comment=attrs.get("description", "")
        )
        if attrs.get("ranges"):
            self.diffsync.job.logger.warning(
                f"Prefix, {self.network}, has a change of Ranges in Nautobot, but"
                " updating Ranges in InfoBlox is currently not supported."
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
        """Create either a Host record or an A record.

        Optionally creates a PTR record in addition to an A record.

        This requires the IP Address to have a DNS name
        """
        network_view = map_network_view_to_namespace(value=ids["namespace"], direction="ns_to_nv")
        dns_name = attrs.get("dns_name")
        ip_address = ids["address"]
        if not dns_name:
            diffsync.job.logger.warning(
                f"Cannot create Infoblox record for IP Address {ip_address}. DNS name is not defined."
            )
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        # Nautobot side doesn't check if dns name is a FQDN. Additionally, Infoblox won't accept DNS name if the corresponding zone FQDN doesn't exist.
        if not validate_dns_name(diffsync.conn, dns_name, network_view):
            diffsync.job.logger.warning(f"Invalid zone fqdn in DNS name `{dns_name}` for IP Address {ip_address}")
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        if diffsync.config.create_a_record and attrs.get("has_a_record"):
            diffsync.conn.create_a_record(dns_name, ip_address, network_view=network_view)
            # Only create PTR records if A record has been created
            if diffsync.config.create_ptr_record and attrs.get("has_ptr_record"):
                diffsync.conn.create_ptr_record(dns_name, ip_address, network_view=network_view)
        elif diffsync.config.create_host_record and attrs.get("has_host_record"):
            diffsync.conn.create_host_record(dns_name, ip_address, network_view=network_view)
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):  # pylint: disable=too-many-branches
        """Update IP Address object in Infoblox."""
        ids = self.get_identifiers()
        inf_attrs = self.get_attrs()
        ip_address = ids["address"]
        network_view = map_network_view_to_namespace(value=ids["namespace"], direction="ns_to_nv")
        payload = {}
        if attrs.get("description"):
            payload.update({"comment": attrs["description"]})
        if attrs.get("dns_name"):
            payload.update({"name": attrs["dns_name"]})

        # Nautobot side doesn't check if dns name is fqdn. Additionally, Infoblox won't allow dns name if the zone fqdn doesn't exist.
        # We get either existing DNS name, or a new one. This is because name might be the same but we need to create a PTR record.
        dns_name = attrs.get("dns_name", inf_attrs["dns_name"])
        if not dns_name:
            self.diffsync.job.logger.warning(
                f"Cannot update Infoblox record for IP Address {ip_address}. DNS name is not defined."
            )
            return super().update(attrs)
        if not validate_dns_name(self.diffsync.conn, dns_name, network_view):
            self.diffsync.job.logger.warning(f"Invalid zone fqdn in DNS name `{dns_name}` for IP Address {ip_address}")
            return super().update(attrs)

        # Infoblox Host record acts as a combined A/PTR record.
        # Only allow creating/updating A and PTR record if IP Address doesn't have a corresponding Host record.
        # Only allows creating/updating Host record if IP Address doesn't have a corresponding A or PTR record.
        incompatible_record_types = False
        if attrs.get("has_a_record", False) and self.diffsync.config.create_a_record and inf_attrs["has_host_record"]:
            incomp_msg = f"Cannot update A Record for IP Address, {ip_address}. It already has an existing Host Record."
            incompatible_record_types = True
        elif (
            attrs.get("has_ptr_record", False)
            and self.diffsync.config.create_ptr_record
            and inf_attrs["has_host_record"]
        ):
            incomp_msg = (
                f"Cannot create/update PTR Record for IP Address, {ip_address}. It already has an existing Host Record."
            )
            incompatible_record_types = True
        elif (
            attrs.get("has_host_record", False)
            and self.diffsync.config.create_host_record
            and inf_attrs["has_a_record"]
        ):
            incomp_msg = f"Cannot update Host Record for IP Address, {ip_address}. It already has an existing A Record."
            incompatible_record_types = True
        elif (
            attrs.get("has_host_record", False)
            and self.diffsync.config.create_host_record
            and inf_attrs["has_ptr_record"]
        ):
            incomp_msg = (
                f"Cannot update Host Record for IP Address, {ip_address}. It already has an existing PTR Record."
            )
            incompatible_record_types = True

        if incompatible_record_types:
            self.diffsync.job.logger.warning(incomp_msg)
            return super().update(attrs)

        a_record_action = "none"
        ptr_record_action = "none"
        host_record_action = "none"
        if self.diffsync.config.create_a_record and inf_attrs["has_a_record"]:
            a_record_action = "update"
        if self.diffsync.config.create_ptr_record:
            ptr_record_action = "update" if inf_attrs["has_ptr_record"] else "create"
        if self.diffsync.config.create_host_record and inf_attrs["has_host_record"]:
            host_record_action = "update"

        # IP Address in Infoblox is not a plain IP Address like in Nautobot.
        # In Infoblox we can fixed_address (not supported here), Host record for IP Address, or A Record for IP Address.
        # When syncing from Nautobot to Infoblox we take IP Address and check if it has dns_name field populated.
        # We then combine this with the Infoblox Config toggles to arrive at the desired state in Infoblox.
        if host_record_action == "update" and payload:
            self.diffsync.conn.update_host_record(ref=self.host_record_ref, data=payload)
        if a_record_action == "update" and payload:
            self.diffsync.conn.update_a_record(ref=self.a_record_ref, data=payload)
        if ptr_record_action == "update" and payload:
            self.diffsync.conn.update_ptr_record(ref=self.ptr_record_ref, data=payload)
        elif ptr_record_action == "create":
            self.diffsync.conn.create_ptr_record(dns_name, ip_address, network_view=network_view)
        return super().update(attrs)

    # def delete(self):
    #     """Delete an IP Address from Infoblox."""
    #     self.diffsync.conn.delete_host_record(self.get_identifiers()["address"])
    #     return super().delete()


class InfobloxNamespace(Namespace):
    """Infoblox implementation of the Namespace model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Don't allow creating Network Views in Infoblox."""
        diffsync.job.logger.error(
            f"Creating Network Views in Infoblox is not allowed. Nautobot Namespace: {ids['name']}"
        )
        raise NotImplementedError

    def update(self, attrs):
        """Don't allow updating Network Views in Infoblox."""
        self.diffsync.job.logger.error(
            f"Updating Network Views in Infoblox is not allowed. Nautobot Namespace: {self.get_identifiers()['name']}"
        )
        raise NotImplementedError

    def delete(self):
        """Don't allow deleting Network Views in Infoblox."""
        self.diffsync.job.logger.error(
            f"Deleting Network Views in Infoblox is not allowed. Nautobot Namespace: {self.get_identifiers()['name']}"
        )
        raise NotImplementedError
