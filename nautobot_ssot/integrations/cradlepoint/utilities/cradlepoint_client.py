import requests


class CradlepointClient:
    def __init__(self, api_key, base_url="https://www.cradlepointecm.com/api/v2/"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method, endpoint, params=None, data=None):
        url = f"{self.base_url}{endpoint}"
        response = requests.request(
            method, url, headers=self.headers, params=params, json=data
        )

        if not response.ok:
            raise Exception(f"Error {response.status_code}: {response.text}")

        return response.json()

    def get_routers(self, params=None):
        """Fetch a list of routers."""
        return self._request("GET", "routers", params=params)

    def get_router_by_id(self, router_id):
        """Fetch details of a specific router by ID."""
        return self._request("GET", f"routers/{router_id}")

    def reboot_router(self, router_id):
        """Reboot a router by ID."""
        return self._request("POST", f"routers/{router_id}/reboot")

    def get_alerts(self, params=None):
        """Fetch a list of alerts."""
        return self._request("GET", "alerts", params=params)

    def create_alert(self, data):
        """Create a new alert."""
        return self._request("POST", "alerts", data=data)

    def update_router(self, router_id, data):
        """Update a router's information."""
        return self._request("PATCH", f"routers/{router_id}", data=data)

    def delete_alert(self, alert_id):
        """Delete an alert by ID."""
        return self._request("DELETE", f"alerts/{alert_id}")


# Usage Example:
# client = CradlepointECMClient(api_key="your_api_key")
# routers = client.get_routers()
# print(routers)
