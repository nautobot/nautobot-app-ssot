"""Infoblox Models for Infoblox integration with SSoT app."""

from requests.exceptions import HTTPError

from nautobot_ssot.integrations.infoblox.choices import (
    DNSRecordTypeChoices,
    FixedAddressTypeChoices,
    InfobloxDeletableModelChoices,
)
from nautobot_ssot.integrations.infoblox.diffsync.models.base import (
    DnsARecord,
    DnsHostRecord,
    DnsPTRRecord,
    IPAddress,
    Namespace,
    Network,
    Vlan,
    VlanView,
)
from nautobot_ssot.integrations.infoblox.utils.diffsync import map_network_view_to_namespace, validate_dns_name


class InfobloxNetwork(Network):
    """Infoblox implementation of the Network Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Network object in Infoblox."""
        network_type = attrs.get("network_type")
        network = ids["network"]
        network_view = map_network_view_to_namespace(value=ids["namespace"], direction="ns_to_nv")
        try:
            if network_type != "container":
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
        network_view = map_network_view_to_namespace(value=self.get_identifiers()["namespace"], direction="ns_to_nv")
        self.diffsync.conn.update_network(
            prefix=self.get_identifiers()["network"],
            network_view=network_view,
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
        """Creates Fixed Address record."""
        network_view = map_network_view_to_namespace(value=ids["namespace"], direction="ns_to_nv")
        ip_address = ids["address"]
        mac_address = attrs.get("mac_address")
        has_fixed_address = attrs.get("has_fixed_address", False)
        fixed_address_name = attrs.get("description") or ""
        fixed_address_comment = attrs.get("fixed_address_comment") or ""

        if diffsync.config.fixed_address_type == FixedAddressTypeChoices.RESERVED and has_fixed_address:
            diffsync.conn.create_fixed_address(
                ip_address=ip_address,
                name=fixed_address_name,
                comment=fixed_address_comment,
                match_client="RESERVED",
                network_view=network_view,
            )
            if diffsync.job.debug:
                diffsync.job.logger.debug(
                    "Created fixed address reservation, address: %s, name: %s, network_view: %s, comment: %s",
                    ip_address,
                    fixed_address_name,
                    network_view,
                    fixed_address_comment,
                )
        elif (
            diffsync.config.fixed_address_type == FixedAddressTypeChoices.MAC_ADDRESS
            and mac_address
            and has_fixed_address
        ):
            diffsync.conn.create_fixed_address(
                ip_address=ip_address,
                name=fixed_address_name,
                mac_address=mac_address,
                match_client="MAC_ADDRESS",
                comment=fixed_address_comment,
                network_view=network_view,
            )
            if diffsync.job.debug:
                diffsync.job.logger.debug(
                    "Created fixed address with MAC, address: %s, name: %s, mac address: %s, network_view: %s, comment: %s",
                    ip_address,
                    fixed_address_name,
                    mac_address,
                    network_view,
                    fixed_address_comment,
                )

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):  # pylint: disable=too-many-branches
        """Update IP Address object in Infoblox."""
        ids = self.get_identifiers()
        inf_attrs = self.get_attrs()
        ip_address = ids["address"]
        network_view = map_network_view_to_namespace(value=ids["namespace"], direction="ns_to_nv")

        mac_address = attrs.get("mac_address")
        fixed_address_name = attrs.get("description") or ""
        fixed_address_comment = attrs.get("fixed_address_comment") or ""

        # Attempt update of a fixed address if Infoblox has one already
        if inf_attrs.get("has_fixed_address"):
            fa_update_data = {}
            if "description" in attrs:
                fa_update_data["name"] = fixed_address_name
            if "fixed_address_comment" in attrs:
                fa_update_data["comment"] = fixed_address_comment

            if (
                self.diffsync.config.fixed_address_type == FixedAddressTypeChoices.RESERVED
                and self.fixed_address_type == "RESERVED"
                and fa_update_data
            ):
                self.diffsync.conn.update_fixed_address(ref=self.fixed_address_ref, data=fa_update_data)
                if self.diffsync.job.debug:
                    self.diffsync.job.logger.debug(
                        "Updated fixed address reservation, address: %s, network_view: %s, update data: %s",
                        ip_address,
                        network_view,
                        fa_update_data,
                        extra={"grouping": "update"},
                    )
            elif (
                self.diffsync.config.fixed_address_type == FixedAddressTypeChoices.MAC_ADDRESS
                and self.fixed_address_type == "MAC_ADDRESS"
                and (fa_update_data or mac_address)
            ):
                if mac_address:
                    fa_update_data["mac"] = mac_address
                self.diffsync.conn.update_fixed_address(ref=self.fixed_address_ref, data=fa_update_data)
                if self.diffsync.job.debug:
                    self.diffsync.job.logger.debug(
                        "Updated fixed address with MAC, address: %s, network_view: %s, update data: %s",
                        ip_address,
                        network_view,
                        fa_update_data,
                        extra={"grouping": "update"},
                    )
        # IP Address exists in Infoblox without Fixed Address object. Nautobot side is asking for Fixed Address so we need to create one.
        elif (
            attrs.get("has_fixed_address")
            and self.diffsync.config.fixed_address_type != FixedAddressTypeChoices.DONT_CREATE_RECORD
        ):
            if self.diffsync.config.fixed_address_type == FixedAddressTypeChoices.RESERVED:
                self.diffsync.conn.create_fixed_address(
                    ip_address=ip_address,
                    name=fixed_address_name,
                    comment=fixed_address_comment,
                    match_client="RESERVED",
                    network_view=network_view,
                )
                if self.diffsync.job.debug:
                    self.diffsync.job.logger.debug(
                        "Created fixed address reservation, address: %s, name: %s, network_view: %s, comment: %s",
                        ip_address,
                        fixed_address_name,
                        network_view,
                        fixed_address_comment,
                        extra={"grouping": "update"},
                    )
            elif self.diffsync.config.fixed_address_type == FixedAddressTypeChoices.MAC_ADDRESS and mac_address:
                self.diffsync.conn.create_fixed_address(
                    ip_address=ip_address,
                    name=fixed_address_name,
                    mac_address=mac_address,
                    comment=fixed_address_comment,
                    match_client="MAC_ADDRESS",
                    network_view=network_view,
                )
                if self.diffsync.job.debug:
                    self.diffsync.job.logger.debug(
                        "Created fixed address with MAC, address: %s, name: %s, mac address: %s, network_view: %s, comment: %s",
                        ip_address,
                        fixed_address_name,
                        mac_address,
                        network_view,
                        fixed_address_comment,
                        extra={"grouping": "update"},
                    )

        return super().update(attrs)

    def delete(self):
        """Delete Fixed Address in Infoblox."""
        if InfobloxDeletableModelChoices.FIXED_ADDRESS not in self.diffsync.config.infoblox_deletable_models:
            return super().delete()

        if self.diffsync.config.fixed_address_type == FixedAddressTypeChoices.DONT_CREATE_RECORD:
            return super().delete()

        network_view = map_network_view_to_namespace(value=self.namespace, direction="ns_to_nv")
        self.diffsync.conn.delete_fixed_address_record_by_ref(self.fixed_address_ref)
        self.diffsync.job.logger.info(
            "Deleted Fixed Address record in Infoblox, address: %s, network_view: %s",
            self.address,
            network_view,
        )
        return super().delete()


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


class InfobloxDnsARecord(DnsARecord):
    """Infoblox implementation of the DnsARecord Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create DNS A record in Infoblox."""
        # DNS record not needed, we can return
        if diffsync.config.dns_record_type not in (
            DNSRecordTypeChoices.A_RECORD,
            DNSRecordTypeChoices.A_AND_PTR_RECORD,
        ):
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        network_view = map_network_view_to_namespace(value=ids["namespace"], direction="ns_to_nv")
        ip_address = ids["address"]
        dns_name = attrs.get("dns_name")
        dns_comment = attrs.get("description")
        if not dns_name:
            diffsync.job.logger.warning(
                f"Cannot create Infoblox DNS A record for IP Address {ip_address}. DNS name is not defined."
            )
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        # Nautobot side doesn't check if dns name is a FQDN. Additionally, Infoblox won't accept DNS name if the corresponding zone FQDN doesn't exist.
        if not validate_dns_name(diffsync.conn, dns_name, network_view):
            diffsync.job.logger.warning(f"Invalid zone fqdn in DNS name `{dns_name}` for IP Address {ip_address}.")
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        diffsync.conn.create_a_record(dns_name, ip_address, dns_comment, network_view=network_view)
        if diffsync.job.debug:
            diffsync.job.logger.debug(
                "Created DNS A record, address: %s, dns_name: %s, network_view: %s, comment: %s",
                ip_address,
                dns_name,
                network_view,
                dns_comment,
            )

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update DNS A record in Infoblox."""
        # DNS record not needed, we can return
        if self.diffsync.config.dns_record_type not in (
            DNSRecordTypeChoices.A_RECORD,
            DNSRecordTypeChoices.A_AND_PTR_RECORD,
        ):
            return super().update(attrs)

        network_view = map_network_view_to_namespace(value=self.namespace, direction="ns_to_nv")
        dns_payload = {}
        dns_comment = attrs.get("description")
        if dns_comment:
            dns_payload["comment"] = dns_comment
        if attrs.get("dns_name"):
            # Nautobot side doesn't check if dns name is a FQDN. Additionally, Infoblox won't accept DNS name if the corresponding zone FQDN doesn't exist.
            if not validate_dns_name(self.diffsync.conn, attrs.get("dns_name"), network_view):
                self.diffsync.job.logger.warning(
                    f"Invalid zone fqdn in DNS name `{attrs.get('dns_name')}` for IP Address {self.address}."
                )
                return super().update(attrs)

            dns_payload["name"] = attrs.get("dns_name")

        if dns_payload:
            self.diffsync.conn.update_a_record(ref=self.ref, data=dns_payload)
            if self.diffsync.job.debug:
                self.diffsync.job.logger.debug(
                    "Updated A record, address: %s, network_view: %s, update data: %s",
                    self.address,
                    network_view,
                    dns_payload,
                )

        return super().update(attrs)

    def delete(self):
        """Delete A Record in Infoblox."""
        if InfobloxDeletableModelChoices.DNS_A_RECORD not in self.diffsync.config.infoblox_deletable_models:
            return super().delete()

        if self.diffsync.config.dns_record_type not in (
            DNSRecordTypeChoices.A_RECORD,
            DNSRecordTypeChoices.A_AND_PTR_RECORD,
        ):
            return super().delete()

        network_view = map_network_view_to_namespace(value=self.namespace, direction="ns_to_nv")
        self.diffsync.conn.delete_a_record_by_ref(self.ref)
        self.diffsync.job.logger.info(
            "Deleted A record in Infoblox, address: %s, network_view: %s",
            self.address,
            network_view,
        )
        return super().delete()


class InfobloxDnsHostRecord(DnsHostRecord):
    """Infoblox implementation of the DnsHostRecord Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create DNS Host record in Infoblox."""
        # DNS record not needed, we can return
        if diffsync.config.dns_record_type != DNSRecordTypeChoices.HOST_RECORD:
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        network_view = map_network_view_to_namespace(value=ids["namespace"], direction="ns_to_nv")
        ip_address = ids["address"]
        dns_name = attrs.get("dns_name")
        dns_comment = attrs.get("description")
        if not dns_name:
            diffsync.job.logger.warning(
                f"Cannot create Infoblox DNS Host record for IP Address {ip_address}. DNS name is not defined."
            )
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        # Nautobot side doesn't check if dns name is a FQDN. Additionally, Infoblox won't accept DNS name if the corresponding zone FQDN doesn't exist.
        if not validate_dns_name(diffsync.conn, dns_name, network_view):
            diffsync.job.logger.warning(f"Invalid zone fqdn in DNS name `{dns_name}` for IP Address {ip_address}.")
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        diffsync.conn.create_host_record(dns_name, ip_address, dns_comment, network_view=network_view)
        if diffsync.job.debug:
            diffsync.job.logger.debug(
                "Created DNS Host record, address: %s, dns_name: %s, network_view: %s, comment: %s",
                ip_address,
                dns_name,
                network_view,
                dns_comment,
            )

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update DNS Host record in Infoblox."""
        # DNS record not needed, we can return
        if self.diffsync.config.dns_record_type != DNSRecordTypeChoices.HOST_RECORD:
            return super().update(attrs)

        network_view = map_network_view_to_namespace(value=self.namespace, direction="ns_to_nv")
        dns_payload = {}
        dns_comment = attrs.get("description")
        if dns_comment:
            dns_payload["comment"] = dns_comment
        if attrs.get("dns_name"):
            # Nautobot side doesn't check if dns name is a FQDN. Additionally, Infoblox won't accept DNS name if the corresponding zone FQDN doesn't exist.
            if not validate_dns_name(self.diffsync.conn, attrs.get("dns_name"), network_view):
                self.diffsync.job.logger.warning(
                    f"Invalid zone fqdn in DNS name `{attrs.get('dns_name')}` for IP Address {self.address}."
                )
                return super().update(attrs)

            dns_payload["name"] = attrs.get("dns_name")

        if dns_payload:
            self.diffsync.conn.update_host_record(ref=self.ref, data=dns_payload)
            if self.diffsync.job.debug:
                self.diffsync.job.logger.debug(
                    "Updated Host record, address: %s, network_view: %s, update data: %s",
                    self.address,
                    network_view,
                    dns_payload,
                )

        return super().update(attrs)

    def delete(self):
        """Delete DNS Host record in Infoblox."""
        if InfobloxDeletableModelChoices.DNS_HOST_RECORD not in self.diffsync.config.infoblox_deletable_models:
            return super().delete()

        if self.diffsync.config.dns_record_type != DNSRecordTypeChoices.HOST_RECORD:
            return super().delete()

        network_view = map_network_view_to_namespace(value=self.namespace, direction="ns_to_nv")
        self.diffsync.conn.delete_host_record_by_ref(self.ref)
        self.diffsync.job.logger.info(
            "Deleted Host record in Infoblox, address: %s, network_view: %s",
            self.address,
            network_view,
        )
        return super().delete()


class InfobloxDnsPTRRecord(DnsPTRRecord):
    """Infoblox implementation of the DnsPTRRecord Model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create PTR record in Infoblox."""
        # DNS record not needed, we can return
        if diffsync.config.dns_record_type != DNSRecordTypeChoices.A_AND_PTR_RECORD:
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        network_view = map_network_view_to_namespace(value=ids["namespace"], direction="ns_to_nv")
        ip_address = ids["address"]
        dns_name = attrs.get("dns_name")
        dns_comment = attrs.get("description")
        if not dns_name:
            diffsync.job.logger.warning(
                f"Cannot create Infoblox PTR DNS record for IP Address {ip_address}. DNS name is not defined."
            )
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        # Nautobot side doesn't check if dns name is a FQDN. Additionally, Infoblox won't accept DNS name if the corresponding zone FQDN doesn't exist.
        if not validate_dns_name(diffsync.conn, dns_name, network_view):
            diffsync.job.logger.warning(f"Invalid zone fqdn in DNS name `{dns_name}` for IP Address {ip_address}.")
            return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

        diffsync.conn.create_ptr_record(dns_name, ip_address, dns_comment, network_view=network_view)
        if diffsync.job.debug:
            diffsync.job.logger.debug(
                "Created DNS PTR record, address: %s, dns_name: %s, network_view: %s, comment: %s",
                ip_address,
                dns_name,
                network_view,
                dns_comment,
            )

        return super().create(ids=ids, diffsync=diffsync, attrs=attrs)

    def update(self, attrs):
        """Update PTR record in Infoblox."""
        if not self.diffsync.config.dns_record_type == DNSRecordTypeChoices.A_AND_PTR_RECORD:
            return super().update(attrs)

        network_view = map_network_view_to_namespace(value=self.namespace, direction="ns_to_nv")
        dns_payload = {}
        dns_comment = attrs.get("description")
        if dns_comment:
            dns_payload["comment"] = dns_comment
        if attrs.get("dns_name"):
            # Nautobot side doesn't check if dns name is a FQDN. Additionally, Infoblox won't accept DNS name if the corresponding zone FQDN doesn't exist.
            if not validate_dns_name(self.diffsync.conn, attrs.get("dns_name"), network_view):
                self.diffsync.job.logger.warning(
                    f"Invalid zone fqdn in DNS name `{attrs.get('dns_name')}` for IP Address {self.address}."
                )
                return super().update(attrs)

            dns_payload["ptrdname"] = attrs.get("dns_name")

        if dns_payload:
            self.diffsync.conn.update_ptr_record(ref=self.ref, data=dns_payload)
            if self.diffsync.job.debug:
                self.diffsync.job.logger.debug(
                    "Updated PTR record, address: %s, network_view: %s, update data: %s",
                    self.address,
                    network_view,
                    dns_payload,
                )

        return super().update(attrs)

    def delete(self):
        """Delete PTR Record in Infoblox."""
        if InfobloxDeletableModelChoices.DNS_PTR_RECORD not in self.diffsync.config.infoblox_deletable_models:
            return super().delete()

        if not self.diffsync.config.dns_record_type == DNSRecordTypeChoices.A_AND_PTR_RECORD:
            return super().delete()

        network_view = map_network_view_to_namespace(value=self.namespace, direction="ns_to_nv")
        self.diffsync.conn.delete_ptr_record_by_ref(self.ref)
        self.diffsync.job.logger.info(
            "Deleted PTR record in Infoblox, address: %s, network_view: %s",
            self.address,
            network_view,
        )
        return super().delete()
