"""Diagnostics for the Skoda Car API integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from .const import CONF_VIN
from .coordinator import SkodaConfigEntry

TO_REDACT = {
    CONF_API_KEY,
    CONF_VIN,
    "vin",
    "licensePlate",
    "renderUrl",
    "gpsCoordinates",
    "formattedAddress",
    "latitude",
    "longitude",
    "name",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SkodaConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    rl = coordinator.client.rate_limit
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "polling": {
            "update_interval_s": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
            "last_update_success": coordinator.last_update_success,
            "fetched_at": coordinator.data.fetched_at if coordinator.data else None,
            "last_command_at": coordinator.last_command_at,
        },
        "rate_limit": {
            "limit": rl.limit,
            "remaining": rl.remaining,
            "reset_at": rl.reset_at,
        },
        "key_expires_at": coordinator.client.key_expires_at,
        "vehicle": async_redact_data(
            coordinator.data.vehicle if coordinator.data else {}, TO_REDACT
        ),
        "errors": coordinator.data.errors if coordinator.data else [],
    }
