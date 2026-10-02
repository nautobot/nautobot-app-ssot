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
UNSET_IP_ADDRESS = "0.0.0.0/0"
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
            if config.token:
                client.connect(
                    nodes=[parsed_url.hostname],
                    username="",
                    password="",
                    is_cvaas=not config.is_on_premise,
                    api_token=config.token,
                )
            elif config.cvp_user and config.cvp_password:
                client.connect(
                    nodes=[parsed_url.hostname],
                    username=config.cvp_user,
                    password=config.cvp_password,
                    is_cvaas=False,
                )
            else:
                raise AuthFailure(
                    error_code="Missing Credentials",
                    message="Unable to authenticate due to missing credentials.",
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

    Merges the updates of every notification into one flat dict, so it must only be used with a
    path that resolves to a single object. Use `collate_notifications` for a path containing a
    `Wildcard()`, which would otherwise collapse distinct objects into each other.

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

    # Interface names are unique across linecards, so a single accumulator spans all of them.
    per_intf = {}
    for lc in queryLC:
        pathElts = ["Sysdb", "interface", "status", "eth", "phy", "slice", lc, "intfStatus", Wildcard()]
        for intf_name, updates in collate_notifications(client, dataset, pathElts).items():
            per_intf.setdefault(intf_name, {}).update(updates)
    return [_interface_status_entry(name, updates) for name, updates in per_intf.items()]


def get_interfaces_fixed(client: CloudvisionApi, dId: str):
    """Gets information about interfaces for a fixed system device.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to determine type for.
    """
    pathElts = ["Sysdb", "interface", "status", "eth", "phy", "slice", "1", "intfStatus", Wildcard()]

    return [
        _interface_status_entry(name, updates) for name, updates in collate_notifications(client, dId, pathElts).items()
    ]


def clean_query_results(path_elements: List[str], client: CloudvisionApi, dataset: str):
    """Retrieve and clean up a query to make it easier to use."""
    query = [create_query([(path_elements, [])], dataset)]
    query = list(client.get(query))
    query = unfreeze_frozen_dict(query)
    query = unpath(query)
    return query


def collate_notifications(client: CloudvisionApi, dId: str, path_elements: List[str], key_index: int = -1) -> dict:
    """Merge the updates of a query into a single attribute dict per object.

    CloudVision streams an object's attributes across an arbitrary number of notifications and
    batches, and a notification carrying state routinely omits the object's identity key (`intfId`,
    `name`). The wildcard element of the gRPC path is the only reliable identity, so notifications
    are grouped by that element and their updates merged.

    Callers must interpret the merged result rather than an individual notification. Choosing
    between attributes, or requiring two attributes to be present together, is only correct once
    every frame for that object has been merged.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to query.
        path_elements (List[str]): Query path, normally containing a `Wildcard()`.
        key_index (int): Index into a notification's path elements identifying the object.

    Returns:
        dict[str, dict]: Object name mapped to its merged updates, in first-seen order.
    """
    collated = {}
    for batch in clean_query_results(path_elements, client, dId):
        for notif in batch["notifications"]:
            collated.setdefault(notif["path_elements"][key_index], {}).update(notif["updates"])
    return collated


def _interface_status_entry(name: str, updates: dict) -> dict:
    """Build an interface entry from merged `intfStatus` updates.

    Args:
        name (str): Interface name taken from the query path.
        updates (dict): Merged updates for that interface.

    Returns:
        dict: Interface attributes, omitting anything CloudVision did not report.
    """
    entry = {"interface": updates.get("intfId") or name}
    if updates.get("linkStatus"):
        entry["link_status"] = "up" if updates["linkStatus"]["Name"] == "linkUp" else "down"
    if updates.get("operStatus"):
        entry["oper_status"] = "up" if updates["operStatus"]["Name"] == "intfOperUp" else "down"
    if updates.get("enabledState"):
        entry["enabled"] = bool(updates["enabledState"]["Name"] == "enabled")
    if updates.get("burnedInAddr"):
        entry["mac_addr"] = updates["burnedInAddr"]
    if updates.get("mtu"):
        entry["mtu"] = updates["mtu"]
    return entry


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

    config_path = ["Sysdb", "interface", "config", "eth", "lag", "intfConfig", Wildcard()]

    # The two subtrees are collated separately rather than merged: they share attribute names
    # (mtu, addr) and the operational values from intfStatus take precedence over the configured
    # ones from intfConfig.
    status = collate_notifications(client, dId, status_path)
    config = collate_notifications(client, dId, config_path)

    pc_interfaces = {}
    for name in dict.fromkeys([*status, *config]):
        status_updates = status.get(name, {})
        config_updates = config.get(name, {})
        entry = {"interface": status_updates.get("intfId") or config_updates.get("intfId") or name}
        if status_updates.get("linkStatus"):
            entry["link_status"] = "up" if status_updates["linkStatus"]["Name"] == "linkUp" else "down"
        if status_updates.get("operStatus"):
            entry["oper_status"] = "up" if status_updates["operStatus"]["Name"] == "intfOperUp" else "down"
        mac_addr = status_updates.get("addr") or config_updates.get("addr")
        if mac_addr:
            entry["mac_addr"] = mac_addr
        mtu = status_updates.get("mtu") or config_updates.get("mtu")
        if mtu:
            entry["mtu"] = mtu
        enabled = _port_channel_enabled(status_updates, config_updates)
        if enabled is not None:
            entry["enabled"] = enabled
        pc_interfaces[name] = entry

    return list(pc_interfaces.values())


def _port_channel_enabled(status_updates: dict, config_updates: dict):
    """Resolve a Port-Channel's enabled state, preferring operational data over configuration.

    Args:
        status_updates (dict): Merged updates from the `lag/input/interface/lag/intfStatus` subtree.
        config_updates (dict): Merged updates from the `interface/config/eth/lag/intfConfig` subtree.

    Returns:
        bool: The enabled state, or None when CloudVision reported neither source.
    """
    if "active" in status_updates:
        return bool(status_updates["active"])
    state_local = config_updates.get("enabledStateLocal")
    if isinstance(state_local, dict) and state_local.get("Name"):
        return state_local["Name"] == "enabled"
    if "enabledDefault" in config_updates:
        return bool(config_updates["enabledDefault"])
    return None


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
    for intf_name, updates in collate_notifications(client, dId, pathElts).items():
        lag_path = updates.get("lag")
        if isinstance(lag_path, list) and lag_path:
            members[updates.get("intfId") or intf_name] = lag_path[-1]
    return members


def get_interface_transceiver(client: CloudvisionApi, dId: str, interface: str):
    """Gets transceiver information for specified interface on specific device.

    Args:
        client (CloudvisionApi): CloudVision connection.
        dId (str): Device ID to determine transceiver type for.
        interface (str): Name of interface to get transceiver information for.
    """
    pathElts = ["Sysdb", "hardware", "archer", "xcvr", "status", "all", interface]

    for updates in collate_notifications(client, dId, pathElts).values():
        media_type = _transceiver_media_type(updates)
        if media_type:
            return media_type
    return "Unknown"


def _transceiver_media_type(updates: dict) -> str:
    """Resolve a transceiver's media type from merged updates, most authoritative source first.

    The priority has to be applied once to the merged attributes. Applying it per notification lets
    a frame carrying only `localMediaType` win over a frame carrying the eeprom contents.

    Args:
        updates (dict): Merged updates for one transceiver.

    Returns:
        str: The media type, or an empty string when CloudVision reported none.
    """
    eeprom = updates.get("actualIdEepromContents")
    if isinstance(eeprom, dict) and eeprom.get("mediaType"):
        return eeprom["mediaType"]
    if updates.get("mediaType"):
        return updates["mediaType"]["Name"]
    if updates.get("localMediaType"):
        return updates["localMediaType"]["Name"]
    return ""


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
    for intf, updates in collate_notifications(client, dId, pathElts).items():
        media_type = _transceiver_media_type(updates)
        if media_type:
            transceivers[intf] = media_type
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
    for intf, updates in collate_notifications(client, dId, pathElts).items():
        mode = updates.get("switchportMode")
        if mode:
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
        for intf, updates in collate_notifications(client, dId, pathElts).items():
            description = updates.get("description")
            if description:
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

    collated = collate_notifications(client, dId, pathElts)
    return collated.get(interface, {}).get("description") or ""


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
    for intf_name, updates in collate_notifications(client, dId, pathElts).items():
        addresses = [updates.get("addrWithMask"), updates.get("virtualAddrWithMask")]
        # CloudVision reports 0.0.0.0/0 for an interface with no address of that kind.
        address = next((addr for addr in addresses if addr and addr != UNSET_IP_ADDRESS), None)
        if address:
            ip_intfs.append({"interface": updates.get("intfId") or intf_name, "address": address})
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
