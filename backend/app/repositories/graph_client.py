"""
Low-level Microsoft Graph v1.0 HTTP client.
Handles: auth header injection, 429 throttling with Retry-After,
token expiry refresh, pagination via @odata.nextLink, timeouts.
All calls are server-side only.
"""
import httpx
import time
from typing import Callable

class GraphError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Graph API Error {status_code}: {message}")

class GraphClient:
    BASE_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self, access_token_getter: Callable[[], str | None]):
        self.access_token_getter = access_token_getter
        self.client = httpx.Client(timeout=30.0)

    def _get_headers(self) -> dict:
        token = self.access_token_getter()
        if not token:
            raise GraphError(401, "No access token available")
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, url: str, **kwargs) -> dict:
        if not url.startswith("http"):
            url = f"{self.BASE_URL}{url}"

        for attempt in range(4): # max 3 retries
            headers = self._get_headers()
            kwargs["headers"] = headers
            
            try:
                response = self.client.request(method, url, **kwargs)
            except httpx.RequestError as e:
                raise GraphError(503, f"Request failed: {str(e)}")

            if response.status_code == 429:
                if attempt < 3:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    time.sleep(retry_after)
                    continue
                
            if response.status_code >= 400:
                raise GraphError(response.status_code, response.text)

            if response.status_code == 204:
                return {}
            
            return response.json()
            
        raise GraphError(429, "Too many requests after retries")

    def get(self, path: str, params: dict = None) -> dict:
        return self._request("GET", path, params=params)

    def post(self, path: str, body: dict) -> dict:
        return self._request("POST", path, json=body)

    def patch(self, path: str, body: dict) -> dict:
        return self._request("PATCH", path, json=body)

    def get_all_pages(self, path: str, params: dict = None) -> list[dict]:
        results = []
        current_url = path
        current_params = params

        while current_url:
            data = self._request("GET", current_url, params=current_params)
            if "value" in data:
                results.extend(data["value"])
            
            current_url = data.get("@odata.nextLink")
            current_params = None # nextLink already has params

        return results
