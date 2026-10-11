"""Switches for the Skoda Car API integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ACTIVE_CLIMATE_STATES,
    CONF_CLIMATE_WITHOUT_EXTERNAL_POWER,
    DEFAULT_CLIMATE_WITHOUT_EXTERNAL_POWER,
    OP_START_ACTIVE_VENTILATION,
    OP_START_AIR_CONDITIONING,
    OP_START_CHARGING,
    OP_STOP_ACTIVE_VENTILATION,
    OP_STOP_AIR_CONDITIONING,
    OP_STOP_CHARGING,
)
from .coordinator import SkodaConfigEntry, SkodaCoordinator, VehicleData
from .entity import SkodaCommandEntity

PARALLEL_UPDATES = 1


def _charging_on(d: VehicleData) -> bool | None:
    state = d.get("charging", "status", "state")
    return None if state is None else state == "CHARGING"


def _climate_on(d: VehicleData) -> bool | None:
    state = d.get("airConditioning", "state")
    if not isinstance(state, str) or state in ("UNKNOWN", "UNSUPPORTED"):
        return None
    return state.lower() in ACTIVE_CLIMATE_STATES


def _ventilation_on(d: VehicleData) -> bool | None:
    state = d.get("activeVentilation", "state")
    if not isinstance(state, str) or state in ("UNKNOWN", "UNSUPPORTED"):
        return None
    return state != "OFF"


def _start_climate(c: SkodaCoordinator) -> Awaitable[None]:
    return c.client.start_air_conditioning(
        c.climate_temperature,
        c.config_entry.options.get(
            CONF_CLIMATE_WITHOUT_EXTERNAL_POWER, DEFAULT_CLIMATE_WITHOUT_EXTERNAL_POWER
        ),
    )


@dataclass(frozen=True, kw_only=True)
class SkodaSwitchDescription(SwitchEntityDescription):
    """Switch description."""

    part: str
    op_on: str
    op_off: str
    value_fn: Callable[[VehicleData], bool | None]
    on_fn: Callable[[SkodaCoordinator], Awaitable[None]]
    off_fn: Callable[[SkodaCoordinator], Awaitable[None]]


SWITCHES: tuple[SkodaSwitchDescription, ...] = (
    SkodaSwitchDescription(
        key="charging",
        translation_key="charging",
        part="charging",
        op_on=OP_START_CHARGING,
        op_off=OP_STOP_CHARGING,
        value_fn=_charging_on,
        on_fn=lambda c: c.client.start_charging(),
        off_fn=lambda c: c.client.stop_charging(),
    ),
    SkodaSwitchDescription(
        key="air_conditioning",
        translation_key="air_conditioning",
        part="airConditioning",
        op_on=OP_START_AIR_CONDITIONING,
        op_off=OP_STOP_AIR_CONDITIONING,
        value_fn=_climate_on,
        on_fn=_start_climate,
        off_fn=lambda c: c.client.stop_air_conditioning(),
    ),
    SkodaSwitchDescription(
        key="active_ventilation",
        translation_key="active_ventilation",
        part="activeVentilation",
        op_on=OP_START_ACTIVE_VENTILATION,
        op_off=OP_STOP_ACTIVE_VENTILATION,
        value_fn=_ventilation_on,
        on_fn=lambda c: c.client.start_active_ventilation(),
        off_fn=lambda c: c.client.stop_active_ventilation(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switches."""
    coordinator = entry.runtime_data
    async_add_entities(
        SkodaSwitch(coordinator, description)
        for description in SWITCHES
        if coordinator.data.has_part(description.part)
        and coordinator.supports(description.op_on)
    )


class SkodaSwitch(SkodaCommandEntity, SwitchEntity):
    """Start/stop switch for a remote operation."""

    entity_description: SkodaSwitchDescription

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self._resolve(self.entity_description.value_fn(self.coordinator.data))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start the operation."""
        desc = self.entity_description
        await self.coordinator.async_command(
            desc.op_on, lambda: desc.on_fn(self.coordinator)
        )
        self._set_pending(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop the operation."""
        desc = self.entity_description
        await self.coordinator.async_command(
            desc.op_off, lambda: desc.off_fn(self.coordinator)
        )
        self._set_pending(False)
