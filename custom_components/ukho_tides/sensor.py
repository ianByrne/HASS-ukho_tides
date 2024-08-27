from datetime import datetime, timedelta, timezone
import logging
from operator import itemgetter
from typing import Any, Callable, Dict, List, Optional, Tuple

from aiohttp.client_exceptions import ClientConnectorError
from async_timeout import timeout
from ukhotides import ApiError, InvalidApiKeyError, TidalEvent, UkhoTides
import voluptuous as vol

from homeassistant import config_entries, core
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import ATTR_ATTRIBUTION, CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    ATTR_ICON_FALLING,
    ATTR_ICON_RISING,
    ATTRIBUTION,
    CONF_API_LEVEL,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_STATION_OFFSET_HIGH,
    CONF_STATION_OFFSET_LOW,
    CONF_STATIONS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

TIDE_STATION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_STATION_ID): cv.string,
        vol.Optional(CONF_STATION_NAME): cv.string,
        vol.Optional(CONF_STATION_OFFSET_HIGH): int,
        vol.Optional(CONF_STATION_OFFSET_LOW): int,
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_API_KEY): cv.string,
        vol.Optional(CONF_API_LEVEL): cv.string,
        vol.Required(CONF_STATIONS): vol.All(cv.ensure_list, [TIDE_STATION_SCHEMA]),
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: Callable,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    session = async_get_clientsession(hass)
    ukhotides = UkhoTides(session, config[CONF_API_KEY])

    sensors = []

    for station in config[CONF_STATIONS]:
        coordinator = UkhoTidesDataUpdateCoordinator(hass, ukhotides, station)

        if CONF_STATION_NAME in coordinator.station:
            name = station[CONF_STATION_NAME]
        else:
            name = (
                await ukhotides.async_get_station(coordinator.station[CONF_STATION_ID])
            ).name

        sensors.append(UkhoTidesSensor(coordinator, name))

    async_add_entities(sensors, update_before_add=True)


async def async_setup_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry, async_add_entities
):
    config = hass.data[DOMAIN][entry.entry_id]

    if entry.options:
        config.update(entry.options)

    session = async_get_clientsession(hass)
    ukhotides = UkhoTides(session, config[CONF_API_KEY])

    sensors = []

    for station in config[CONF_STATIONS]:
        coordinator = UkhoTidesDataUpdateCoordinator(hass, ukhotides, station)

        if CONF_STATION_NAME in coordinator.station:
            name = station[CONF_STATION_NAME]
        else:
            name = (
                await ukhotides.async_get_station(coordinator.station[CONF_STATION_ID])
            ).name

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

        next_predictions = self.get_next_predictions()

        if next_predictions[0]["tidal_event"].event_type == "HighWater":
            return "Rising"
        else:
            return "Falling"

    @property
    def icon(self):
        if self.coordinator.data is None:
            return None

        next_predictions = self.get_next_predictions()

        if next_predictions[0]["tidal_event"].event_type == "HighWater":
            return ATTR_ICON_RISING
        else:
            return ATTR_ICON_FALLING

    @property
    def extra_state_attributes(self):
        next_predictions = self.get_next_predictions()

        if next_predictions is None:
            return None

        self._attrs[f"predictions"] = []
        for p in self.coordinator.data:
            self._attrs[f"predictions"].append(
                [
                    p["tidal_event_datetime"].strftime("%Y-%m-%d %H:%M:%S"),
                    round(p["tidal_event"].height, 1),
                ]
            )

        now = datetime.utcnow().replace(tzinfo=timezone.utc)

        for i in range(2):
            time_to_next_tide = next_predictions[i]["tidal_event_datetime"] - now
            next_height = round(next_predictions[i]["tidal_event"].height, 1)

            hours, rem = divmod(time_to_next_tide.seconds, 3600)
            minutes, seconds = divmod(rem, 60)

            if next_predictions[i]["tidal_event"].event_type == "HighWater":
                self._attrs[f"next_high_tide_in"] = f"{hours}h {minutes}m"
                self._attrs[f"next_high_tide_at"] = next_predictions[i][
                    "tidal_event_datetime"
                ].astimezone()
                self._attrs[f"next_high_tide_height"] = f"{next_height}m"
            else:
                self._attrs[f"next_low_tide_in"] = f"{hours}h {minutes}m"
                self._attrs[f"next_low_tide_at"] = next_predictions[i][
                    "tidal_event_datetime"
                ].astimezone()
                self._attrs[f"next_low_tide_height"] = f"{next_height}m"

        return self._attrs

    def get_next_predictions(self) -> [{datetime, TidalEvent}]:
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        next_predictions = []

        for tidal_event in self.coordinator.data:
            if tidal_event["tidal_event_datetime"] > now:
                next_predictions.append(tidal_event)

        return next_predictions


class UkhoTidesDataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, ukhotides, station):
        self._ukhotides = ukhotides
        self._download_interval = timedelta(minutes=60)
        self._last_download_datetime = None
        self._data = []
        self.station = station

        update_interval = timedelta(minutes=1)

        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)

    async def _async_update_data(self) -> List[TidalEvent]:
        now = datetime.utcnow().replace(tzinfo=timezone.utc)

        # As predictions rarely change, only refresh from the API infrequently
        if (
            self._last_download_datetime is None
            or not self._data
            or self._last_download_datetime < now - self._download_interval
        ):
            _LOGGER.debug("Re-downloading tide data")

            try:
                async with timeout(10):
                    tidal_events = await self._ukhotides.async_get_tidal_events(
                        self.station[CONF_STATION_ID]
                    )

                    for tidal_event in tidal_events:
                        tidal_event_datetime = datetime.strptime(
                            # Get just the stuff before any potential milliseconds
                            tidal_event.date_time.split(".")[0],
                            "%Y-%m-%dT%H:%M:%S",
                        )
                        # Convert to UTC
                        tidal_event_datetime = tidal_event_datetime.replace(
                            tzinfo=timezone.utc
                        )

                        # Add any offsets
                        if (
                            tidal_event.event_type == "HighWater"
                            and CONF_STATION_OFFSET_HIGH in self.station
                        ):
                            tidal_event_datetime = tidal_event_datetime + timedelta(
                                minutes=self.station[CONF_STATION_OFFSET_HIGH]
                            )

                        if (
                            tidal_event.event_type == "LowWater"
                            and CONF_STATION_OFFSET_LOW in self.station
                        ):
                            tidal_event_datetime = tidal_event_datetime + timedelta(
                                minutes=self.station[CONF_STATION_OFFSET_LOW]
                            )

                        self._data.append(
                            {
                                "tidal_event_datetime": tidal_event_datetime,
                                "tidal_event": tidal_event,
                            }
                        )

                    # Stack Overflow voodoo (comprehension) to get distinct events
                    self._data = [
                        i
                        for n, i in enumerate(self._data)
                        if i not in self._data[n + 1 :]
                    ]
                    self._data.sort(key=itemgetter("tidal_event_datetime"))

                    i = 0
                    for tidal_event in self._data:
                        if tidal_event["tidal_event_datetime"] > now:
                            if i > 1:
                                self._data = self._data[i - 2 :]
                            break

                        i += 1
            except (
                ApiError,
                ClientConnectorError,
                InvalidApiKeyError,
                # TODO: Other errors
            ) as error:
                raise UpdateFailed(error) from error

            self._last_download_datetime = now

        return self._data
