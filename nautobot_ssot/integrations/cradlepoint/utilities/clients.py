"""SDK for Cradlepoint API."""

from dataclasses import dataclass, field
#from ratelimit import limits
import requests
from requests.exceptions import HTTPError

@dataclass
class CradlepointClient:
    """Client class or interacting with Cradlepoint API."""

    x_ecm_api_id: str = field(repr=False)
    x_ecm_api_key: str = field(repr=False)
    x_cp_api_id: str = field(repr=False)
    x_cp_api_key: str = field(repr=False)
    base_url: str = "https://cradlepointcm.com/api/v2"
    page_limit: int = 20
    verify_ssl: bool = True
    debug: bool = False

    def __post_init__(self):
        """Post init actions."""
        self.base_url = self.base_url.rstrip("/")

    def request_params(self, **kwargs):
        """Build request params from kwargs while skipping NoneTypes."""
        params = {}
        for key, value in kwargs.items():
            if value is None:
                continue
            params[key] = value
        if not params:
            return None
        return params



    @property
    def headers(self):
        """Get required headers for API calls."""
        return {
            "X-ECM-API-ID": self.x_ecm_api_id,
            "X-ECM-API-KEY": self.x_ecm_api_key,
            "X-CP-API-ID": self.x_cp_api_id,
            "X-CP-API-KEY": self.x_cp_api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    
    # TODO: Make `calls` field configurable for rate limiting
    #@limits(calls=500, period=300)
    def request(self, method, endpoint, params=None, **kwargs):
        response = requests.request(
            method=method,
            url=f"{self.base_url}/{endpoint}",
            headers=kwargs.pop("headers", self.headers),
            verify=self.verify_ssl,
            params=params,
            **kwargs,
        )
        if not response.ok:
            raise HTTPError(f"{response.status_code} Error: {response.reason}")
        return response

    def get(self, endpoint: str, object_id=None, **kwargs):
        """Perform GET request."""
        if endpoint[-1] != "/": endpoint = f"{endpoint}/"
        # Add object ID to URL if defined
        if object_id: endpoint = f"{endpoint}/{object_id}/"
        return self.request(
            "GET",
            endpoint=endpoint,
            **kwargs,
        )
    
    def load_from_paginated_list(self, endpoint):
        """Generator method for getting paginated data from API."""
        offset = 0
        next_page = True
        call_method = getattr(self, f"get_{endpoint}")
        if not call_method:
            raise AttributeError(f"Cradlepoint client does not have method `{call_method}`.")

        while next_page:
            response = call_method(offset=offset).json()
            meta = response["meta"]
            data = response["data"]

            yield data

            offset = offset + self.page_limit
            next_page = meta["next"]
        return None

    def get_routers(self, offset=0, fields=None):
        """Fetch a list of routers."""
        return self.get(
            endpoint="routers/",
            params=self.request_params(
                limit=self.page_limit,
                offset=offset,
                fields=fields,
            )
        )

    def get_locations(self, offset=0, fields=None):
        """Fetch a list of locations."""
        return self.get(
            endpoint="locations/",
            params=self.request_params(
                limit=self.page_limit,
                offset=offset,
                fields=fields,
            ),
        )

    def get_products(self, offset=0, fields=None):
        """Fetch a list of products."""
        return self.get(
            endpoint="products/",
            params=self.request_params(
                limit=self.page_limit,
                offset=offset,
                fields=fields,
            ),
        )




class CradlepointClientOld:
    """initialize the CradlepointClient client."""

    def __init__(
        self,
        cradlepoint_uri,
        x_ecm_api_id,
        x_ecm_api_key,
        x_cp_api_id,
        x_cp_api_key,
        verify_ssl,
        debug,
    ):
        """Initialize the CradlepointClient client."""
        self.base_url = f"{cradlepoint_uri}/api/v2/"
        self.x_ecm_api_id_token = x_ecm_api_id
        self.x_ecm_api_key_token = x_ecm_api_key
        self.x_cp_api_id_token = x_cp_api_id
        self.x_cp_api_key_token = x_cp_api_key
        self.verify_ssl = verify_ssl
        self.debug = debug
        self.headers = {
            "X-ECM-API-ID": self.x_ecm_api_id_token,
            "X-ECM-API-KEY": self.x_ecm_api_key_token,
            "X-CP-API-ID": self.x_cp_api_id_token,
            "X-CP-API-KEY": self.x_cp_api_key_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method, endpoint, params=None, data=None):
        url = f"{self.base_url}{endpoint}"
        response = requests.request(  # noqa: S113
            method, url, headers=self.headers, params=params, json=data
        )

        if not response.ok:
            raise Exception(f"Error {response.status_code}: {response.text}")

        return response.json()

    def get_routers(self, params=None):
        """Fetch a list of routers."""
        if "limit" not in params:
            params["limit"] = 100
        return self._request("GET", "routers", params=params)

    def get_locations(self, params=None):
        """Fetch a list of locations."""
        return self._request("GET", "locations", params=params)

    def get_products(self, params=None):
        """Fetch a list of products."""
        return self._request("GET", "products", params=params)
