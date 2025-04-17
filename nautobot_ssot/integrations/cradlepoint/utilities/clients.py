"""SDK for Cradlepoint API."""

from dataclasses import dataclass, field
# from ratelimit import limits
import requests
from requests.exceptions import HTTPError
from nautobot.extras.choices import (
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)

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

def get_secret_from_group(secrets_group, choice):
    """Get a Nautobot secret value from the app config"""
    return secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=choice,
    )

def cradlepoint_client(app_config, debug, **kwargs) -> CradlepointClient:
    """Instantiate and return Cradlepoint API client object."""
    secrets_group = app_config.cradlepoint_instance.secrets_group

    return CradlepointClient(
        base_url=app_config.api_url,
        x_cp_api_id=get_secret_from_group(secrets_group, SecretsGroupSecretTypeChoices.TYPE_SECRET),
        x_cp_api_key=get_secret_from_group(secrets_group, SecretsGroupSecretTypeChoices.TYPE_TOKEN),
        x_ecm_api_id=get_secret_from_group(secrets_group, SecretsGroupSecretTypeChoices.TYPE_USERNAME),
        x_ecm_api_key=get_secret_from_group(secrets_group, SecretsGroupSecretTypeChoices.TYPE_PASSWORD),
        verify_ssl=getattr(app_config, "verify_ssl", True),
        page_limit=kwargs.pop("page_limit", 100),
        debug=debug,
    )
