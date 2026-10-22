"""Coordinator for the Loomy integration."""

from datetime import timedelta
import logging
from typing import Any

from aiohttp import ClientError, ClientTimeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

type LoomyConfigEntry = ConfigEntry[LoomyCoordinator]


async def async_fetch(hass: HomeAssistant, host: str) -> dict[str, Any]:
    """Fetch the current readings from the meter."""
    session = async_get_clientsession(hass)
    async with session.get(f"http://{host}/", timeout=ClientTimeout(total=5)) as resp:
        resp.raise_for_status()
        return await resp.json()


class LoomyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll the meter every second."""

    config_entry: LoomyConfigEntry

    def __init__(self, hass: HomeAssistant, entry: LoomyConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=1),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the meter."""
        try:
            return await async_fetch(self.hass, self.config_entry.data[CONF_HOST])
        except (ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Error communicating with meter: {err}") from err
