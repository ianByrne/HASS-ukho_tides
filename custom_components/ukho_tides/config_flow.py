import logging
import voluptuous as vol
import asyncio

from async_timeout import timeout
from aiohttp import ClientError
from aiohttp.client_exceptions import ClientConnectorError
from ukhotides import (
    UkhoTides,
    ApiError,
    InvalidApiKeyError,
)

from .const import (
    DOMAIN,
    CONF_STATIONS,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DEFAULT_NAME,
)

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

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
                    )

                    stations = await ukhotides.async_get_stations()

                    # self._stations = {}

                    # for s in stations:
                    #     self._stations.update(
                    #         {s["properties"]["Id"]: s["properties"]["Name"]}
                    #     )

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
                    vol.Required(CONF_API_KEY): str,
                }
            ),
            errors=errors,
        )

    async def async_step_station(self, user_input=None):
        errors = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)

            try:
                async with timeout(10):
                    ukhotides = UkhoTides(
                        session,
                        self.data[CONF_API_KEY],
                    )

                    station = await ukhotides.async_get_station(
                        user_input[CONF_STATION_ID]
                    )

            except (ApiError, ClientConnectorError, asyncio.TimeoutError, ClientError):
                errors["base"] = "cannot_connect"
            except InvalidApiKeyError:
                errors[CONF_API_KEY] = "invalid_api_key"

            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            else:
                self.data[CONF_STATIONS].append(
                    {
                        CONF_STATION_ID: user_input[CONF_STATION_ID],
                        CONF_STATION_NAME: user_input.get(
                            CONF_STATION_NAME, station.name
                        ),
                    }
                )

                if user_input.get("add_another", False):
                    return await self.async_step_station()

                return self.async_create_entry(title=DEFAULT_NAME, data=self.data)

        return self.async_show_form(
            step_id="station",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_ID): str,
                    vol.Optional(CONF_STATION_NAME): str,
                    vol.Optional("add_another"): cv.boolean,
                }
            ),
            errors=errors,
        )