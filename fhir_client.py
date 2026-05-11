import httpx


class FhirClient:
    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self) -> dict:
        headers = {"Accept": "application/fhir+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def read(self, path: str) -> dict | None:
        url = f"{self.base_url}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                r = await client.get(url, headers=self._headers())
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPStatusError, httpx.RequestError):
                return None

    async def search(self, resource_type: str, params: dict | None = None) -> dict | None:
        url = f"{self.base_url}/{resource_type}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                r = await client.get(url, headers=self._headers(), params=params)
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPStatusError, httpx.RequestError):
                return None
