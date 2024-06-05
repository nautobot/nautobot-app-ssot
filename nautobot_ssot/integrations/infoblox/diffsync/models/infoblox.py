"""Infoblox Models for Infoblox integration with SSoT app."""

from requests.exceptions import HTTPError

from nautobot_ssot.integrations.infoblox.choices import DNSRecordTypeChoices, FixedAddressTypeChoices
from nautobot_ssot.integrations.infoblox.diffsync.models.base import IPAddress, Namespace, Network, Vlan, VlanView
from nautobot_ssot.integrations.infoblox.utils.diffsync import map_network_view_to_namespace, validate_dns_name


class InfobloxNetwork(Network):
    """Infoblox implementation of the Network Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Network object in Infoblox."""
        status = attrs.get("status")
        network = ids["network"]
        network_view = ids["namespace"]
        try:
            if status != "container":
                diffsync.conn.create_network(
                    prefix=network, comment=attrs.get("description", ""), network_view=network_view
                )
            else:
                diffsync.conn.create_network_container(
                    prefix=network, comment=attrs.get("description", ""), network_view=network_view
                )
        except HTTPError as err:
            diffsync.job.logger.warning(f"Failed to create {network}-{network_view} due to {err.response.text}")
        dhcp_ranges = attrs.get("ranges")
        if dhcp_ranges:
            for dhcp_range in dhcp_ranges:
                start, end = dhcp_range.split("-")
                try:
                    diffsync.conn.create_range(
                        prefix=network,
                        start=start.strip(),
                        end=end.strip(),
                        network_view=network_view,
                    )
                except HTTPError as err:
                    diffsync.job.logger.warning(
                        f"Failed to create {dhcp_range}-{network_view} due to {err.response.text}"
                    )
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update Network object in Infoblox."""
        self.diffsync.conn.update_network(
            prefix=self.get_identifiers()["network"],
            network_view=self.get_identifiers()["namespace"],
            comment=attrs.get("description", ""),
        )
        if attrs.get("ranges"):
            self.diffsync.job.logger.warning(
                f"Prefix, {self.network}-{self.namespace}, has a change of Ranges in Nautobot, but"
                " updating Ranges in InfoBlox is currently not supported."
            )
        return super().update(attrs)


class InfobloxVLANView(VlanView):
    """Infoblox implementation of the VLANView Model."""


class InfobloxVLAN(Vlan):
    """Infoblox implementation of the VLAN Model."""


class InfobloxIPAddress(IPAddress):
    """Infoblox implementation of the VLAN Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Creates IP Address Reservation. Additionally create DNS Host record or an A record.

        Optionally creates a PTR record in addition to an A record.

        DNS record creation requires the IP Address to have a DNS name
        """
        network_view = map_network_view_to_namespace(value=ids["namespace"], direction="ns_to_nv")
        dns_name = attrs.get("dns_name")
        ip_address = ids["address"]
        name = attrs.get("description")
        mac_address = attrs.get("mac_address")

        # Used DNS name for fixed address name if it exists. Otherwise use description.
        if dns_name:
            fixed_address_name = dns_name
        else:
            fixed_address_name = name

        if diffsync.config.fixed_address_type == FixedAddressTypeChoices.RESERVED:
            diffsync.conn.create_fixed_address(
                ip_address=ip_address, name=fixed_address_name, match_client="RESERVED", network_view=network_view
            )
            diffsync.job.logger.debug(
                "Created fixed address reservation, address: %s, name: %s, network_view: %s",
                ip_address,
                fixed_address_name,
                network_view,
            )
        elif diffsync.config.fixed_address_type == FixedAddressTypeChoices.MAC_ADDRESS and mac_address:
            diffsync.conn.create_fixed_address(
                ip_address=ip_address,
                name=fixed_address_name,
                mac_address=mac_address,
                match_client="MAC_ADDRESS",
                network_view=network_view,
            )
            diffsync.job.logger.debug(
                "Created fixed address with MAC, address: %s, name: %s, mac address: %s, network_view: %s",
                ip_address,
                fixed_address_name,
                mac_address,
                network_view,
            )

        # DNS record not needed, we can return
        if diffsync.config.dns_record_type == DNSRecordTypeChoices.DONT_CREATE_RECORD:
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        if not dns_name:
            diffsync.job.logger.warning(
                f"Cannot create Infoblox DNS record for IP Address {ip_address}. DNS name is not defined."
            )
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        # Nautobot side doesn't check if dns name is a FQDN. Additionally, Infoblox won't accept DNS name if the corresponding zone FQDN doesn't exist.
        if not validate_dns_name(diffsync.conn, dns_name, network_view):
            diffsync.job.logger.warning(f"Invalid zone fqdn in DNS name `{dns_name}` for IP Address {ip_address}.")
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        if diffsync.config.dns_record_type == DNSRecordTypeChoices.A_RECORD:
            diffsync.conn.create_a_record(dns_name, ip_address, network_view=network_view)
            diffsync.job.logger.debug(
                "Created DNS A record, address: %s, dns_name: %s, network_view: %s",
                ip_address,
                dns_name,
                network_view,
            )
        elif diffsync.config.dns_record_type == DNSRecordTypeChoices.A_AND_PTR_RECORD:
            diffsync.conn.create_a_record(dns_name, ip_address, network_view=network_view)
            diffsync.job.logger.debug(
                "Created DNS A record, address: %s, dns_name: %s, network_view: %s",
                ip_address,
                dns_name,
                network_view,
            )
            diffsync.conn.create_ptr_record(dns_name, ip_address, network_view=network_view)
            diffsync.job.logger.debug(
                "Created DNS PTR record, address: %s, dns_name: %s, network_view: %s",
                ip_address,
                dns_name,
                network_view,
            )
        elif diffsync.config.dns_record_type == DNSRecordTypeChoices.HOST_RECORD:
            diffsync.conn.create_host_record(dns_name, ip_address, network_view=network_view)
            diffsync.job.logger.debug(
                "Created DNS Host record, address: %s, dns_name: %s, network_view: %s",
                ip_address,
                dns_name,
                network_view,
            )
        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def _update_fixed_address(self, new_attrs: dict, inf_attrs: dict, ip_address: str, network_view: str) -> None:
        """Updates fixed address record in Infoblox.

        Args:
            new_attrs: Object attributes changed in Nautobot
            inf_attrs: Infoblox object attributes
            ip_address: IP address of the fixed address
            network_view: Network View of the fixed address
        """
        new_dns_name = new_attrs.get("dns_name")
        new_description = new_attrs.get("description")
        mac_address = new_attrs.get("mac_address")

        fa_update_data = {}
        # Fixed Address name uses DNS Name if it's defined, then description.
        if new_dns_name:
            fa_update_data["name"] = new_dns_name
        # DNS name cleared on Nautobot side
        if new_dns_name == "":
            # Description updated on Nautobot side
            if new_description:
                fa_update_data["name"] = new_description
            # Nautobot description not updated. Copy Infoblox description over to the name attribute.
            elif inf_attrs.get("description"):
                fa_update_data["name"] = inf_attrs.get("description")
        if new_description:
            fa_update_data["comment"] = new_description

        if (
            self.diffsync.config.fixed_address_type == FixedAddressTypeChoices.RESERVED
            and self.fixed_address_type == "RESERVED"
            and fa_update_data
        ):
            self.diffsync.conn.update_fixed_address(ref=self.fixed_address_ref, data=fa_update_data)
            self.diffsync.job.logger.debug(
                "Updated fixed address reservation, address: %s, network_view: %s, update data: %s",
                ip_address,
                network_view,
                fa_update_data,
            )
        elif (
            self.diffsync.config.fixed_address_type == FixedAddressTypeChoices.MAC_ADDRESS
            and self.fixed_address_type == "MAC_ADDRESS"
            and (fa_update_data or mac_address)
        ):
            if mac_address:
                fa_update_data["mac"] = mac_address
            self.diffsync.conn.update_fixed_address(ref=self.fixed_address_ref, data=fa_update_data)
            self.diffsync.job.logger.debug(
                "Updated fixed address with MAC, address: %s, network_view: %s, update data: %s",
                ip_address,
                network_view,
                fa_update_data,
            )

    def _check_for_incompatible_record_types(self, attrs: dict, inf_attrs: dict, ip_address: str):
        """Checks whether requested changes to the DNS records are compatible with existing Infoblox DNS objects.

        Args:
            attrs: Changed Nautobot object attributes
            inf_attrs: Infoblox objects attributes
            ip_address: IP address of the record

        Returns:
            tuple (bool, str)
        """
        # Infoblox Host record acts as a combined A/PTR record.
        # Only allow creating/updating A and PTR record if IP Address doesn't have a corresponding Host record.
        # Only allows creating/updating Host record if IP Address doesn't have a corresponding A or PTR record.
        incompatible_record_types = False
        incomp_msg = ""
        if (
            attrs.get("has_a_record", False)
            and self.diffsync.config.dns_record_type == DNSRecordTypeChoices.A_RECORD
            and inf_attrs["has_host_record"]
        ):
            incomp_msg = f"Cannot update A Record for IP Address, {ip_address}. It already has an existing Host Record."
            incompatible_record_types = True
        elif (
            attrs.get("has_ptr_record", False)
            and self.diffsync.config.dns_record_type == DNSRecordTypeChoices.A_AND_PTR_RECORD
            and inf_attrs["has_host_record"]
        ):
            incomp_msg = (
                f"Cannot create/update PTR Record for IP Address, {ip_address}. It already has an existing Host Record."
            )
            incompatible_record_types = True
        elif (
            attrs.get("has_host_record", False)
            and self.diffsync.config.dns_record_type == DNSRecordTypeChoices.HOST_RECORD
            and inf_attrs["has_a_record"]
        ):
            incomp_msg = f"Cannot update Host Record for IP Address, {ip_address}. It already has an existing A Record."
            incompatible_record_types = True
        elif (
            attrs.get("has_host_record", False)
            and self.diffsync.config.dns_record_type == DNSRecordTypeChoices.HOST_RECORD
            and inf_attrs["has_ptr_record"]
        ):
            incomp_msg = (
                f"Cannot update Host Record for IP Address, {ip_address}. It already has an existing PTR Record."
            )
            incompatible_record_types = True

        return incompatible_record_types, incomp_msg

    def update(self, attrs):  # pylint: disable=too-many-branches,too-many-locals,too-many-statements
        """Update IP Address object in Infoblox."""
        ids = self.get_identifiers()
        inf_attrs = self.get_attrs()
        ip_address = ids["address"]
        network_view = map_network_view_to_namespace(value=ids["namespace"], direction="ns_to_nv")

        # Update fixed address
        if inf_attrs.get("has_fixed_address"):
            self._update_fixed_address(
                new_attrs=attrs, inf_attrs=inf_attrs, ip_address=ip_address, network_view=network_view
            )

        # DNS record not needed, we can return
        if self.diffsync.config.dns_record_type == DNSRecordTypeChoices.DONT_CREATE_RECORD:
            return super().update(attrs)

        # Nautobot side doesn't check if dns name is a fqdn. Additionally, Infoblox won't allow dns name if the zone fqdn doesn't exist.
        # We get either existing DNS name, or a new one. This is because name might be the same but we need to create a PTR record.
        canonical_dns_name = attrs.get("dns_name", inf_attrs["dns_name"])
        if not canonical_dns_name:
            self.diffsync.job.logger.warning(
                f"Cannot update Infoblox record for IP Address {ip_address}. DNS name is not defined."
            )
            return super().update(attrs)
        if not validate_dns_name(self.diffsync.conn, canonical_dns_name, network_view):
            self.diffsync.job.logger.warning(
                f"Invalid zone fqdn in DNS name `{canonical_dns_name}` for IP Address {ip_address}"
            )
            return super().update(attrs)

        incompatible_record_types, incomp_msg = self._check_for_incompatible_record_types(
            attrs=attrs, inf_attrs=inf_attrs, ip_address=ip_address
        )
        if incompatible_record_types:
            self.diffsync.job.logger.warning(incomp_msg)
            return super().update(attrs)

        dns_payload = {}
        ptr_payload = {}
        new_description = attrs.get("description")
        if new_description:
            dns_payload.update({"comment": new_description})
            ptr_payload.update({"comment": new_description})
        if attrs.get("dns_name"):
            dns_payload.update({"name": attrs.get("dns_name")})
            ptr_payload.update({"ptrdname": attrs.get("dns_name")})

        a_record_action = ptr_record_action = host_record_action = "none"
        if self.diffsync.config.dns_record_type == DNSRecordTypeChoices.A_RECORD:
            a_record_action = "update" if inf_attrs["has_a_record"] else "create"
        elif self.diffsync.config.dns_record_type == DNSRecordTypeChoices.A_AND_PTR_RECORD:
            a_record_action = "update" if inf_attrs["has_a_record"] else "create"
            ptr_record_action = "update" if inf_attrs["has_ptr_record"] else "create"
        elif self.diffsync.config.dns_record_type == DNSRecordTypeChoices.HOST_RECORD:
            host_record_action = "update" if inf_attrs["has_host_record"] else "create"

        # IP Address in Infoblox is not a plain IP Address like in Nautobot.
        # In Infoblox we can have Fixed Address, Host record for IP Address, or A Record for IP Address.
        # When syncing from Nautobot to Infoblox we take IP Address and check if it has dns_name field populated.
        # We then combine this with the Infoblox Config toggles to arrive at the desired state in Infoblox.
        if host_record_action == "update" and dns_payload:
            self.diffsync.conn.update_host_record(ref=self.host_record_ref, data=dns_payload)
            self.diffsync.job.logger.debug(
                "Updated Host record, address: %s, network_view: %s, update data: %s",
                ip_address,
                network_view,
                dns_payload,
            )
        elif host_record_action == "create":
            self.diffsync.conn.create_host_record(canonical_dns_name, ip_address, network_view=network_view)
            self.diffsync.job.logger.debug(
                "Created Host record, address: %s, network_view: %s, DNS name: %s",
                ip_address,
                network_view,
                canonical_dns_name,
            )
        if a_record_action == "update" and dns_payload:
            self.diffsync.conn.update_a_record(ref=self.a_record_ref, data=dns_payload)
            self.diffsync.job.logger.debug(
                "Updated A record, address: %s, network_view: %s, update data: %s",
                ip_address,
                network_view,
                dns_payload,
            )
        elif a_record_action == "create":
            self.diffsync.conn.create_a_record(canonical_dns_name, ip_address, network_view=network_view)
            self.diffsync.job.logger.debug(
                "Created A record, address: %s, network_view: %s, DNS name: %s",
                ip_address,
                network_view,
                canonical_dns_name,
            )
        if ptr_record_action == "update" and ptr_payload:
            self.diffsync.conn.update_ptr_record(ref=self.ptr_record_ref, data=ptr_payload)
            self.diffsync.job.logger.debug(
                "Updated PTR record, address: %s, network_view: %s, update data: %s",
                ip_address,
                network_view,
                ptr_payload,
            )
        elif ptr_record_action == "create":
            self.diffsync.conn.create_ptr_record(canonical_dns_name, ip_address, network_view=network_view)
            self.diffsync.job.logger.debug(
                "Created PTR record, address: %s, network_view: %s, DNS name: %s",
                ip_address,
                network_view,
                canonical_dns_name,
            )
        return super().update(attrs)


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
