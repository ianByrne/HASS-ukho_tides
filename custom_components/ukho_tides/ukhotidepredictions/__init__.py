import json
import logging

from aiohttp import ClientSession

from .const import (
    ENDPOINT_BASE,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
)

_LOGGER = logging.getLogger(__name__)


class UkhoTidePredictions:
    def __init__(self, api_key, session: ClientSession, station_id, station_name=None):
        self._api_key = api_key
        self._session = session
        self._station_id = station_id
        self._station_name = station_name
        self._station_country = None

    async def _async_get_data(self, url: str) -> str:
        async with self._session.get(
            url, headers={"Ocp-Apim-Subscription-Key": self._api_key}
        ) as resp:
            if resp.status == HTTP_UNAUTHORIZED:
                raise InvalidApiKeyError("Invalid API key")
            if resp.status != HTTP_OK:
                raise ApiError(f"Invalid response from API: {resp.status}")
            _LOGGER.debug("Data retrieved from %s, status: %s", url, resp.status)
            data = await resp.json()
        return data

    async def async_get_station_name(self):
        url = ENDPOINT_BASE + self._station_id
        data = await self._async_get_data(url)
        self._station_name = data["properties"]["Name"]
        self._station_country = data["properties"]["Country"]

    async def async_get_tidal_events(self, metric=True):
        url = ENDPOINT_BASE + self._station_id + "/TidalEvents"
        data = await self._async_get_data(url)
        return data

    @property
    def station_id(self):
        return self._station_id

    @property
    def station_name(self):
        return self._station_name


class ApiError(Exception):
    def __init__(self, status):
        super().__init__(status)
        self.status = status


class InvalidApiKeyError(Exception):
    def __init__(self, status):
        super().__init__(status)
        self.status = status