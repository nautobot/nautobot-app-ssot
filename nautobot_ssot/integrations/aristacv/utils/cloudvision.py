# pylint: disable=invalid-name, no-member
"""Utility functions for CloudVision Resource API."""
import ssl
from datetime import datetime
from typing import Any, Iterable, List, Optional, Tuple, Union
from urllib.parse import urlparse

import google.protobuf.timestamp_pb2 as pbts
import grpc
import requests
from arista.inventory.v1 import models, services
from arista.tag.v2 import models as tag_models
from arista.tag.v2 import services as tag_services

from google.protobuf.wrappers_pb2 import StringValue  # pylint: disable=no-name-in-module

from cvprac.cvp_client import CvpClient
from cvprac.cvp_client import CvpLoginError
import cloudvision.Connector.gen.notification_pb2 as ntf
import cloudvision.Connector.gen.router_pb2 as rtr
import cloudvision.Connector.gen.router_pb2_grpc as rtr_client
from cloudvision.Connector import codec
from cloudvision.Connector.codec import Wildcard
from cloudvision.Connector.codec.custom_types import FrozenDict
from cloudvision.Connector.grpc_client.grpcClient import create_query, to_pbts

from nautobot_ssot.integrations.aristacv.constants import PORT_TYPE_MAP
from nautobot_ssot.integrations.aristacv.types import CloudVisionAppConfig

RPC_TIMEOUT = 30
TIME_TYPE = Union[pbts.Timestamp, datetime]
UPDATE_TYPE = Tuple[Any, Any]
UPDATES_TYPE = List[UPDATE_TYPE]


class AuthFailure(Exception):
    """Exception raised when authenticating to on-prem CVP fails."""

    def __init__(self, error_code, message):
        """Populate exception information."""
        self.expression = error_code
        self.message = message
        super().__init__(self.message)


class CloudvisionApi:  # pylint: disable=too-many-instance-attributes, too-many-arguments
    """Arista CloudVision gRPC client."""

    AUTH_KEY_PATH = "access_token"

    def __init__(self, config: CloudVisionAppConfig):
        """Create CloudVision API connection."""
        self.metadata = None

        parsed_url = urlparse(config.url)
        if not parsed_url.hostname or not parsed_url.port:
            raise ValueError("Invalid URL provided for CloudVision")
        token = config.token
        if config.is_on_premise:
            if config.verify_ssl:
                channel_creds = grpc.ssl_channel_credentials()
            else:
                channel_creds = grpc.ssl_channel_credentials(
                    bytes(ssl.get_server_certificate((parsed_url.hostname, parsed_url.port)), "utf-8")
                )
            if token:
                call_creds = grpc.access_token_call_credentials(token)
            elif config.cvp_user != "" and config.cvp_password != "":  # nosec
                response = requests.post(  # nosec
                    f"{parsed_url.hostname}:{parsed_url.port}/cvpservice/login/authenticate.do",
                    auth=(config.cvp_user, config.cvp_password),
                    timeout=60,
                    verify=config.verify_ssl,
                )
                session_id = response.json().get("sessionId")
                if not session_id:
                    error_code = response.json().get("errorCode")
                    error_message = response.json().get("errorMessage")
                    raise AuthFailure(error_code, error_message)
                token = session_id
                call_creds = grpc.access_token_call_credentials(session_id)
            else:
                raise AuthFailure(
                    error_code="Missing Credentials", message="Unable to authenticate due to missing credentials."
                )
            self.metadata = ((self.AUTH_KEY_PATH, token),)
        else:
            call_creds = grpc.access_token_call_credentials(token)
            channel_creds = grpc.ssl_channel_credentials()
        conn_creds = grpc.composite_channel_credentials(channel_creds, call_creds)
        self.comm_channel = grpc.secure_channel(f"{parsed_url.hostname}:{parsed_url.port}", conn_creds)
        self.__client = rtr_client.RouterV1Stub(self.comm_channel)
        self.__auth_client = rtr_client.AuthStub(self.comm_channel)
        self.__search_client = rtr_client.SearchStub(self.comm_channel)
        self.encoder = codec.Encoder()
        self.decoder = codec.Decoder()

    def __enter__(self):
        """Magic method to enable use of class with `with` statement."""
        return self

    def __exit__(self, exit_type, value, traceback):
        """Magic method for exiting context manager when using with `with` statement."""
        return self.comm_channel.__exit__(exit_type, value, traceback)

    def close(self):
        """Close the shared gRPC channel."""
        self.comm_channel.close()

    def get(
        self,
        queries: List[rtr.Query],
        start: Optional[TIME_TYPE] = None,
        end: Optional[TIME_TYPE] = None,
        versions=0,
        sharding=None,
        exact_range=False,
    ):
        """Get creates and executes a Get protobuf message, returning a stream of notificationBatch.

        queries must be a list of query protobuf messages.
        start and end, if present, must be nanoseconds timestamps (uint64).
        sharding, if present must be a protobuf sharding message.
        """
        end_ts = 0
        start_ts = 0
        if end:
            end_ts = to_pbts(end).ToNanoseconds()

        if start:
            start_ts = to_pbts(start).ToNanoseconds()

        request = rtr.GetRequest(
            query=queries,
            start=start_ts,
            end=end_ts,
            versions=versions,
            sharded_sub=sharding,
            exact_range=exact_range,
        )
        stream = self.__client.Get(request, metadata=self.metadata)
        return (self.decode_batch(nb) for nb in stream)

    def subscribe(self, queries, sharding=None):
        """Subscribe creates and executes a Subscribe protobuf message, returning a stream of notificationBatch.

        queries must be a list of query protobuf messages.
        sharding, if present must be a protobuf sharding message.
        """
        req = rtr.SubscribeRequest(query=queries, sharded_sub=sharding)
        stream = self.__client.Subscribe(req, metadata=self.metadata)
        return (self.decode_batch(nb) for nb in stream)

    def publish(
        self,
        dId,
        notifs: List[ntf.Notification],
        dtype: str = "device",
        sync: bool = True,
        compare: Optional[UPDATE_TYPE] = None,
    ) -> None:
        """Publish creates and executes a Publish protobuf message.

        refer to cloudvision/Connector/protobufs/router.proto:124
        default to sync publish being true so that changes are reflected
        """
        comp_pb = None
        if compare:
            key = compare[0]
            value = compare[1]
            comp_pb = ntf.Notification.Update(key=self.encoder.encode(key), value=self.encoder.encode(value))

        req = rtr.PublishRequest(
            batch=ntf.NotificationBatch(d="device", dataset=ntf.Dataset(type=dtype, name=dId), notifications=notifs),
            sync=sync,
            compare=comp_pb,
        )
        self.__client.Publish(req, metadata=self.metadata)

    def get_datasets(self, types: Optional[List[str]] = None):
        """Get Datasets retrieves all the datasets streaming on CloudVision.

        types, if present, filter the queried dataset by types
        """
        req = rtr.DatasetsRequest(types=types)
        stream = self.__client.GetDatasets(req, metadata=self.metadata)
        return stream

    def create_dataset(self, dtype, dId) -> None:
        """Create Datasets will create a dataset request on CloudVision."""
        req = rtr.CreateDatasetRequest(dataset=ntf.Dataset(type=dtype, name=dId))
        self.__auth_client.CreateDataset(req, metadata=self.metadata)

    def decode_batch(self, batch):
        """Decode a batch of notifications from CloudVision."""
        res = {
            "dataset": {"name": batch.dataset.name, "type": batch.dataset.type},
            "notifications": [self.decode_notification(n) for n in batch.notifications],
        }
        return res

    def decode_notification(self, notif):
        """Decode notifications into standardize format."""
        res = {
            "timestamp": notif.timestamp,
            "deletes": [self.decoder.decode(d) for d in notif.deletes],
            "updates": {self.decoder.decode(u.key): self.decoder.decode(u.value) for u in notif.updates},
            "retracts": [self.decoder.decode(r) for r in notif.retracts],
            "path_elements": [self.decoder.decode(elt) for elt in notif.path_elements],
        }
        return res

    def search(  # pylint:disable=dangerous-default-value, too-many-locals
        self,
        search_type=rtr.SearchRequest.CUSTOM,
        d_type: str = "device",
        d_name: str = "",
        result_size: int = 1,
        start: Optional[TIME_TYPE] = None,
        end: Optional[TIME_TYPE] = None,
        path_elements=[],
        key_filters: Iterable[rtr.Filter] = [],
        value_filters: Iterable[rtr.Filter] = [],
        exact_range: bool = False,
        offset: int = 0,
        exact_term: bool = False,
        sort: Iterable[rtr.Sort] = [],
        count_only: bool = False,
    ):
        """Format a search request to CloudVision."""
        start_ts = to_pbts(start).ToNanoseconds() if start else 0
        end_ts = to_pbts(end).ToNanoseconds() if end else 0
        encoded_path_elements = [self.encoder.encode(x) for x in path_elements]
        req = rtr.SearchRequest(
            search_type=search_type,
            start=start_ts,
            end=end_ts,
            query=[
                rtr.Query(
                    dataset=ntf.Dataset(type=d_type, name=d_name), paths=[rtr.Path(path_elements=encoded_path_elements)]
                )
            ],
            result_size=result_size,
            key_filters=key_filters,
            value_filters=value_filters,
            exact_range=exact_range,
            offset=offset,
            exact_term=exact_term,
            sort=sort,
            count_only=count_only,
        )
        res = self.__search_client.Search(req)
        return (self.decode_batch(nb) for nb in res)


def get_devices(client, import_active: bool):
    """Get devices from CloudVision inventory."""
    device_stub = services.DeviceServiceStub(client)
    if import_active:
        req = services.DeviceStreamRequest(
            partial_eq_filter=[models.Device(streaming_status=models.STREAMING_STATUS_ACTIVE)]
        )
    else:
        req = services.DeviceStreamRequest()
    responses = device_stub.GetAll(req)
    devices = []
    for resp in responses:
        device = {
            "device_id": resp.value.key.device_id.value,
            "hostname": resp.value.hostname.value,
            "fqdn": resp.value.fqdn.value,
            "sw_ver": resp.value.software_version.value,
            "model": resp.value.model_name.value,
            "status": "Active" if resp.value.streaming_status == 2 else "Offline",
            "system_mac_address": resp.value.system_mac_address.value,
        }
        devices.append(device)
    return devices


def get_tags_by_type(client, creator_type: int = tag_models.CREATOR_TYPE_USER):
    """Get tags by creator type from CloudVision."""
    tag_stub = tag_services.TagServiceStub(client)
    req = tag_services.TagStreamRequest(partial_eq_filter=[tag_models.Tag(creator_type=creator_type)])
    responses = tag_stub.GetAll(req)
    tags = []
    for resp in responses:
        dev_tag = {
            "label": resp.value.key.label.value,
            "value": resp.value.key.value.value,
        }
        tags.append(dev_tag)
    return tags


# credit to @Eric-Jckson in https://github.com/nautobot/nautobot-plugin-ssot-arista-cloudvision/pull/164 for update to get_device_tags()
def get_device_tags(client, device_id: str):
    """Get tags for specific device."""
    tag_stub = tag_services.TagAssignmentServiceStub(client)
    req = tag_services.TagAssignmentConfigStreamRequest(
        partial_eq_filter=[
            tag_models.TagAssignmentConfig(
                key=tag_models.TagAssignmentKey(
                    device_id=StringValue(value=device_id),
                    element_type=tag_models.ELEMENT_TYPE_DEVICE,
                    workspace_id=StringValue(value=""),
                )
            )
        ]
    )
    responses = tag_stub.GetAll(req)
    tags = []
    for resp in responses:
        dev_tag = {
            "label": resp.value.key.label.value,
            "value": resp.value.key.value.value,
        }
        tags.append(dev_tag)
    return tags


def create_tag(client, label: str, value: str):
    """Create user-defined tag in CloudVision."""
    tag_stub = tag_services.TagConfigServiceStub(client)
    req = tag_services.TagConfigSetRequest(
        value=tag_models.TagConfig(
            key=tag_models.TagKey(label=StringValue(value=label), value=StringValue(value=value))
        )
    )
    try:
        tag_stub.Set(req)
    except grpc.RpcError as err:
        # Ignore RPC error if tag already exists for idempotency
        print(f"Failure to create tag: {err}")
        raise err


def delete_tag(client, label: str, value: str):
    """Delete user-defined tag in CloudVision."""
    tag_stub = tag_services.TagConfigServiceStub(client)
    req = tag_services.TagConfigDeleteRequest(
        key=tag_models.TagKey(label=StringValue(value=label), value=StringValue(value=value))
    )
    try:
        tag_stub.Delete(req)
    # Skip error of tags that may be assigned to devices manually in CloudVision
    except grpc.RpcError as err:
        print(f"Failure to delete tag: {err}")
        raise err


def assign_tag_to_device(client, device_id: str, label: str, value: str):
    """Assign user-defined tag to device in CloudVision."""
    tag_stub = tag_services.TagAssignmentConfigServiceStub(client)
    req = tag_services.TagAssignmentConfigSetRequest(
        value=tag_models.TagAssignmentConfig(
            key=tag_models.TagAssignmentKey(
                label=StringValue(value=label),
                value=StringValue(value=value),
                device_id=StringValue(value=device_id),
            )
        )
    )
    tag_stub.Set(req)


def remove_tag_from_device(client, device_id: str, label: str, value: str):
    """Unassign a tag from a device in CloudVision."""
    tag_stub = tag_services.TagAssignmentConfigServiceStub(client)
    req = tag_services.TagAssignmentConfigDeleteRequest(
        key=tag_models.TagAssignmentKey(
            label=StringValue(value=label),
            value=StringValue(value=value),
            device_id=StringValue(value=device_id),
        )
    )
    tag_stub.Delete(req, timeout=RPC_TIMEOUT)


# This section is based off example code from Arista: https://github.com/aristanetworks/cloudvision-python/blob/trunk/examples/Connector/get_intf_status.py


def get_query(client, dataset, pathElts):
    """Returns a query on a path element.

    Args:
        client (obj): GRPC client connection.
        dataset (dict): Data related to query.
        pathElts (List[str]): List of strings denoting path elements for query.

    Returns:
        dict: Query from dataset and path elements.
    """
    result = {}
    query = [create_query([(pathElts, [])], dataset)]

    for batch in client.get(query):
        for notif in batch["notifications"]:
            result.update(notif["updates"])
    return result


def unfreeze_frozen_dict(frozen_dict):
    """Used to unfreeze Frozen dictionaries.

    Args:
        frozen_dict (FrozenDict|dict|str): Potentially frozen dict to be unfrozen.

    Returns:
        dict|str|list: Unfrozen contents of FrozenDict that was passed in.
    """
    if isinstance(frozen_dict, (dict, FrozenDict)):
        return {k: unfreeze_frozen_dict(v) for k, v in frozen_dict.items()}

    if isinstance(frozen_dict, (str)):
        return frozen_dict

    try:
        return [unfreeze_frozen_dict(i) for i in frozen_dict]
    except TypeError:
        pass

    return frozen_dict


def get_device_type(client: CloudvisionApi, dId: str):
    """Returns the type of the device: modular/fixed.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to determine type for.

    Returns:
        str: Type of device, either modular or fixed.
    """
    pathElts = ["Sysdb", "hardware", "entmib"]
    query = get_query(client, dId, pathElts)
    query = unfreeze_frozen_dict(query)
    if "fixedSystem" in query and query["fixedSystem"] is None:
        dType = "modular"
    elif query.get("fixedSystem"):
        dType = "fixedSystem"
    else:
        dType = "Unknown"
    return dType


def get_interfaces_chassis(client: CloudvisionApi, dId):
    """Gets information about interfaces for a modular device.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to determine type for.
    """
    # Fetch the list of slices/linecards
    pathElts = ["Sysdb", "interface", "status", "eth", "phy", "slice"]
    dataset = dId
    query = get_query(client, dataset, pathElts)
    queryLC = unfreeze_frozen_dict(query).keys()
    intfStatusChassis = []

    # Go through each linecard and get the state of all interfaces
    for lc in queryLC:
        pathElts = ["Sysdb", "interface", "status", "eth", "phy", "slice", lc, "intfStatus", Wildcard()]

        query = [create_query([(pathElts, [])], dataset)]

        for interface in client.get(query):
            new_intf = {}
            for notif in interface["notifications"]:
                results = notif["updates"]
                if results.get("intfId"):
                    new_intf["interface"] = results["intfId"]
                if results.get("linkStatus"):
                    new_intf["link_status"] = "up" if results["linkStatus"]["Name"] == "linkUp" else "down"
                if results.get("operStatus"):
                    new_intf["oper_status"] = "up" if results["operStatus"]["Name"] == "intfOperUp" else "down"
                if results.get("enabledState"):
                    new_intf["enabled"] = bool(results["enabledState"]["Name"] == "enabled")
                if results.get("burnedInAddr"):
                    new_intf["mac_addr"] = results["burnedInAddr"]
                if results.get("mtu"):
                    new_intf["mtu"] = results["mtu"]
            intfStatusChassis.append(new_intf)
    return intfStatusChassis


def get_interfaces_fixed(client: CloudvisionApi, dId: str):
    """Gets information about interfaces for a fixed system device.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to determine type for.
    """
    pathElts = ["Sysdb", "interface", "status", "eth", "phy", "slice", "1", "intfStatus", Wildcard()]
    query = [create_query([(pathElts, [])], dId)]
    query = unfreeze_frozen_dict(query)

    intfStatusFixed = []
    for interface in client.get(query):
        new_intf = {}
        for notif in interface["notifications"]:
            results = notif["updates"]
            if results.get("intfId"):
                new_intf["interface"] = results["intfId"]
            if results.get("enabledState"):
                new_intf["enabled"] = bool(results["enabledState"]["Name"] == "enabled")
            if results.get("burnedInAddr"):
                new_intf["mac_addr"] = results["burnedInAddr"]
            if results.get("mtu"):
                new_intf["mtu"] = results["mtu"]
            if results.get("operStatus"):
                new_intf["oper_status"] = "up" if results["operStatus"]["Name"] == "intfOperUp" else "down"
            if results.get("linkStatus"):
                new_intf["link_status"] = "up" if results["linkStatus"]["Name"] == "linkUp" else "down"
        intfStatusFixed.append(new_intf)
    return intfStatusFixed


def get_interface_transceiver(client: CloudvisionApi, dId: str, interface: str):
    """Gets transceiver information for specified interface on specific device.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to determine transceiver type for.
        interface (str): Name of interface to get transceiver information for.
    """
    pathElts = ["Sysdb", "hardware", "archer", "xcvr", "status", "all", interface]
    query = [create_query([(pathElts, [])], dId)]
    query = unfreeze_frozen_dict(query)

    for batch in client.get(query):
        for notif in batch["notifications"]:
            if notif["updates"].get("actualIdEepromContents") and notif["updates"]["actualIdEepromContents"].get(
                "mediaType"
            ):
                return notif["updates"]["actualIdEepromContents"]["mediaType"]
            if notif["updates"].get("mediaType"):
                return notif["updates"]["mediaType"]["Name"]
            if notif["updates"].get("localMediaType"):
                return notif["updates"]["localMediaType"]["Name"]
    return "Unknown"


def get_interface_mode(client: CloudvisionApi, dId: str, interface: str):
    """Gets interface mode, ie access/trunked.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to determine type for.
        interface (str): Name of interface to get mode information for.
    """
    pathElts = ["Sysdb", "bridging", "switchIntfConfig", "switchIntfConfig", interface]
    query = [create_query([(pathElts, [])], dId)]
    query = unfreeze_frozen_dict(query)

    for batch in client.get(query):
        for notif in batch["notifications"]:
            if notif["updates"].get("switchportMode"):
                return notif["updates"]["switchportMode"]["Name"]
    return "Unknown"


def get_port_type(port_info: dict, transceiver: str) -> str:
    """Returns the type of port mapping CVP to Nautobot.

    This attempts to determine what the port type is by looking at transceiver or speed.

    Args:
        port_info (dict): Data required to determine the port type.

    Returns:
        str: The Nautobot string for port type.
    """
    if transceiver != "Unknown" and transceiver in PORT_TYPE_MAP:
        return PORT_TYPE_MAP[transceiver]

    if port_info.get("interface") and "Management" in port_info["interface"]:
        return "1000base-t"

    if port_info.get("interface") and ("Vlan" in port_info["interface"] or "Loopback" in port_info["interface"]):
        return "virtual"

    if port_info.get("interface") and "Port-Channel" in port_info["interface"]:
        return "lag"

    return "other"


def get_interface_status(port_info: dict) -> str:
    """Returns the status of Interface based on link and operational status.

    Args:
        port_info (dict): Information about port including link and operational status.

    Returns:
        str: The status of a port: active|decommissioned|maintenance|planned.
    """
    status = "Decommissioning"
    if port_info["oper_status"] == "up" and port_info["link_status"] == "up":
        status = "Active"

    if port_info["oper_status"] == "up" and port_info["link_status"] == "down":
        status = "Planned"

    if port_info["oper_status"] == "down" and port_info["link_status"] == "down":
        status = "Maintenance"
    return status


def get_interface_description(client: CloudvisionApi, dId: str, interface: str):
    """Gets interface description.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to get description for.
        interface (str): Name of interface to get description for.
    """
    pathElts = ["Sysdb", "interface", "config", "eth", "phy", "slice", "1", "intfConfig", interface]
    query = [create_query([(pathElts, [])], dId)]
    query = unfreeze_frozen_dict(query)

    for batch in client.get(query):
        for notif in batch["notifications"]:
            if notif["updates"].get("description") and notif["updates"]["description"] is not None:
                return notif["updates"]["description"]
    return ""


def get_interface_vrf(client: CloudvisionApi, dId: str, interface: str) -> str:
    """Gets interface VRF.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to determine type for.
        interface (str): Name of interface to get mode information for.
    """
    pathElts = ["Sysdb", "l3", "intf", "config", "intfConfig", interface]
    query = [create_query([(pathElts, [])], dId)]
    query = unfreeze_frozen_dict(query)

    for batch in client.get(query):
        for notif in batch["notifications"]:
            if notif["updates"].get("vrf"):
                return notif["updates"]["vrf"]["value"]
    return "Global"


def get_ip_interfaces(client: CloudvisionApi, dId: str):
    """Gets interfaces with IP Addresses configured from specified device.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to retrieve IP Addresses and associated interfaces for.
    """
    pathElts = ["Sysdb", "ip", "config", "ipIntfConfig", Wildcard()]
    query = [create_query([(pathElts, [])], dId)]
    query = unfreeze_frozen_dict(query)

    ip_intfs = []
    for batch in client.get(query):
        for notif in batch["notifications"]:
            results = notif["updates"]
            if results.get("intfId") and results.get("addrWithMask"):
                ip_intfs.append(
                    {
                        "interface": results["intfId"],
                        "address": (
                            results["addrWithMask"]
                            if results["addrWithMask"] != "0.0.0.0/0"
                            else results.get("virtualAddrWithMask")
                        ),
                    }
                )
    return ip_intfs


def get_cvp_version(config: CloudVisionAppConfig):
    """Returns CloudVision portal version.

    Returns:
        str: CloudVision version from API or blank string if unable to find.
    """
    client = CvpClient()
    try:
        if config.token and not config.is_on_premise:
            client.connect(
                nodes=[config.url],
                username="",
                password="",  # nosec: B106
                is_cvaas=True,
                api_token=config.token,
            )
        else:
            client.connect(
                nodes=[config.url],
                username=config.cvp_user,
                password=config.cvp_password,
                is_cvaas=False,
            )
    except CvpLoginError as err:
        raise AuthFailure(error_code="Failed Login", message=f"Unable to login to CloudVision Portal. {err}") from err
    version = client.api.get_cvp_info()
    if "version" in version:
        return version["version"]
    return ""
