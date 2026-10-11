"""Fixtures for Skoda Car API tests."""

from __future__ import annotations

from collections.abc import Generator
import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.skoda_car_api.const import API_BASE_URL, CONF_VIN, DOMAIN

VIN = "TMBJB9NY5RF999999"
API_KEY = "test-key"
VEHICLE_URL = f"{API_BASE_URL}/vehicles/{VIN}"

_FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "vehicle.json").read_text())


def rate_headers(remaining: int = 15, reset: int = 1800) -> dict[str, str]:
    """Return typical response headers."""
    return {
        "RateLimit-Limit": "20",
        "RateLimit-Remaining": str(remaining),
        "RateLimit-Reset": str(reset),
        "X-API-Key-Expires-At": "2027-04-01T00:00:00Z",
    }


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> Generator[None]:
    """Enable custom integrations."""
    yield


@pytest.fixture
def vehicle_payload() -> dict[str, Any]:
    """Return a fresh copy of the vehicle payload."""
    return copy.deepcopy(_FIXTURE)


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Elroq (ABC 123)",
        unique_id=VIN,
        data={"api_key": API_KEY, CONF_VIN: VIN},
    )


@pytest.fixture
def mock_api(
    aioclient_mock: AiohttpClientMocker, vehicle_payload: dict[str, Any]
) -> AiohttpClientMocker:
    """Mock a healthy API."""
    aioclient_mock.get(VEHICLE_URL, json=vehicle_payload, headers=rate_headers())
    return aioclient_mock
