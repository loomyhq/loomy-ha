"""Tests for the Loomy integration."""

from pathlib import Path

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant

HOST = "192.168.4.25"
URL = f"http://{HOST}/raw"


def load_telegram(name: str) -> str:
    """Return a telegram from the fixtures directory."""
    return (Path(__file__).parent / "fixtures" / f"{name}.txt").read_text()


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the integration from a config entry."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
