"""Coordinator for the Loomy integration."""

from datetime import timedelta
import logging

from aiohttp import ClientError, ClientTimeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .p1 import P1ParseError, P1Telegram, parse_telegram

_LOGGER = logging.getLogger(__name__)

type LoomyConfigEntry = ConfigEntry[LoomyCoordinator]

# Everything that can go wrong while fetching a telegram from the meter.
FETCH_ERRORS = (ClientError, TimeoutError, P1ParseError)


async def async_fetch(hass: HomeAssistant, host: str) -> P1Telegram:
    """Fetch and parse the current P1 telegram from the meter.

    Raises one of FETCH_ERRORS when that fails.
    """
    session = async_get_clientsession(hass)
    async with session.get(
        f"http://{host}/raw", timeout=ClientTimeout(total=5)
    ) as resp:
        resp.raise_for_status()
        return parse_telegram(await resp.text())


class LoomyCoordinator(DataUpdateCoordinator[P1Telegram]):
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

    async def _async_update_data(self) -> P1Telegram:
        """Fetch data from the meter."""
        try:
            return await async_fetch(self.hass, self.config_entry.data[CONF_HOST])
        except FETCH_ERRORS as err:
            raise UpdateFailed(f"Error communicating with meter: {err}") from err
