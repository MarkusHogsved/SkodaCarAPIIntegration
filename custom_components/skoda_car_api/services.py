"""Service actions for the Skoda Car API integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
import voluptuous as vol

from .const import (
    DOMAIN,
    OP_START_AIR_CONDITIONING,
    OP_START_AUXILIARY_HEATING,
    OP_STOP_AUXILIARY_HEATING,
)
from .coordinator import SkodaCoordinator

ATTR_DEVICE_ID = "device_id"
ATTR_TEMPERATURE = "temperature"
ATTR_WITHOUT_EXTERNAL_POWER = "without_external_power"
ATTR_SPIN = "spin"
ATTR_DURATION = "duration"
ATTR_START_MODE = "start_mode"

SERVICE_START_AIR_CONDITIONING = "start_air_conditioning"
SERVICE_START_AUXILIARY_HEATING = "start_auxiliary_heating"
SERVICE_STOP_AUXILIARY_HEATING = "stop_auxiliary_heating"

_TEMPERATURE = vol.All(vol.Coerce(float), vol.Range(min=16, max=30))

START_AIR_CONDITIONING_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Optional(ATTR_TEMPERATURE): _TEMPERATURE,
        vol.Optional(ATTR_WITHOUT_EXTERNAL_POWER): cv.boolean,
    }
)

START_AUXILIARY_HEATING_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_SPIN): vol.All(cv.string, vol.Match(r"^\d{4}$")),
        vol.Optional(ATTR_TEMPERATURE): _TEMPERATURE,
        vol.Optional(ATTR_DURATION): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
        vol.Optional(ATTR_START_MODE): vol.In(["heating", "ventilation"]),
    }
)

DEVICE_ONLY_SCHEMA = vol.Schema({vol.Required(ATTR_DEVICE_ID): cv.string})


def _coordinator(hass: HomeAssistant, device_id: str) -> SkodaCoordinator:
    device = dr.async_get(hass).async_get(device_id)
    if device is not None:
        for entry_id in device.config_entries:
            entry = hass.config_entries.async_get_entry(entry_id)
            if (
                entry is not None
                and entry.domain == DOMAIN
                and entry.state is ConfigEntryState.LOADED
            ):
                return entry.runtime_data
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="invalid_device",
        translation_placeholders={"device_id": device_id},
    )


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register service actions."""

    async def start_air_conditioning(call: ServiceCall) -> None:
        c = _coordinator(hass, call.data[ATTR_DEVICE_ID])
        temperature: Any = call.data.get(ATTR_TEMPERATURE, c.climate_temperature)
        await c.async_command(
            OP_START_AIR_CONDITIONING,
            lambda: c.client.start_air_conditioning(
                temperature, call.data.get(ATTR_WITHOUT_EXTERNAL_POWER)
            ),
        )

    async def start_auxiliary_heating(call: ServiceCall) -> None:
        c = _coordinator(hass, call.data[ATTR_DEVICE_ID])
        duration = call.data.get(ATTR_DURATION)
        mode = call.data.get(ATTR_START_MODE)
        await c.async_command(
            OP_START_AUXILIARY_HEATING,
            lambda: c.client.start_auxiliary_heating(
                call.data[ATTR_SPIN],
                call.data.get(ATTR_TEMPERATURE),
                duration * 60 if duration else None,
                mode.upper() if mode else None,
            ),
        )

    async def stop_auxiliary_heating(call: ServiceCall) -> None:
        c = _coordinator(hass, call.data[ATTR_DEVICE_ID])
        await c.async_command(
            OP_STOP_AUXILIARY_HEATING, lambda: c.client.stop_auxiliary_heating()
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_AIR_CONDITIONING,
        start_air_conditioning,
        schema=START_AIR_CONDITIONING_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_START_AUXILIARY_HEATING,
        start_auxiliary_heating,
        schema=START_AUXILIARY_HEATING_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_AUXILIARY_HEATING,
        stop_auxiliary_heating,
        schema=DEVICE_ONLY_SCHEMA,
    )
