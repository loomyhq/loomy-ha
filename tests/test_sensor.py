"""Test the Loomy sensors."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    snapshot_platform,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.loomy.sensor import SENSORS

from . import URL, load_telegram, setup_integration


async def test_sensors(
    hass: HomeAssistant,
    mock_meter: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test every sensor against a snapshot, for a meter with both submeters."""
    await setup_integration(hass, mock_config_entry)

    assert len(hass.states.async_all("sensor")) == len(SENSORS)
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


async def test_values(
    hass: HomeAssistant,
    mock_meter: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the values that are derived rather than read from a register."""
    await setup_integration(hass, mock_config_entry)

    # Day plus night tariff.
    assert hass.states.get("sensor.loomy_energy_consumption").state == "358.023"
    assert hass.states.get("sensor.loomy_tariff").state == "day"
    # Home Assistant renders timestamps in UTC, the meter runs on CET.
    assert (
        hass.states.get("sensor.loomy_meter_time").state == "2024-01-15T13:30:00+00:00"
    )
    assert hass.states.get("sensor.loomy_text_message").state == "Hello"
    assert hass.states.get("sensor.loomy_gas").state == "123.456"
    assert hass.states.get("sensor.loomy_gas_meter_ean").state == "not set"

    # The most recent month of the history, which skips the garbage month.
    peak = hass.states.get("sensor.loomy_peak_demand_last_month")
    assert peak.state == "2.5"
    assert [month["value"] for month in peak.attributes["history"]] == [3.1, 2.5]


async def test_only_present_registers(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test only sensors for registers in the telegram are created."""
    aioclient_mock.get(URL, text=load_telegram("telegram_minimal"))
    await setup_integration(hass, mock_config_entry)

    # The meter time is in the telegram but garbage, so it has no sensor either.
    assert sorted(hass.states.async_entity_ids("sensor")) == [
        "sensor.loomy_energy_consumption",
        "sensor.loomy_energy_consumption_day",
        "sensor.loomy_energy_consumption_night",
        "sensor.loomy_power_consumption",
        "sensor.loomy_text_message",
    ]


async def test_register_disappears(
    hass: HomeAssistant,
    mock_meter: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a sensor becomes unavailable when its register leaves the telegram."""
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get("sensor.loomy_gas").state == "123.456"

    mock_meter.clear_requests()
    mock_meter.get(URL, text=load_telegram("telegram_minimal"))
    freezer.tick(timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.loomy_gas").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.loomy_energy_consumption").state == "358.023"


async def test_meter_unreachable(
    hass: HomeAssistant,
    mock_meter: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test all sensors become unavailable when the meter cannot be read."""
    await setup_integration(hass, mock_config_entry)

    mock_meter.clear_requests()
    mock_meter.get(URL, status=500)
    freezer.tick(timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.loomy_energy_consumption").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.loomy_gas").state == STATE_UNAVAILABLE
