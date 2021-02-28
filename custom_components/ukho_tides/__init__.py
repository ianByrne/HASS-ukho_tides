import asyncio
import logging
import datetime

from .admiraltyuktidalapi import (
    AdmiraltyUKTidalApi,
    ApiError,
    InvalidApiKeyError,
    ApiQuotaExceededError,
    TooManyRequestsError,
    StationNotFoundError,
)
from .const import (
    DOMAIN,
    COORDINATOR,
    UNDO_UPDATE_LISTENER,
    CONF_STATIONS,
    CONF_STATION_ID,
    CONF_STATION_NAME,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.const import CONF_API_KEY

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup(hass: HomeAssistant, config: dict):
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})

    # coordinator = AdmiraltyUKTidalApiDataUpdateCoordinator(
    #     hass, admiraltyUKTidalApi, station_id
    # )

    # if not coordinator.last_update_success:
    #     raise ConfigEntryNotReady

    # undo_listener = entry.add_update_listener(update_listener)

    # hass.data[DOMAIN][entry.entry_id] = {
    #     COORDINATOR: coordinator,
    #     UNDO_UPDATE_LISTENER: undo_listener,
    # }

    hass.data[DOMAIN][entry.entry_id] = entry.data

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