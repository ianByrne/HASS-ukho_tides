import logging
import voluptuous as vol
import asyncio

from async_timeout import timeout
from aiohttp import ClientError
from aiohttp.client_exceptions import ClientConnectorError

from .ukhotidepredictions import UkhoTidePredictions, ApiError, InvalidApiKeyError
from .ukhotidepredictions.const import CONF_STATION_ID
from .const import DOMAIN

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            websession = async_get_clientsession(self.hass)

            try:
                async with timeout(10):
                    ukhoTidePredictions = UkhoTidePredictions(
                        user_input[CONF_API_KEY],
                        websession,
                        user_input[CONF_STATION_ID],
                    )
                    await ukhoTidePredictions.async_get_station_name()

            except (ApiError, ClientConnectorError, asyncio.TimeoutError, ClientError):
                errors["base"] = "cannot_connect"
            except InvalidApiKeyError:
                errors[CONF_API_KEY] = "invalid_api_key"

            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            else:
                await self.async_set_unique_id(
                    user_input[CONF_STATION_ID], raise_on_progress=False
                )

                return self.async_create_entry(
                    title=ukhoTidePredictions.station_name, data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): str,
                    vol.Required(CONF_STATION_ID): str,
                }
            ),
            errors=errors,
        )