"""Test the Loomy config flow."""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

from aiohttp import ClientError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.loomy.const import DOMAIN

from . import HOST, URL, load_telegram


@pytest.fixture(autouse=True)
def mock_setup_entry() -> Generator[AsyncMock]:
    """Skip setting up the integration when the flow creates an entry."""
    with patch(
        "custom_components.loomy.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup


async def test_user_flow(
    hass: HomeAssistant, mock_meter: AiohttpClientMocker, mock_setup_entry: AsyncMock
) -> None:
    """Test configuring a reachable meter creates an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == HOST
    assert result["data"] == {CONF_HOST: HOST}
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        {"exc": ClientError},
        {"exc": TimeoutError},
        {"status": 500},
        {"text": "Not a telegram"},
    ],
)
async def test_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, response: dict[str, Any]
) -> None:
    """Test an unreachable or unreadable meter shows an error, then recovers."""
    aioclient_mock.get(URL, **response)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, text=load_telegram("telegram"))
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_already_configured(
    hass: HomeAssistant,
    mock_meter: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test a meter cannot be configured twice."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
