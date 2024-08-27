import asyncio
from copy import deepcopy
import logging
from typing import Any, Dict

from aiohttp import ClientError
from aiohttp.client_exceptions import ClientConnectorError
from async_timeout import timeout
from ukhotides import ApiError, ApiLevel, InvalidApiKeyError, Station, UkhoTides
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_API_LEVEL,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_STATION_OFFSET_HIGH,
    CONF_STATION_OFFSET_LOW,
    CONF_STATIONS,
    DEFAULT_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)

            try:
                async with timeout(10):
                    ukhotides = UkhoTides(
                        session,
                        user_input[CONF_API_KEY],
                        ApiLevel[user_input[CONF_API_LEVEL]],
                    )

                    stations = await ukhotides.async_get_stations()

                    self._all_stations = {s.id: s.name for s in stations}
                    self._stations_map = {s.id: s for s in stations}

            except (ApiError, ClientConnectorError, asyncio.TimeoutError, ClientError):
                errors["base"] = "cannot_connect"
            except InvalidApiKeyError:
                errors[CONF_API_KEY] = "invalid_api_key"

            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            else:
                self.data = user_input
                self.data[CONF_STATIONS] = []

                return await self.async_step_station()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_API_LEVEL, default=ApiLevel.Discovery.name
                    ): vol.In(
                        [
                            ApiLevel.Discovery.name,
                            ApiLevel.Foundation.name,
                            ApiLevel.Premium.name,
                        ]
                    ),
                    vol.Required(CONF_API_KEY): str,
                }
            ),
            errors=errors,
        )

    async def async_step_station(self, user_input=None):
        errors = {}

        if user_input is not None:
            if not user_input[CONF_STATIONS]:
                return self.async_create_entry(title=DEFAULT_NAME, data=self.data)

            for station_id in user_input[CONF_STATIONS]:
                station = self._stations_map[station_id]
                self.data[CONF_STATIONS].append(
                    {CONF_STATION_ID: station.id, CONF_STATION_NAME: station.name}
                )

            return await self.async_step_station_settings()

        return self.async_show_form(
            step_id="station",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_STATIONS): cv.multi_select(self._all_stations),
                }
            ),
            errors=errors,
        )

    async def async_step_station_settings(self, user_input=None):
        errors = {}

        if user_input is not None:
            for key in user_input:
                station_id = key[key.rindex("_") + 1 :]

                if "station_name" in key:
                    for station in self.data[CONF_STATIONS]:
                        if station[CONF_STATION_ID] == station_id:
                            station[CONF_STATION_NAME] = user_input[key]
                            break

                if "station_offset_high" in key:
                    for station in self.data[CONF_STATIONS]:
                        if station[CONF_STATION_ID] == station_id:
                            station[CONF_STATION_OFFSET_HIGH] = user_input[key]
                            break

                if "station_offset_low" in key:
                    for station in self.data[CONF_STATIONS]:
                        if station[CONF_STATION_ID] == station_id:
                            station[CONF_STATION_OFFSET_LOW] = user_input[key]
                            break

            return self.async_create_entry(title=DEFAULT_NAME, data=self.data)

        selected_stations = {}

        for station in self.data[CONF_STATIONS]:
            selected_stations.update(
                {
                    vol.Required(
                        CONF_STATION_NAME + "_" + station[CONF_STATION_ID],
                        default=station[CONF_STATION_NAME],
                    ): str,
                    vol.Required(
                        CONF_STATION_OFFSET_HIGH + "_" + station[CONF_STATION_ID],
                        default=0,
                    ): int,
                    vol.Required(
                        CONF_STATION_OFFSET_LOW + "_" + station[CONF_STATION_ID],
                        default=0,
                    ): int,
                }
            )

        return self.async_show_form(
            step_id="station_settings",
            data_schema=vol.Schema(selected_stations),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        errors: Dict[str, str] = {}

        session = async_get_clientsession(self.hass)
        self.data = self.hass.data[DOMAIN][self.config_entry.entry_id]

        try:
            async with timeout(10):
                api_key = self.data[CONF_API_KEY]

                ukhotides = UkhoTides(
                    session,
                    api_key,
                )

                # Get all stations
                stations = await ukhotides.async_get_stations()

                all_stations = {s.id: s.name for s in stations}
                stations_map = {s.id: s for s in stations}

        except (ApiError, ClientConnectorError, asyncio.TimeoutError, ClientError):
            errors["base"] = "cannot_connect"
        except InvalidApiKeyError:
            errors[CONF_API_KEY] = "invalid_api_key"

        except Exception:
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"

        else:
            # Get currently registered entities
            entity_registry = er.async_get(self.hass)
            registered_entities = er.async_entries_for_config_entry(
                entity_registry, self.config_entry.entry_id
            )

            # Default values for the multi-select
            registered_stations_unique_to_entity = {
                e.unique_id: e.entity_id for e in registered_entities
            }

            registered_stations_entity_to_unique = {
                e.entity_id: e.unique_id for e in registered_entities
            }

            if user_input is not None:
                # Remove any unchecked stations
                removed_unique_ids = [
                    unique_id
                    for unique_id in registered_stations_entity_to_unique.values()
                    if unique_id not in user_input[CONF_STATIONS]
                ]

                for unique_id in removed_unique_ids:
                    # Unregister from HA
                    entity_registry.async_remove(
                        registered_stations_unique_to_entity[unique_id]
                    )

                # Add any newly checked stations
                self.updated_stations = []
                if user_input.get(CONF_STATIONS):
                    for entry_unique_id in user_input[CONF_STATIONS]:
                        s = next(
                            (
                                item
                                for item in self.data[CONF_STATIONS]
                                if item[CONF_STATION_ID] == entry_unique_id
                            ),
                            None,
                        )

                        if s is not None:
                            self.updated_stations.append(s)
                        else:
                            s = stations_map[entry_unique_id]

                            self.updated_stations.append(
                                {
                                    CONF_STATION_ID: s.id,
                                    CONF_STATION_NAME: s.name,
                                    CONF_STATION_OFFSET_HIGH: 0,
                                    CONF_STATION_OFFSET_LOW: 0,
                                }
                            )

                if not errors:
                    if not self.updated_stations:
                        return self.async_create_entry(
                            title="",
                            data={CONF_STATIONS: self.updated_stations},
                        )
                    else:
                        return await self.async_step_station_settings()

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_STATIONS,
                    default=list(registered_stations_unique_to_entity.keys()),
                ): cv.multi_select(all_stations),
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=options_schema, errors=errors
        )

    async def async_step_station_settings(self, user_input=None):
        errors = {}

        if user_input is not None:
            for key in user_input:
                station_id = key[key.rindex("_") + 1 :]

                if "station_name" in key:
                    for station in self.updated_stations:
                        if station[CONF_STATION_ID] == station_id:
                            station[CONF_STATION_NAME] = user_input[key]
                            break

                if "station_offset_high" in key:
                    for station in self.updated_stations:
                        if station[CONF_STATION_ID] == station_id:
                            station[CONF_STATION_OFFSET_HIGH] = user_input[key]
                            break

                if "station_offset_low" in key:
                    for station in self.updated_stations:
                        if station[CONF_STATION_ID] == station_id:
                            station[CONF_STATION_OFFSET_LOW] = user_input[key]
                            break

            return self.async_create_entry(
                title="",
                data={CONF_STATIONS: self.updated_stations},
            )

        selected_stations = {}

        for station in self.updated_stations:
            selected_stations.update(
                {
                    vol.Required(
                        CONF_STATION_NAME + "_" + station[CONF_STATION_ID],
                        default=station[CONF_STATION_NAME],
                    ): str,
                    vol.Required(
                        CONF_STATION_OFFSET_HIGH + "_" + station[CONF_STATION_ID],
                        default=(
                            station[CONF_STATION_OFFSET_HIGH]
                            if CONF_STATION_OFFSET_HIGH in station
                            else 0
                        ),
                    ): int,
                    vol.Required(
                        CONF_STATION_OFFSET_LOW + "_" + station[CONF_STATION_ID],
                        default=(
                            station[CONF_STATION_OFFSET_LOW]
                            if CONF_STATION_OFFSET_LOW in station
                            else 0
                        ),
                    ): int,
                }
            )

        return self.async_show_form(
            step_id="station_settings",
            data_schema=vol.Schema(selected_stations),
            errors=errors,
        )
