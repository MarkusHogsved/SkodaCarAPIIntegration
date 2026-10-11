"""Config flow tests."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.skoda_car_api.const import CONF_VIN, DOMAIN

from .conftest import API_KEY, VEHICLE_URL, VIN, rate_headers


async def test_user_flow(hass: HomeAssistant, mock_api: AiohttpClientMocker) -> None:
    """A valid key and VIN create an entry titled after the vehicle."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": f" {API_KEY} ", CONF_VIN: VIN.lower()}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Elroq (ABC 123)"
    assert result["data"] == {"api_key": API_KEY, CONF_VIN: VIN}
    assert result["result"].unique_id == VIN


async def test_invalid_vin(hass: HomeAssistant) -> None:
    """A malformed VIN is rejected without calling the API."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": API_KEY, CONF_VIN: "ABC"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_VIN: "invalid_vin"}


async def test_key_not_authorized(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 403 is reported on the form."""
    aioclient_mock.get(
        VEHICLE_URL,
        status=403,
        json={
            "type": "https://public.api.connect.skoda-auto.cz/problems/api-key-not-authorized",
            "status": 403,
        },
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": API_KEY, CONF_VIN: VIN}
    )
    assert result["errors"] == {"base": "key_not_authorized"}


async def test_key_expired(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An expired key gets its own message."""
    aioclient_mock.get(
        VEHICLE_URL,
        status=401,
        json={
            "type": "https://public.api.connect.skoda-auto.cz/problems/api-key-expired",
            "status": 401,
        },
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": API_KEY, CONF_VIN: VIN}
    )
    assert result["errors"] == {"base": "key_expired"}


async def test_already_configured(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AiohttpClientMocker
) -> None:
    """The same VIN cannot be added twice."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": API_KEY, CONF_VIN: VIN}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_replaces_key(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    vehicle_payload: dict[str, Any],
) -> None:
    """Reconfigure swaps the key and reloads."""
    aioclient_mock.get(VEHICLE_URL, json=vehicle_payload, headers=rate_headers())
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": "new-key"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data["api_key"] == "new-key"


async def test_options(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AiohttpClientMocker
) -> None:
    """Options are stored."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "interval_plugged_in": 5,
            "interval_idle": 30,
            "quota_reserve": 3,
            "climate_without_external_power": False,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options["interval_idle"] == 30
