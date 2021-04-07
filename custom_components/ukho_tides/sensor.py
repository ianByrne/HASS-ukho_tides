import logging
import voluptuous as vol

import homeassistant.helpers.config_validation as cv

from operator import itemgetter
from ukhotides import (
    UkhoTides,
    ApiError,
    InvalidApiKeyError,
    TidalEvent,
)
from datetime import datetime, timedelta
from async_timeout import timeout
from aiohttp.client_exceptions import ClientConnectorError
from typing import Any, Callable, Dict, Optional, Tuple, List
from homeassistant import config_entries, core
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
    ATTRIBUTION,
    ATTR_ICON_RISING,
    ATTR_ICON_FALLING,
    CONF_API_LEVEL,
    CONF_STATIONS,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_STATION_OFFSET_HIGH,
    CONF_STATION_OFFSET_LOW,
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
    hass: HomeAssistantType,
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
    def device_state_attributes(self):
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

        now = datetime.utcnow()

        for i in range(2):
            time_to_next_tide = next_predictions[i]["tidal_event_datetime"] - now
            next_height = round(next_predictions[i]["tidal_event"].height, 1)

            hours, rem = divmod(time_to_next_tide.seconds, 3600)
            minutes, seconds = divmod(rem, 60)

            if next_predictions[i]["tidal_event"].event_type == "HighWater":
                self._attrs[f"next_high_tide_in"] = f"{hours}h {minutes}m"
                self._attrs[f"next_high_tide_height"] = f"{next_height}m"
            else:
                self._attrs[f"next_low_tide_in"] = f"{hours}h {minutes}m"
                self._attrs[f"next_low_tide_height"] = f"{next_height}m"

        return self._attrs

    def get_next_predictions(self) -> [{datetime, TidalEvent}]:
        now = datetime.utcnow()
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
        now = datetime.utcnow()

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

                    # Keep only the last two events and all future ones
                    self._data = [
                        {
                            "tidal_event_datetime": datetime(2021, 4, 7, 10, 8),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-07T10:08:00",
                                height=6.051584390821417,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 7, 16, 26),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-07T16:26:00",
                                height=1.6336545919687804,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 7, 22, 51),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-07T22:51:00",
                                height=5.8651614615040275,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 8, 5, 33),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-08T05:33:00",
                                height=1.0709444743299135,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 8, 11, 28),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-08T11:28:00",
                                height=6.378397962953322,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 8, 17, 51),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-08T17:51:00",
                                height=1.2901730764333224,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 8, 23, 59),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-08T23:59:00",
                                height=6.272647633742875,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 9, 6, 41),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-09T06:41:00",
                                height=0.655615908077814,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 9, 12, 28),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-09T12:28:00",
                                height=6.718895418850187,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 9, 18, 50),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-09T18:50:00",
                                height=1.0112565033254173,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 10, 0, 49),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-10T00:49:00",
                                height=6.59042465022251,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 10, 7, 30),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-10T07:30:00",
                                height=0.4532243821894268,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 10, 13, 13),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-10T13:13:00",
                                height=6.875253173186719,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 10, 19, 38),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-10T19:38:00",
                                height=0.8788238222707145,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 11, 1, 30),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-11T01:30:00",
                                height=6.76072016878396,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 11, 8, 10),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-11T08:10:00",
                                height=0.4430852759969102,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 11, 13, 51),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-11T13:51:00",
                                height=6.889346595329482,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 11, 20, 18),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-11T20:18:00",
                                height=0.8285890084888763,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 12, 2, 4),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-12T02:04:00",
                                height=6.8708468180737805,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 12, 8, 43),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-12T08:43:00",
                                height=0.5037995107343224,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 12, 14, 24),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-12T14:24:00",
                                height=6.870998125223708,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 12, 20, 54),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-12T20:54:00",
                                height=0.7893814535251917,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 13, 2, 35),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-13T02:35:00",
                                height=6.98267985753056,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 13, 9, 11),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-13T09:11:00",
                                height=0.5507882745489687,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 13, 14, 53),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-13T14:53:00",
                                height=6.865598028368006,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 13, 21, 26),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-13T21:26:00",
                                height=0.7484565884291392,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 7, 10, 8),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-07T10:08:00",
                                height=6.051584390821417,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 7, 16, 26),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-07T16:26:00",
                                height=1.6336545919687804,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 7, 22, 51),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-07T22:51:00",
                                height=5.8651614615040275,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 8, 5, 33),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-08T05:33:00",
                                height=1.0709444743299135,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 8, 11, 28),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-08T11:28:00",
                                height=6.378397962953322,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 8, 17, 51),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-08T17:51:00",
                                height=1.2901730764333224,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 8, 23, 59),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-08T23:59:00",
                                height=6.272647633742875,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 9, 6, 41),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-09T06:41:00",
                                height=0.655615908077814,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 9, 12, 28),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-09T12:28:00",
                                height=6.718895418850187,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 9, 18, 50),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-09T18:50:00",
                                height=1.0112565033254173,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 10, 0, 49),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-10T00:49:00",
                                height=6.59042465022251,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 10, 7, 30),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-10T07:30:00",
                                height=0.4532243821894268,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 10, 13, 13),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-10T13:13:00",
                                height=6.875253173186719,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 10, 19, 38),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-10T19:38:00",
                                height=0.8788238222707145,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 11, 1, 30),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-11T01:30:00",
                                height=6.76072016878396,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 11, 8, 10),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-11T08:10:00",
                                height=0.4430852759969102,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 11, 13, 51),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-11T13:51:00",
                                height=6.889346595329482,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 11, 20, 18),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-11T20:18:00",
                                height=0.8285890084888763,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 12, 2, 4),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-12T02:04:00",
                                height=6.8708468180737805,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 12, 8, 43),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-12T08:43:00",
                                height=0.5037995107343224,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 12, 14, 24),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-12T14:24:00",
                                height=6.870998125223708,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 12, 20, 54),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-12T20:54:00",
                                height=0.7893814535251917,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 13, 2, 35),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-13T02:35:00",
                                height=6.98267985753056,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 13, 9, 11),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-13T09:11:00",
                                height=0.5507882745489687,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 13, 14, 53),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-13T14:53:00",
                                height=6.865598028368006,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 13, 21, 26),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-13T21:26:00",
                                height=0.7484565884291392,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 6, 10, 8),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-07T10:08:00",
                                height=6.051584390821417,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 6, 16, 26),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-07T16:26:00",
                                height=1.6336545919687804,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 5, 10, 8),
                            "tidal_event": TidalEvent(
                                event_type="HighWater",
                                date_time="2021-04-07T10:08:00",
                                height=6.051584390821417,
                            ),
                        },
                        {
                            "tidal_event_datetime": datetime(2021, 4, 5, 16, 26),
                            "tidal_event": TidalEvent(
                                event_type="LowWater",
                                date_time="2021-04-07T16:26:00",
                                height=1.6336545919687804,
                            ),
                        },
                    ]

                    # Stack Overflow voodoo to get distinct events
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