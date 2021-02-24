import asyncio
import logging
import datetime

from async_timeout import timeout
from aiohttp.client_exceptions import ClientConnectorError

from .ukhotidepredictions import UkhoTidePredictions, ApiError, InvalidApiKeyError
from .ukhotidepredictions.const import CONF_STATION_ID
from .const import DOMAIN, COORDINATOR, UNDO_UPDATE_LISTENER

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.const import CONF_API_KEY

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup(hass: HomeAssistant, config: dict):
    hass.data.setdefault(DOMAIN, {})

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    api_key = entry.data[CONF_API_KEY]
    station_id = entry.data[CONF_STATION_ID]
    station_name = entry.title

    websession = async_get_clientsession(hass)

    coordinator = UkhoTidePredictionsDataUpdateCoordinator(
        station_name, hass, websession, api_key, station_id
    )
    await coordinator.async_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    undo_listener = entry.add_update_listener(update_listener)

    hass.data[DOMAIN][entry.entry_id] = {
        COORDINATOR: coordinator,
        UNDO_UPDATE_LISTENER: undo_listener,
    }

    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def update_listener(hass, config_entry):
    await hass.config_entries.async_reload(config_entry.entry_id)


class UkhoTidePredictionsDataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, name, hass, session, api_key, station_id):
        self.ukhotidepredictions = UkhoTidePredictions(
            api_key, session, station_id, name
        )
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
                    self._data = await self.ukhotidepredictions.async_get_tidal_events()
            except (
                ApiError,
                ClientConnectorError,
                InvalidApiKeyError,
            ) as error:
                raise UpdateFailed(error) from error

            self._last_download_datetime = now

        return self._data

    @property
    def station_id(self):
        return self.ukhotidepredictions.station_id

    @property
    def station_name(self):
        return self.ukhotidepredictions.station_name