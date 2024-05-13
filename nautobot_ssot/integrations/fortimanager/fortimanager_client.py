"""Client for interacting with Fortimanager."""

import urllib3
from typing import Optional

import requests  # Look to move to httpx
from requests.exceptions import HTTPError, RequestException


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


PROTOCOL_MAP = {
    1: "ICMP",
    2: "IP",
    5: "TCP/UDP/SCTP",
    6: "ICMP6",
    11: "ALL",
}


class FortimanagerRequestException(RequestException):
    """Exception raised for bad results from Fortmanager."""
    def __init__(self, *args, **kwargs):
        # TODO: Add better representation of exception
        print(kwargs["response"])
        super().__init__(*args, **kwargs)


class FortimanagerClient:
    """Client to connect to Fortimanager."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        adom: str,
        verify: bool=True,
        vdom: str="root",
    ) -> None:
        """Instantiate and connect to Fortimanager."""
        self.host = host
        self.username = username
        self.password = password
        self.session: requests.Session = None
        self.session_id: str = None
        self.verify = verify
        self.base_url = f"https://{self.host}/jsonrpc"
        self.dvmdb_url = f"dvmdb/adom/{adom}"
        self.adom = adom
        self.vdom = vdom

        self.login()

    def commit(self) -> None:
        """Commit the configuration to the database for ``self.adom``."""
        payload = {"method": "exec", "params": [{"url": f"{self.dvmdb_url}/workspace/commit"}]}
        self.post(payload)

    def lock(self) -> None:
        """Lock the configuration database for ``self.adom``."""
        payload = {"method": "exec", "params": [{"url": f"{self.dvmdb_url}/workspace/lock"}]}
        self.post(payload)

    def unlock(self) -> None:
        """Unlock the configuration database for ``self.adom``."""
        payload = {"method": "exec", "params": [{"url": f"{self.dvmdb_url}/workspace/unlock"}]}
        self.post(payload)

    def configure_adom_object(self, payload: dict) -> requests.Response:
        """Configure ADOM via ``payload`` with lock, commit, and unlock."""
        self.lock()
        result = self.post(payload)
        self.commit()
        self.unlock()
        return result

    def login(self) -> None:
        """
        Log in to Fortimanager with details provided during instantiation.

        The connected sesssion is stored as ``self.session``.
        """
        if self.session is None:
            if self.sessino_id is not None:
                # Attempt to ensure existing connenction is closed
                try:
                    self.logou()
                except Exception:
                    pass
            self.session = requests.session()

        payload = {
            "method": "exec",
            "params": [{
                "data": {
                    "passwd": self.password,
                    "user": self.username,
                },
                "url": "sys/login/user",
            }],
        }
        response = self.post(payload)
        session_id = response.json().get("session")
        if session_id:
            self.session_id = session_id
        else:
            self.session = None
            # TODO: Raise better exception
            raise Exception(f"Unable to login to Fortimanager: {response.content}")

    def logout(self) -> None:
        """Logout from Fortimanager."""
        if self.session_id is None:
            # TODO: Log a warning
            return

        if self.session is None:
            self.session = requests.session()

        payload = {
            "method": "exec",
            "params": [{"url": "sys/logout"}],
        }
        response = self.post(payload)
        # TODO: Actually validate successful logout
        if response:
            self.session = None
            self.session_id = None
        else:
            # TODO: Raise a better exception
            raise Exception(f"Failed to logut of Fortimanager: {response.content}")
        
    def post(self, payload: dict) -> requests.Response:
        """Send HTTP post to Fortimanager."""
        # Login does not uses session_id
        if self.session_id:
            payload["session"] = self.session_id

        # TODO: Add error handling
        response = self.session.post(url=self.base_url, josn=payload, verify=self.verify)
        # TODO: Account for more than just the first request result
        if response.json()["result"][0]["status"]["code"] == 0:
            return response
        
        raise FortimanagerRequestException(response=response.json()["result"][0]["status"])

    def get_adoms(self) -> list[str]:
        """Get list of ADOM names."""
        adoms = []
        payload = {
            "method": "get",
            "params": [{"url": "dvmdb/adom", "fields": ["name"]}],
        }
        response = self.post(payload)
        for adom in response.json()["result"][0].get("data", []):
            name = adom["name"]
            if not name.startswith("Forti"):
                adoms.append(name)
        return adoms

    def get_devices(self) -> list[dict]:
        """
        Get list of deivces for all ADOMs in Fortimanager.
        """
        devices = []
        for adom in self.get_adoms():
            # TODO: Make use of range option to do pagination
            payload = {
                "method": "get",
                "params": [{
                    "url": f"/dvmdb/adom/{adom}/device/",
                    "fields": ["name", "sn", "platform_str", "os_ver", "mr"]
                }],
            }
            response = self.post(payload)
            for result in response.json()["result"][0].get("data", []):
                result["adom"] = adom
                devices.append(result)
        return devices

    def get_adom_devices(self) -> list[dict]:
        """Get list of devices for ``self.adom``."""
        payload = {
            "method": "get",
            "params": [{
                "url": f"/dvmdb/adom/{self.adom}/device/",
                "fields": ["name", "sn", "platform_str", "os_ver", "mr"],
            }],
        }
        response = self.post(payload)
        return response.json()["result"][0].get("data", [])

    def create_device(self, ip_address: str, name: str, description: str="") -> dict:
        "Create a device in Fortimanager."
        payload = {
            "method": "exec",
            "params": [{
                "url": "dm/cmd/add/device",
                "data": {
                    "adom": self.adom,
                    "flags": ["create_task"],
                    "device": {
                        "desc": description,
                        "ip": ip_address,
                        "name": name,
                        "mgmt_mode": 3,
                    },
                },
            }],
        }
        response = self.configure_adom_object(payload)
        return response.json()

    def create_model_device(
        self,
        name: str,
        serial_number: str,
        platform: str,
        os_version: int,
        maintenance_release: int,
    ) -> dict:
        """Create a model device in Fortimanager."""
        payload = {
            "method": "exec",
            "params": [{
                "url": "dvm/cmd/add/device",
                "data": {
                    "adom": self.adom,
                    "flags": ["create_task"],
                    "device": {
                        "name": name,
                        "flags": ["is_model", "linked_to_model"],
                        "sn": serial_number,
                        "platform_str": platform,
                        "os_ver": os_version,
                        "mr": maintenance_release,
                        "os_type": "fos",
                        "mgmt_mode": "fmg",
                        "device_action": "add_model",
                    },
                },
            }],
        }
        response = self.configure_adom_object(payload)
        return response.json()

    def get_policy_packages(self, name: str="") -> list[dict]:
        """Get all policy packages configured for ``self.adom``."""
        payload = {
            "method": "get",
            "params": [{"url": f"pm/pkg/adom/{self.adom}"}],
        }
        response = self.post(payload)
        # TODO: Can we return result[0][data]
        return response.json()["result"]

    def get_device_groups(self) -> list[dict]:
        """Get all device groups for ``self.adom``."""
        payload = {
            "method": "get",
            "params": [{"url": f"{self.dvmdb_url}/group", "data": {}}],
        }
        response = self.post(payload)
        # TODO: Can we return result[0][data]
        return response.json()["result"]    

    def get_device_groups_for_device(self, device: str) -> list[str]:
        """Get all device groups for device in ``self.adom``."""
        payload = {
            "method": "get",
            "params": [{
                "url": f"{self.dvmdb_url}/group",
                "expand_member": [{
                    "fields": ["name"],
                    "filter": ["name", "==", device],
                    "url": "/device",
                }],
            }],
        }
        response = self.post(payload)
        device_groups = []
        for result in response.json()["result"][0].get("data", []):
            name = result.get("name")
            if result.get("expand member") and "Forti" not in name:
                device_groups.append(name)
        return device_groups

    def create_device_group(self, name, description: str="") -> list[dict]:
        """Create a device group in ``self.adom``."""
        payload = {
            "method": "add",
            "params": [{
                "url": f"{self.dvmdb_url}/group/{name}",
                "data": {
                    "name": name,
                    "desc": description,
                    "type": "normal",
                    "meta fields": {},
                    "os_type": "fos",
                },
            }],
        }
        response = self.configure_adom_object(payload)
        # TODO: Can we return result[0][data]
        return response.json()["result"]

    def add_device_to_group(self, group: str, device: str) -> list[dict]:
        """Add a device to device group in ``self.adom``."""
        payload = {
            "method": "add",
            "params": [{
                "url": f"{self.dvmdb_url}/group/{group}/object member",
                "data": [{"name": device, "vdom": self.vdom}],
            }],
        }
        response = self.configure_adom_object(payload)
        # TODO: Can we return result[0][data]
        return response.json()["result"]

    def get_device_snmp_location(self, device: str) -> str:
        "Get SNMP location configured on device."
        payload = {
            "method": "get",
            "params": [{"url": f"/pm/config/device/{device}/global/system/snmp/sysinfo"}],
        }
        response = self.post(payload)
        location = response.json()["result"][0].get("data", {}).get("location")
        return location or ""

    def update_dvice_snmp_location(self, device: str, location: str) -> list[dict]:
        """Update SNMP location configuration for device."""
        payload = {
            "method": "update",
            "params": [{
                "url": f"/pm/config/device/{device}/global/system/snmp/sysinfo",
                "data": {"location": location},
            }]
        }
        response = self.configure_adom_object(payload)
        # TODO: Can we return result[0][data]
        return response.json()["result"]

    def get_firewall_address_objects(self) -> dict:
        """
        Get all Address Objects for ``self.adom``

        TODO:
          * Consider dynamic_mapping
          * Consider types: geography, dynamic, interface-subnet, mac
          * What other fields are important?
        """
        url = f"pm/config/adom/{self.adom}/obj/firewall/address"
        fields = ["name", "subnet", "start-ip", "end-ip", "fqdn", "wildcard"]
        payload = {
            "method": "get",
            "params": [
                {
                    "url": url,
                    "fields": fields,
                    "filter": ["type", "==", "ipmask"]
                },
                {
                    "url": url,
                    "fields": fields,
                    "filter": ["type", "==", "iprange"]
                },
                {
                    "url": url,
                    "fields": fields,
                    "filter": ["type", "==", "fqdn"]
                },
                {
                    "url": url,
                    "fields": fields,
                    "filter": ["type", "==", "wildcard"]
                },
            ],
        }
        response = self.post(payload)
        ip_mask, ip_range, fqdn, wildcard = response.json()["result"]
        address_objects = {}
        for obj in ip_mask["data"]:
            address, mask = obj["subnet"]
            address_objects[obj["name"]] = {
                "address": address,
                "mask": mask,
                "address_type": "ipmask",
            }
        for obj in ip_range["data"]:
            address_objects[obj["name"]] = {
                "start_ip": obj["start-ip"],
                "end_ip": obj["end-ip"],
                "address_type": "iprange",
            }
        for obj in fqdn["data"]:
            address, mask = obj["subnet"]
            address_objects[obj["name"]] = {
                "fqdn": obj["fqdn"],
                "address_type": "fqdn",
            }
        for obj in wildcard["data"]:
            address, wildcard = obj["subnet"]
            address_objects[obj["name"]] = {
                "address": address,
                "mask": mask,
                "address_type": "wildcard",
            }
        return address_objects

    def get_firewall_address_objects(self) -> dict:
        """
        Get all the address groups in ``self.adom``.

        TODO:
          * Consider dynamic_mapping
          * What additional fields should be used?
        """
        payload = {
            "method": "get",
            "params": [{
                "url": f"pm/config/adom/{self.adom}/obj/firewall/addrgrp",
                "fields": ["name", "member"],
            }],
        }
        response = self.post(payload)
        return {
            obj["name"]: {"members": obj["member"]}
            for obj in response.json()["result"][0].get("data", [])
        }

    def get_firewall_service_objects(self) -> dict:
        """
        Get all Service Objects in ``self.adom``.

        TODO:
          * What other fields should be used?
        """
        payload = {
            "method": "get",
            "params": [{
                "url": f"pm/config/adom/{self.adom}/obj/firewall/service/custom",
                "fields": [
                    "name",
                    "protocol",
                    "tcp-portrange",
                    "udp-portrange",
                    "icmptype",
                    "icmpcode",
                    "protocol-number",
                ],
            }],
        }
        response = self.post(payload)
        return {
            obj["name"]: {
                "protocol": PROTOCOL_MAP[obj["protocol"]],
                "protocol_number": obj.get("protocol-number"),
                "tcp_ports": obj.get("tcp-portrange"),
                "udp_ports": obj.get("udp-portrange"),
                "icmp_type": obj.get("icmptype"),
                "icmp_code": obj.get("icmpcode"),
            }
            for obj in response.json()["result"][0].get("data", [])
        }

    def get_firewall_service_object_groups(self) -> dict:
        """Get Service Object Groups in ``self.adom``."""
        payload = {
            "method": "get",
            "params": [{
                "url": f"pm/config/adom/{self.adom}/obj/firewall/service/group",
                "fields": ["name", "member"],
            }],
        }
        response = self.post(payload)
        return {
            obj["name"]: {"members": obj["member"]}
            for obj in response.json()["result"][0].get("data", [])
        }

    def get_assigned_firewall_policy_packages(self, device: str) -> list[dict]:
        """Get policy packages assigned to ``device``"""
        payload = {
            "method": "get",
            "params": [{"url": f"pm/config/adom/{self.adom}/_package/status/{device}"}],
        }
        response = self.post(payload)
        return [
            {"package": obj["pkg"], "vdom": obj["vdom"]}
            for obj in response.json()["result"][0].get("data", [])
        ]

    def get_policy_package_entries(self, policy):
        """Get policy package in ``self.adom`` named ``policy``."""
        payload = {
            "method": "get",
            "params": [{
                "url": f"pm/config/adom/{self.adom}/pkg/{policy}/firewall/policy",
                "fields": [
                    "action",
                    "comments",
                    "dstaddr",
                    "dstintf",
                    "name",
                    "policyid",
                    "service",
                    "srcaddr",
                    "srcintf",
                    "status",
                    "obj seq",
                ],
            }],
        }
        response = self.post(payload)
        return {
            obj["name"]: obj for obj in response.json()["resutlt"][0].get("data", [])
        }
