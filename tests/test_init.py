"""Setup, polling and command tests."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.skoda_car_api.const import DOMAIN

from .conftest import VEHICLE_URL, rate_headers


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_entities(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AiohttpClientMocker
) -> None:
    """Entities reflect the payload; unsupported parts are skipped."""
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    assert hass.states.get("sensor.elroq_battery_level").state == "81"
    assert hass.states.get("sensor.elroq_electric_range").state == "312.0"
    assert hass.states.get("sensor.elroq_charging_state").state == "conserving"
    assert hass.states.get("sensor.elroq_odometer").state == "4321"
    assert hass.states.get("binary_sensor.elroq_charging_cable").state == "on"
    assert hass.states.get("binary_sensor.elroq_charging").state == "off"
    assert hass.states.get("binary_sensor.elroq_lock").state == "off"  # locked
    assert hass.states.get("binary_sensor.elroq_doors").state == "off"
    assert hass.states.get("number.elroq_charging_limit").state == "80"
    assert hass.states.get("switch.elroq_charging").state == "off"
    assert hass.states.get("switch.elroq_air_conditioning").state == "off"
    assert (
        hass.states.get("device_tracker.elroq_parking_position").attributes["latitude"]
        == 57.87
    )
    assert hass.states.get("sensor.elroq_api_requests_remaining").state == "15"
    assert hass.states.get("sensor.elroq_api_key_expires").state.startswith(
        "2027-04-01"
    )

    select = hass.states.get("select.elroq_charge_mode")
    assert select.state == "manual"
    assert select.attributes["options"] == [
        "manual",
        "timer",
        "preferred_charging_times",
    ]

    # Not reported for this vehicle
    assert hass.states.get("sensor.elroq_fuel_level") is None
    assert hass.states.get("binary_sensor.elroq_sunroof") is None
    assert hass.states.get("switch.elroq_active_ventilation") is None


async def test_interval_plugged_in(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AiohttpClientMocker
) -> None:
    """Polls faster while plugged in."""
    await _setup(hass, config_entry)
    assert config_entry.runtime_data.update_interval == timedelta(minutes=6)


async def test_interval_idle(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    vehicle_payload: dict[str, Any],
) -> None:
    """Polls slower when unplugged."""
    status = vehicle_payload["vehicle"]["charging"]["status"]
    status["plugConnectionState"] = "DISCONNECTED"
    status["state"] = "CONNECT_CABLE"
    aioclient_mock.get(VEHICLE_URL, json=vehicle_payload, headers=rate_headers())
    await _setup(hass, config_entry)
    assert config_entry.runtime_data.update_interval == timedelta(minutes=20)


async def test_interval_backs_off_when_quota_low(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    vehicle_payload: dict[str, Any],
) -> None:
    """Waits for the quota window when only the command reserve is left."""
    aioclient_mock.get(
        VEHICLE_URL, json=vehicle_payload, headers=rate_headers(remaining=3, reset=1500)
    )
    await _setup(hass, config_entry)
    interval = config_entry.runtime_data.update_interval
    assert timedelta(seconds=1500) < interval <= timedelta(seconds=1515)


async def test_expired_key_starts_reauth(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A 401 during setup triggers reauthentication."""
    aioclient_mock.get(
        VEHICLE_URL,
        status=401,
        json={
            "type": "https://public.api.connect.skoda-auto.cz/problems/api-key-expired"
        },
    )
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_rate_limited_setup_retries(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A 429 during setup is retried later."""
    aioclient_mock.get(
        VEHICLE_URL,
        status=429,
        headers={"Retry-After": "600"},
        json={
            "type": "https://public.api.connect.skoda-auto.cz/problems/rate-limit-exceeded"
        },
    )
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_key_expiry_issue(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    vehicle_payload: dict[str, Any],
) -> None:
    """A repair issue is raised when the key is about to expire."""
    headers = rate_headers()
    headers["X-API-Key-Expires-At"] = (dt_util.utcnow() + timedelta(days=3)).isoformat()
    aioclient_mock.get(VEHICLE_URL, json=vehicle_payload, headers=headers)
    await _setup(hass, config_entry)
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"api_key_expiring_{config_entry.entry_id}"
    )
    assert issue is not None


async def test_switch_starts_charging(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AiohttpClientMocker
) -> None:
    """Turning on the charging switch posts the command and shows it as on."""
    mock_api.post(f"{VEHICLE_URL}/charging/start", status=202, headers=rate_headers(14))
    await _setup(hass, config_entry)

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.elroq_charging"}, blocking=True
    )
    assert hass.states.get("switch.elroq_charging").state == "on"
    assert any(
        call[0] == "POST" and str(call[1]).endswith("/charging/start")
        for call in mock_api.mock_calls
    )


async def test_charging_limit_rounds_to_ten(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AiohttpClientMocker
) -> None:
    """The limit is sent in steps of 10."""
    mock_api.put(f"{VEHICLE_URL}/charging/limit", status=202)
    await _setup(hass, config_entry)

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.elroq_charging_limit", "value": 90},
        blocking=True,
    )
    call = next(c for c in mock_api.mock_calls if c[0] == "PUT")
    assert call[2] == {"targetStateOfChargeInPercent": 90}
    assert hass.states.get("number.elroq_charging_limit").state == "90"


async def test_command_error_is_raised(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AiohttpClientMocker
) -> None:
    """A rejected command surfaces as an error and leaves the state unchanged."""
    mock_api.post(
        f"{VEHICLE_URL}/air-conditioning/start",
        status=429,
        headers={"Retry-After": "120"},
        json={
            "type": "https://public.api.connect.skoda-auto.cz/problems/vehicle-not-accepting-requests"
        },
    )
    await _setup(hass, config_entry)

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.elroq_air_conditioning"},
            blocking=True,
        )
    assert err.value.translation_key == "vehicle_busy"
    assert hass.states.get("switch.elroq_air_conditioning").state == "off"


async def test_unload(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AiohttpClientMocker
) -> None:
    """The entry unloads cleanly."""
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_charging_details_when_not_charging(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    vehicle_payload: dict[str, Any],
) -> None:
    """No finish time unless charging; current setting falls back to the enum."""
    settings = vehicle_payload["vehicle"]["charging"]["settings"]
    del settings["maxChargeCurrentAcAmpere"]
    vehicle_payload["vehicle"]["charging"]["status"]["fullyChargedAt"] = (
        "2026-10-10T18:09:31Z"
    )
    aioclient_mock.get(VEHICLE_URL, json=vehicle_payload, headers=rate_headers())
    await _setup(hass, config_entry)

    assert hass.states.get("sensor.elroq_fully_charged_at").state == "unknown"
    assert hass.states.get("sensor.elroq_max_ac_charging_current") is None
    assert hass.states.get("sensor.elroq_ac_charging_current").state == "maximum"
