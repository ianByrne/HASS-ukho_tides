import json
import logging

from aiohttp import ClientSession

from .const import (
    ENDPOINT_BASE,
    HTTP_OK,
    HTTP_BAD_REQUEST,
    HTTP_UNAUTHORIZED,
    HTTP_FORBIDDEN,
    HTTP_NOT_FOUND,
    HTTP_TOO_MANY_REQUESTS,
    HTTP_INTERNAL_SERVER_ERROR
)

_LOGGER = logging.getLogger(__name__)


class AdmiraltyUKTidalApi:
    def __init__(self, session: ClientSession, api_key):
        self._session = session
        self._api_key = api_key

    async def _async_get_data(self, url: str) -> str:
        async with self._session.get(
            url, headers={"Ocp-Apim-Subscription-Key": self._api_key}
        ) as resp:
            if resp.status == HTTP_UNAUTHORIZED:
                raise InvalidApiKeyError("Invalid API key")
            if resp.status == HTTP_FORBIDDEN:
                raise ApiQuotaExceededError("API quota exceeded")
            if resp.status == HTTP_TOO_MANY_REQUESTS:
                raise TooManyRequestsError("Too many API requests")
            if resp.status == HTTP_NOT_FOUND:
                raise StationNotFoundError("Station not found")
            if resp.status != HTTP_OK:
                raise ApiError(f"Invalid response from API: {resp.status}")
            
            _LOGGER.debug("Data retrieved from %s, status: %s", url, resp.status)
            
            return await resp.json()

    async def async_get_stations(self):
        url = ENDPOINT_BASE
        return await self._async_get_data(url)

    async def async_get_station(self, station_id):
        url = ENDPOINT_BASE + station_id
        return await self._async_get_data(url)

    async def async_get_tidal_events(self, station_id):
        url = ENDPOINT_BASE + station_id + "/TidalEvents"
        return await self._async_get_data(url)


class ApiError(Exception):
    def __init__(self, status):
        super().__init__(status)
        self.status = status


class InvalidApiKeyError(Exception):
    def __init__(self, status):
        super().__init__(status)
        self.status = status


class ApiQuotaExceededError(Exception):
    def __init__(self, status):
        super().__init__(status)
        self.status = status


class TooManyRequestsError(Exception):
    def __init__(self, status):
        super().__init__(status)
        self.status = status


class StationNotFoundError(Exception):
    def __init__(self, status):
        super().__init__(status)
        self.status = status