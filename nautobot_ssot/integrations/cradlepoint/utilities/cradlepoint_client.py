import requests


class CradlepointClient:
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
