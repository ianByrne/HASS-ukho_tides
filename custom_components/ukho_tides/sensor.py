import datetime
import logging
import voluptuous as vol

import homeassistant.helpers.config_validation as cv

from .admiraltyuktidalapi import (
    AdmiraltyUKTidalApi,
    ApiError,
    InvalidApiKeyError,
    ApiQuotaExceededError,
    TooManyRequestsError,
    StationNotFoundError,
)
from async_timeout import timeout
from aiohttp.client_exceptions import ClientConnectorError
from typing import Any, Callable, Dict, Optional
from homeassistant.const import ATTR_ATTRIBUTION, CONF_API_KEY
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
    HomeAssistantType,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    COORDINATOR,
    ATTRIBUTION,
    ATTR_ICON_RISING,
    ATTR_ICON_FALLING,
    CONF_STATIONS,
    CONF_STATION_ID,
    CONF_STATION_NAME,
)

_LOGGER = logging.getLogger(__name__)

TIDE_STATION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_STATION_ID): cv.string,
        vol.Optional(CONF_STATION_NAME): cv.string,
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_API_KEY): cv.string,
        vol.Required(CONF_STATIONS): vol.All(cv.ensure_list, [TIDE_STATION_SCHEMA]),
    }
)


async def async_setup_platform(
    hass: HomeAssistantType,
    config: ConfigType,
    async_add_entities: Callable,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    session = async_get_clientsession(hass)
    admiraltyUKTidalApi = AdmiraltyUKTidalApi(session, config[CONF_API_KEY])

    sensors = []

    for station in config[CONF_STATIONS]:
        coordinator = AdmiraltyUKTidalApiDataUpdateCoordinator(
            hass, admiraltyUKTidalApi, station
        )

        if CONF_STATION_NAME in coordinator.station:
            name = station[CONF_STATION_NAME]
        else:
            name = (
                await admiraltyUKTidalApi.async_get_station(
                    coordinator.station[CONF_STATION_ID]
                )
            )["properties"]["Name"]

        sensors.append(UkhoTidesSensor(coordinator, name))

    async_add_entities(sensors, update_before_add=True)


async def async_setup_entry(hass, entry, async_add_entities):
    config = hass.data[DOMAIN][entry.entry_id]
    session = async_get_clientsession(hass)
    admiraltyUKTidalApi = AdmiraltyUKTidalApi(session, config[CONF_API_KEY])

    sensors = []

    for station in config[CONF_STATIONS]:
        coordinator = AdmiraltyUKTidalApiDataUpdateCoordinator(
            hass, admiraltyUKTidalApi, station
        )

        if CONF_STATION_NAME in coordinator.station:
            name = station[CONF_STATION_NAME]
        else:
            name = (
                await admiraltyUKTidalApi.async_get_station(
                    coordinator.station[CONF_STATION_ID]
                )
            )["properties"]["Name"]

        sensors.append(UkhoTidesSensor(coordinator, name))

    async_add_entities(sensors, update_before_add=True)


class UkhoTidesSensor(CoordinatorEntity):
    def __init__(self, coordinator, name):
        super().__init__(coordinator)
        self._name = name + " Tide"
        self._attrs = {ATTR_ATTRIBUTION: ATTRIBUTION}

    @property
    def name(self):
        if self._name:
            return self._name

        return "Unknown"

    @property
    def unique_id(self):
        return self.coordinator.station[CONF_STATION_ID]

    @property
    def state(self):
        if self.coordinator.data is None:
            return None

        nextPrediction = self.get_next_prediction()

        if nextPrediction["EventType"] == "HighWater":
            return "Rising"
        else:
            return "Falling"

    @property
    def icon(self):
        if self.coordinator.data is None:
            return None

        nextPrediction = self.get_next_prediction()

        if nextPrediction["EventType"] == "HighWater":
            return ATTR_ICON_RISING
        else:
            return ATTR_ICON_FALLING

    @property
    def device_state_attributes(self):
        nextPrediction = self.get_next_prediction()

        now = datetime.datetime.utcnow()

        timeToNextTide = nextPrediction["DateTimeObject"] - now
        nextHeight = round(nextPrediction["Height"], 1)

        hours, rem = divmod(timeToNextTide.seconds, 3600)
        minutes, seconds = divmod(rem, 60)

        if nextPrediction["EventType"] == "HighWater":
            kind = "high"
        else:
            kind = "low"

        self._attrs[f"{kind}_tide_in"] = f"{hours}h {minutes}m"
        self._attrs[f"{kind}_tide_height"] = f"{nextHeight}m"

        return self._attrs

    def get_next_prediction(self):
        now = datetime.datetime.utcnow()

        for prediction in self.coordinator.data:
            prediction["DateTimeObject"] = datetime.datetime.strptime(
                prediction["DateTime"].split(".")[0], "%Y-%m-%dT%H:%M:%S"
            )

            if prediction["DateTimeObject"] > now:
                return prediction

        return None


class AdmiraltyUKTidalApiDataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, admiraltyUKTidalApi, station):
        self._admiraltyUKTidalApi = admiraltyUKTidalApi
        self.station = station
        self._download_interval = datetime.timedelta(minutes=60)
        self._last_download_datetime = None
        self._data = None

        update_interval = datetime.timedelta(minutes=1)

        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)

    async def _async_update_data(self):
        now = datetime.datetime.utcnow()

        # As predictions rarely change, only refresh from the API infrequently
        if (
            self._last_download_datetime is None
            or self._data is None
            or self._last_download_datetime < now - self._download_interval
        ):
            _LOGGER.debug("Re-downloading tide data")

            try:
                async with timeout(10):
                    self._data = await self._admiraltyUKTidalApi.async_get_tidal_events(
                        self.station[CONF_STATION_ID]
                    )
            except (
                ApiError,
                ClientConnectorError,
                InvalidApiKeyError,
                # TODO: Other errors
            ) as error:
                raise UpdateFailed(error) from error

            self._last_download_datetime = now

        return self._data