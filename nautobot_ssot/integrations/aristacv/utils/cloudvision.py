# pylint: disable=invalid-name, no-member
"""Utility functions for CloudVision Resource API."""

import ssl
import warnings
from datetime import datetime
from typing import Any, Iterable, List, Optional, Tuple, Union
from urllib.parse import urlparse

import cloudvision.Connector.gen.notification_pb2 as ntf
import cloudvision.Connector.gen.router_pb2 as rtr
import cloudvision.Connector.gen.router_pb2_grpc as rtr_client
import google.protobuf.timestamp_pb2 as pbts
import grpc
import requests
from arista.inventory.v1 import models, services
from arista.tag.v2 import models as tag_models
from arista.tag.v2 import services as tag_services
from cloudvision.Connector import codec
from cloudvision.Connector.codec import Wildcard
from cloudvision.Connector.codec.custom_types import FrozenDict, Path
from cloudvision.Connector.grpc_client.grpcClient import create_query, to_pbts
from cvprac.cvp_client import CvpClient, CvpLoginError
from google.protobuf.wrappers_pb2 import StringValue  # pylint: disable=no-name-in-module

from nautobot_ssot.exceptions import AuthFailure
from nautobot_ssot.integrations.aristacv.constants import PORT_TYPE_MAP
from nautobot_ssot.integrations.aristacv.types import CloudVisionAppConfig

RPC_TIMEOUT = 30
TIME_TYPE = Union[pbts.Timestamp, datetime]
UPDATE_TYPE = Tuple[Any, Any]
UPDATES_TYPE = List[UPDATE_TYPE]


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
        if config.verify_ssl:
            channel_creds = grpc.ssl_channel_credentials()
        else:
            channel_creds = grpc.ssl_channel_credentials(
                bytes(ssl.get_server_certificate((parsed_url.hostname, parsed_url.port)), "utf-8")
            )
        if config.is_on_premise:
            if token:
                call_creds = grpc.access_token_call_credentials(token)
            elif config.cvp_user != "" and config.cvp_password != "":
                response = requests.post(
                    f"{parsed_url.scheme}://{parsed_url.hostname}:{parsed_url.port}/cvpservice/login/authenticate.do",
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
        conn_creds = grpc.composite_channel_credentials(channel_creds, call_creds)
        self.comm_channel = grpc.secure_channel(f"{parsed_url.hostname}:{parsed_url.port}", conn_creds)
        self.__client = rtr_client.RouterV1Stub(self.comm_channel)
        self.__auth_client = rtr_client.AuthStub(self.comm_channel)
        self.__search_client = rtr_client.SearchStub(self.comm_channel)
        self.encoder = codec.Encoder()
        self.decoder = codec.Decoder()
        self.cvpclient = self._connect_rest_client(config)

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

    def _connect_rest_client(self, config: CloudVisionAppConfig) -> CvpClient:
        """Build and connect a cvprac REST client using the shared CloudVision app config."""
        client = CvpClient()
        parsed_url = urlparse(config.url)
        if not parsed_url.hostname:
            raise ValueError(f"Invalid URL provided for CloudVision. {config.url}")
        try:
            if config.token and not config.is_on_premise:
                client.connect(
                    nodes=[parsed_url.hostname],
                    username="",
                    password="",
                    is_cvaas=True,
                    api_token=config.token,
                )
            else:
                client.connect(
                    nodes=[parsed_url.hostname],
                    username=config.cvp_user,
                    password=config.cvp_password,
                    is_cvaas=False,
                )
        except CvpLoginError as err:
            raise AuthFailure(
                error_code="Failed Login", message=f"Unable to login to CloudVision Portal. {err}"
            ) from err
        return client

    def get_version(self):
        """Return CloudVision portal version, or '' if absent."""
        return self.cvpclient.api.get_cvp_info().get("version", "")

    def get_inventory(self):
        """Return CloudVision device inventory."""
        return self.cvpclient.api.get_inventory()


def get_devices(client, logger, import_active: bool):
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
    try:
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
    except grpc.RpcError as err:
        logger.error(f"Error when pulling devices: {err}")
    return devices


def get_tags_by_type(client, logger, creator_type: int = tag_models.CREATOR_TYPE_USER):
    """Get tags by creator type from CloudVision."""
    tags = []
    try:
        tag_stub = tag_services.TagServiceStub(client)
        req = tag_services.TagStreamRequest(partial_eq_filter=[tag_models.Tag(creator_type=creator_type)])
        responses = tag_stub.GetAll(req)
        for resp in responses:
            dev_tag = {
                "label": resp.value.key.label.value,
                "value": resp.value.key.value.value,
            }
            if dev_tag not in tags:
                tags.append(dev_tag)
    except grpc.RpcError as err:
        logger.error(f"Error when pulling Tags: {err}")
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
        if dev_tag not in tags:
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


def unpath(data):
    """Recursively replace CloudVision ``Path`` objects with plain lists of their elements.

    Args:
        data: Any nested structure that may contain ``Path`` values.

    Returns:
        The same structure with each ``Path`` replaced by ``list(path._keys)``.
    """
    if isinstance(data, Path):
        return list(data._keys)  # pylint: disable=protected-access
    if isinstance(data, (dict, FrozenDict)):
        return {k: unpath(v) for k, v in data.items()}
    if isinstance(data, str):
        return data
    if isinstance(data, (list, tuple)):
        return [unpath(item) for item in data]
    return data


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

    # Group notifications by the interface name from the path elements. CloudVision may stream an
    # interface's attributes across multiple frames, and a frame carrying state may not contain intfId, so
    # anchoring on the path element and merging keeps those frames from being lost. Interface names
    # are unique across linecards, so a single accumulator spans all of them.
    per_intf = {}
    for lc in queryLC:
        pathElts = ["Sysdb", "interface", "status", "eth", "phy", "slice", lc, "intfStatus", Wildcard()]

        for batch in clean_query_results(pathElts, client, dataset):
            for notif in batch["notifications"]:
                intf_name = notif["path_elements"][-1]
                entry = per_intf.setdefault(intf_name, {"interface": intf_name})
                results = notif["updates"]
                if results.get("intfId"):
                    entry["interface"] = results["intfId"]
                if results.get("linkStatus"):
                    entry["link_status"] = "up" if results["linkStatus"]["Name"] == "linkUp" else "down"
                if results.get("operStatus"):
                    entry["oper_status"] = "up" if results["operStatus"]["Name"] == "intfOperUp" else "down"
                if results.get("enabledState"):
                    entry["enabled"] = bool(results["enabledState"]["Name"] == "enabled")
                if results.get("burnedInAddr"):
                    entry["mac_addr"] = results["burnedInAddr"]
                if results.get("mtu"):
                    entry["mtu"] = results["mtu"]
    return list(per_intf.values())


def get_interfaces_fixed(client: CloudvisionApi, dId: str):
    """Gets information about interfaces for a fixed system device.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to determine type for.
    """
    pathElts = ["Sysdb", "interface", "status", "eth", "phy", "slice", "1", "intfStatus", Wildcard()]

    # Group notifications by the wildcarded interface name from the path. CloudVision may stream an
    # interface's attributes across multiple frames, and a frame carrying state (e.g. enabledState)
    # may not contain intfId, so anchoring on the path element and merging keeps those frames from being lost.
    per_intf = {}
    for batch in clean_query_results(pathElts, client, dId):
        for notif in batch["notifications"]:
            intf_name = notif["path_elements"][-1]
            entry = per_intf.setdefault(intf_name, {"interface": intf_name})
            results = notif["updates"]
            if results.get("intfId"):
                entry["interface"] = results["intfId"]
            if results.get("enabledState"):
                entry["enabled"] = bool(results["enabledState"]["Name"] == "enabled")
            if results.get("burnedInAddr"):
                entry["mac_addr"] = results["burnedInAddr"]
            if results.get("mtu"):
                entry["mtu"] = results["mtu"]
            if results.get("operStatus"):
                entry["oper_status"] = "up" if results["operStatus"]["Name"] == "intfOperUp" else "down"
            if results.get("linkStatus"):
                entry["link_status"] = "up" if results["linkStatus"]["Name"] == "linkUp" else "down"
    return list(per_intf.values())


def clean_query_results(path_elements: List[str], client: CloudvisionApi, dataset: str):
    """Retrieve and clean up a query to make it easier to use."""
    query = [create_query([(path_elements, [])], dataset)]
    query = list(client.get(query))
    query = unfreeze_frozen_dict(query)
    query = unpath(query)
    return query


# pylint: disable=too-many-branches
def get_interfaces_port_channel(client: CloudvisionApi, dId: str):
    """Gets information about Port-Channel (LAG) interfaces for a device.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to retrieve port-channel interfaces for.

    Returns:
        list[dict]: One entry per Port-Channel with keys ``interface``, ``link_status``,
        ``oper_status``, ``enabled``, ``mac_addr``, ``mtu``. Empty list when none exist.
    """
    status_path = ["Sysdb", "lag", "input", "interface", "lag", "intfStatus", Wildcard()]

    pc_interfaces = {}
    for batch in clean_query_results(status_path, client, dId):
        for notif in batch["notifications"]:
            # Anchor on the wildcarded interface name from the path so frames that omit intfId
            # (CloudVision may stream a Port-Channel's attributes across multiple frames) still merge.
            intf_id = notif["path_elements"][-1]
            results = notif["updates"]
            entry = pc_interfaces.setdefault(intf_id, {"interface": intf_id})
            if results.get("intfId"):
                entry["interface"] = results["intfId"]
            if results.get("linkStatus"):
                entry["link_status"] = "up" if results["linkStatus"]["Name"] == "linkUp" else "down"
            if results.get("operStatus"):
                entry["oper_status"] = "up" if results["operStatus"]["Name"] == "intfOperUp" else "down"
            if results.get("addr"):
                entry["mac_addr"] = results["addr"]
            if results.get("mtu"):
                entry["mtu"] = results["mtu"]
            if "active" in results and "enabled" not in entry:
                entry["enabled"] = bool(results["active"])

    config_path = ["Sysdb", "interface", "config", "eth", "lag", "intfConfig", Wildcard()]

    for batch in clean_query_results(config_path, client, dId):
        for notif in batch["notifications"]:
            # Anchor on the wildcarded interface name from the path so frames that omit name still merge.
            name = notif["path_elements"][-1]
            results = notif["updates"]
            entry = pc_interfaces.setdefault(name, {"interface": name})
            if results.get("mtu") and not entry.get("mtu"):
                entry["mtu"] = results["mtu"]
            if results.get("addr") and not entry.get("mac_addr"):
                entry["mac_addr"] = results["addr"]
            if "enabled" not in entry:
                state_local = results.get("enabledStateLocal")
                if isinstance(state_local, dict) and state_local.get("Name"):
                    entry["enabled"] = state_local["Name"] == "enabled"
                elif "enabledDefault" in results:
                    entry["enabled"] = bool(results["enabledDefault"])

    return list(pc_interfaces.values())


def get_port_channel_members(client: CloudvisionApi, dId: str) -> dict:
    """Map physical Ethernet interfaces to the Port-Channel they are bundled into.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to retrieve member relationships for.

    Returns:
        dict[str, str]: Mapping of physical interface name to its Port-Channel name.
        Empty dict when the device has no LAG members.
    """
    pathElts = ["Sysdb", "lag", "input", "config", "cli", "phyIntf", Wildcard()]

    members = {}
    for batch in clean_query_results(pathElts, client, dId):
        for notif in batch["notifications"]:
            results = notif["updates"]
            intf_id = results.get("intfId")
            lag_path = results.get("lag")
            if intf_id and isinstance(lag_path, list) and lag_path:
                members[intf_id] = lag_path[-1]
    return members


def get_interface_transceiver(client: CloudvisionApi, dId: str, interface: str):
    """Gets transceiver information for specified interface on specific device.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to determine transceiver type for.
        interface (str): Name of interface to get transceiver information for.
    """
    pathElts = ["Sysdb", "hardware", "archer", "xcvr", "status", "all", interface]

    for batch in clean_query_results(pathElts, client, dId):
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


def get_all_interface_transceivers(client: CloudvisionApi, dId: str) -> dict:
    """Fetch transceiver information for every interface on a device in a single query.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to retrieve transceivers for.

    Returns:
        dict[str, str]: Mapping of interface name to transceiver media type. Interfaces
        with no transceiver data are omitted; callers should fall back to "Unknown".
    """
    pathElts = ["Sysdb", "hardware", "archer", "xcvr", "status", "all", Wildcard()]

    transceivers = {}
    for batch in clean_query_results(pathElts, client, dId):
        for notif in batch["notifications"]:
            updates = notif["updates"]
            intf = notif["path_elements"][-1]
            eeprom = updates.get("actualIdEepromContents")
            if isinstance(eeprom, dict) and eeprom.get("mediaType"):
                transceivers[intf] = eeprom["mediaType"]
            elif updates.get("mediaType"):
                transceivers[intf] = updates["mediaType"]["Name"]
            elif updates.get("localMediaType"):
                transceivers[intf] = updates["localMediaType"]["Name"]
    return transceivers


def get_interface_mode(client: CloudvisionApi, dId: str, interface: str):
    """Gets interface mode, ie access/trunked.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to determine type for.
        interface (str): Name of interface to get mode information for.
    """
    pathElts = ["Sysdb", "bridging", "switchIntfConfig", "switchIntfConfig", interface]

    for batch in clean_query_results(pathElts, client, dId):
        for notif in batch["notifications"]:
            if notif["updates"].get("switchportMode"):
                return notif["updates"]["switchportMode"]["Name"]
    return "Unknown"


def get_all_interface_modes(client: CloudvisionApi, dId: str) -> dict:
    """Fetch switchport modes for every interface on a device in a single query.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to retrieve modes for.

    Returns:
        dict[str, str]: Mapping of interface name to switchport mode (e.g. "trunk",
        "access"). Interfaces with no mode data are omitted; callers should fall back
        to "Unknown".
    """
    pathElts = ["Sysdb", "bridging", "switchIntfConfig", "switchIntfConfig", Wildcard()]

    modes = {}
    for batch in clean_query_results(pathElts, client, dId):
        for notif in batch["notifications"]:
            mode = notif["updates"].get("switchportMode")
            if not mode:
                continue
            intf = notif["path_elements"][-1]
            modes[intf] = mode["Name"]
    return modes


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
    oper = port_info.get("oper_status")
    link = port_info.get("link_status")
    if oper == "up" and link == "up":
        return "Active"
    if oper == "up" and link == "down":
        return "Planned"
    if oper == "down" and link == "down":
        return "Maintenance"
    return "Decommissioning"


def get_interface_description(client: CloudvisionApi, dId: str, interface: str):
    """Gets interface description.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to get description for.
        interface (str): Name of interface to get description for.
    """
    if interface.startswith("Port-Channel"):
        pathElts = ["Sysdb", "interface", "config", "eth", "lag", "intfConfig", interface]
    else:
        pathElts = ["Sysdb", "interface", "config", "eth", "phy", "slice", "1", "intfConfig", interface]

    for batch in clean_query_results(pathElts, client, dId):
        for notif in batch["notifications"]:
            if notif["updates"].get("description") and notif["updates"]["description"] is not None:
                return notif["updates"]["description"]
    return ""


def get_all_interface_descriptions(client: CloudvisionApi, dId: str) -> dict:
    """Fetch descriptions for every interface on a device.

    CloudVision stores interface descriptions under two different path shapes:
    physical Ethernet at config/eth/phy/slice/<slice>/intfConfig/<intf>, and
    everything else (Port-Channel, L3, Vlan, Loopback, ...) at config/<x>/<y>/intfConfig/<intf>.
    Each Wildcard() matches exactly one segment, so two queries are required.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to retrieve descriptions for.

    Returns:
        dict[str, str]: Mapping of interface name to description. Interfaces with no
        description are omitted; callers should fall back to "".
    """
    paths = [
        # Physical Ethernet: eth/phy/slice/<slice>/intfConfig/<intf>
        ["Sysdb", "interface", "config", "eth", "phy", "slice", Wildcard(), "intfConfig", Wildcard()],
        # Non-physical (Port-Channel, L3, Vlan, Loopback, ...): <x>/<y>/intfConfig/<intf>
        ["Sysdb", "interface", "config", Wildcard(), Wildcard(), "intfConfig", Wildcard()],
    ]

    descriptions = {}
    for pathElts in paths:
        for batch in clean_query_results(pathElts, client, dId):
            for notif in batch["notifications"]:
                updates = notif["updates"]
                intf = updates.get("intfId")
                description = updates.get("description")
                if intf and description:
                    descriptions[intf] = description
    return descriptions


def get_routed_interface_description(client: CloudvisionApi, dId: str, interface: str) -> str:
    """Gets description for a non-physical interface (Loopback, Vlan SVI, Port-Channel, etc.).

    Walks a wildcard intfConfig subtree that covers every non-eth/phy interface kind in one query.
    Use get_interface_description for physical Ethernet interfaces.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to get description for.
        interface (str): Name of interface to get description for.
    """
    pathElts = ["Sysdb", "interface", "config", Wildcard(), Wildcard(), "intfConfig", Wildcard()]

    for batch in clean_query_results(pathElts, client, dId):
        for notif in batch["notifications"]:
            updates = notif["updates"]
            if updates.get("intfId") == interface:
                return updates.get("description") or ""
    return ""


def get_interface_vrf(client: CloudvisionApi, dId: str, interface: str) -> str:
    """Gets interface VRF.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to determine type for.
        interface (str): Name of interface to get mode information for.
    """
    pathElts = ["Sysdb", "l3", "intf", "config", "intfConfig", interface]

    for batch in clean_query_results(pathElts, client, dId):
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

    ip_intfs = []
    for batch in clean_query_results(pathElts, client, dId):
        # Group notifications by the wildcarded interface name from the path. gRPC can coalesce
        # multiple interfaces into one batch, so per-batch accumulators would silently overwrite
        # earlier interfaces' state.
        per_intf = {}
        for notif in batch["notifications"]:
            intf_name = notif["path_elements"][-1]
            entry = per_intf.setdefault(intf_name, {})
            updates = notif["updates"]
            if updates.get("intfId"):
                entry["interface"] = updates["intfId"]
            if updates.get("addrWithMask") and updates["addrWithMask"] != "0.0.0.0/0":
                entry["addr"] = updates["addrWithMask"]
            if updates.get("virtualAddrWithMask") and updates["virtualAddrWithMask"] != "0.0.0.0/0":
                entry["virtual_addr"] = updates["virtualAddrWithMask"]
        for entry in per_intf.values():
            address = entry.get("addr") or entry.get("virtual_addr")
            if entry.get("interface") and address:
                ip_intfs.append({"interface": entry["interface"], "address": address})
    return ip_intfs


def get_cvp_version(config: CloudVisionAppConfig):
    """Returns CloudVision portal version.

    Use ``CloudvisionApi(config).get_version()`` instead.
    Will be removed in a future release.

    Returns:
        str: CloudVision version from API or blank string if unable to find.
    """
    warnings.warn(
        "get_cvp_version() is deprecated, use CloudvisionApi(config).get_version() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return CloudvisionApi(config).get_version()
