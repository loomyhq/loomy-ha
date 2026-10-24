"""Fixtures for the Loomy tests."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import CONF_HOST

from custom_components.loomy.const import DOMAIN

from . import HOST, URL, load_telegram


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow loading custom integrations in every test."""


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Return a snapshot assertion that serializes Home Assistant objects."""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry for a meter at HOST."""
    return MockConfigEntry(
        domain=DOMAIN, title=HOST, data={CONF_HOST: HOST}, entry_id="loomy_test"
    )


@pytest.fixture
def mock_meter(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Serve the full telegram, with a gas and water meter, at the meter's URL."""
    aioclient_mock.get(URL, text=load_telegram("telegram"))
    return aioclient_mock
