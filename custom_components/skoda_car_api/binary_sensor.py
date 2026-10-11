"""Binary sensors for the Skoda Car API integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SkodaConfigEntry, VehicleData
from .entity import SkodaEntity

PARALLEL_UPDATES = 0


def _map(value: Any, on: str, off: str | tuple[str, ...]) -> bool | None:
    """Map an API enum to on/off; anything else (UNKNOWN, missing) is None."""
    if value == on:
        return True
    if value == off or (isinstance(off, tuple) and value in off):
        return False
    return None


@dataclass(frozen=True, kw_only=True)
class SkodaBinarySensorDescription(BinarySensorEntityDescription):
    """Binary sensor description."""

    value_fn: Callable[[VehicleData], bool | None]
    exists_fn: Callable[[VehicleData], bool] = lambda _: True


BINARY_SENSORS: tuple[SkodaBinarySensorDescription, ...] = (
    SkodaBinarySensorDescription(
        key="plugged_in",
        translation_key="plugged_in",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda d: d.plugged_in,
        exists_fn=lambda d: d.has_part("charging"),
    ),
    SkodaBinarySensorDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda d: (
            None
            if (s := d.get("charging", "status", "state")) is None
            else s == "CHARGING"
        ),
        exists_fn=lambda d: d.has_part("charging"),
    ),
    SkodaBinarySensorDescription(
        key="charging_cable_lock",
        translation_key="charging_cable_lock",
        device_class=BinarySensorDeviceClass.LOCK,
        # Lock device class: on means unlocked
        value_fn=lambda d: _map(
            d.get("charging", "status", "plugLockState"), "UNLOCKED", "LOCKED"
        ),
        exists_fn=lambda d: d.has_part("charging"),
    ),
    SkodaBinarySensorDescription(
        key="at_saved_location",
        translation_key="at_saved_location",
        device_class=BinarySensorDeviceClass.PRESENCE,
        value_fn=lambda d: d.get("charging", "isVehicleInSavedLocation"),
        exists_fn=lambda d: d.has_part("charging"),
    ),
    SkodaBinarySensorDescription(
        key="lock",
        translation_key="lock",
        device_class=BinarySensorDeviceClass.LOCK,
        value_fn=lambda d: _map(d.get("status", "overall", "locked"), "NO", "YES"),
        exists_fn=lambda d: d.has_part("status"),
    ),
    SkodaBinarySensorDescription(
        key="doors",
        translation_key="doors",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda d: _map(d.get("status", "overall", "doors"), "OPEN", "CLOSED"),
        exists_fn=lambda d: d.has_part("status"),
    ),
    SkodaBinarySensorDescription(
        key="windows",
        translation_key="windows",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_fn=lambda d: _map(
            d.get("status", "overall", "windows"), "OPEN", "CLOSED"
        ),
        exists_fn=lambda d: (
            d.has_part("status")
            and d.get("status", "overall", "windows") != "UNSUPPORTED"
        ),
    ),
    SkodaBinarySensorDescription(
        key="trunk",
        translation_key="trunk",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=lambda d: _map(d.get("status", "detail", "trunk"), "OPEN", "CLOSED"),
        exists_fn=lambda d: d.has_part("status"),
    ),
    SkodaBinarySensorDescription(
        key="bonnet",
        translation_key="bonnet",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=lambda d: _map(d.get("status", "detail", "bonnet"), "OPEN", "CLOSED"),
        exists_fn=lambda d: d.has_part("status"),
    ),
    SkodaBinarySensorDescription(
        key="sunroof",
        translation_key="sunroof",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_fn=lambda d: _map(d.get("status", "detail", "sunroof"), "OPEN", "CLOSED"),
        exists_fn=lambda d: d.get("status", "detail", "sunroof") in ("OPEN", "CLOSED"),
    ),
    SkodaBinarySensorDescription(
        key="lights",
        translation_key="lights",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_fn=lambda d: _map(d.get("status", "overall", "lights"), "ON", "OFF"),
        exists_fn=lambda d: d.has_part("status"),
    ),
    SkodaBinarySensorDescription(
        key="in_motion",
        translation_key="in_motion",
        device_class=BinarySensorDeviceClass.MOVING,
        value_fn=lambda d: _map(
            d.get("parkingPosition", "state"), "IN_MOTION", "PARKED"
        ),
        exists_fn=lambda d: d.has_part("parkingPosition"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        SkodaBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
        if description.exists_fn(coordinator.data)
    )


class SkodaBinarySensor(SkodaEntity, BinarySensorEntity):
    """Vehicle binary sensor."""

    entity_description: SkodaBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data)
