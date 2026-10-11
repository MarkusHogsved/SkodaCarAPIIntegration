"""Sensors for the Skoda Car API integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfLength,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import AIR_CONDITIONING_STATES, CHARGING_STATES
from .coordinator import SkodaConfigEntry, SkodaCoordinator, VehicleData
from .entity import SkodaEntity

PARALLEL_UPDATES = 0


def _ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is not None and parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return parsed


def _num(value: Any) -> float | int | None:
    return (
        value
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else None
    )


def _enum(value: Any, options: list[str]) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.lower()
    return value if value in options else None


def _meters_to_km(value: Any) -> float | None:
    v = _num(value)
    return round(v / 1000, 1) if v is not None else None


@dataclass(frozen=True, kw_only=True)
class SkodaSensorDescription(SensorEntityDescription):
    """Sensor description with value and presence callbacks."""

    value_fn: Callable[[SkodaCoordinator], Any]
    exists_fn: Callable[[VehicleData], bool] = lambda _: True


def _has(part: str) -> Callable[[VehicleData], bool]:
    return lambda data: data.has_part(part)


SENSORS: tuple[SkodaSensorDescription, ...] = (
    # Charging and battery
    SkodaSensorDescription(
        key="battery_level",
        translation_key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: _num(
            c.data.get("charging", "status", "battery", "stateOfChargeInPercent")
        ),
        exists_fn=_has("charging"),
    ),
    SkodaSensorDescription(
        key="electric_range",
        translation_key="electric_range",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda c: _meters_to_km(
            c.data.get(
                "charging", "status", "battery", "remainingCruisingRangeInMeters"
            )
        ),
        exists_fn=_has("charging"),
    ),
    SkodaSensorDescription(
        key="charging_power",
        translation_key="charging_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda c: _num(c.data.get("charging", "status", "chargePowerInKw")),
        exists_fn=_has("charging"),
    ),
    SkodaSensorDescription(
        key="charging_rate",
        translation_key="charging_rate",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value_fn=lambda c: _num(
            c.data.get("charging", "status", "chargingRateInKilometersPerHour")
        ),
        exists_fn=_has("charging"),
    ),
    SkodaSensorDescription(
        key="charging_state",
        translation_key="charging_state",
        device_class=SensorDeviceClass.ENUM,
        options=CHARGING_STATES,
        value_fn=lambda c: _enum(
            c.data.get("charging", "status", "state"), CHARGING_STATES
        ),
        exists_fn=_has("charging"),
    ),
    SkodaSensorDescription(
        key="charge_type",
        translation_key="charge_type",
        device_class=SensorDeviceClass.ENUM,
        options=["ac", "dc", "off"],
        value_fn=lambda c: _enum(
            c.data.get("charging", "status", "chargeType"), ["ac", "dc", "off"]
        ),
        exists_fn=_has("charging"),
    ),
    SkodaSensorDescription(
        key="remaining_charging_time",
        translation_key="remaining_charging_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda c: _num(
            c.data.get("charging", "status", "remainingTimeToFullyChargedInMinutes")
        ),
        exists_fn=_has("charging"),
    ),
    SkodaSensorDescription(
        key="fully_charged_at",
        translation_key="fully_charged_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: _ts(c.data.get("charging", "status", "fullyChargedAt")),
        exists_fn=_has("charging"),
    ),
    SkodaSensorDescription(
        key="max_charge_current",
        translation_key="max_charge_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: _num(
            c.data.get("charging", "settings", "maxChargeCurrentAcAmpere")
        ),
        exists_fn=_has("charging"),
    ),
    SkodaSensorDescription(
        key="charging_updated_at",
        translation_key="charging_updated_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: _ts(c.data.get("charging", "carCapturedTimestamp")),
        exists_fn=_has("charging"),
    ),
    # Combustion and hybrid vehicles
    SkodaSensorDescription(
        key="fuel_level",
        translation_key="fuel_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: _num(
            c.data.get("fuelStatus", "primaryEngineRange", "currentFuelLevelInPercent")
        ),
        exists_fn=_has("fuelStatus"),
    ),
    SkodaSensorDescription(
        key="total_range",
        translation_key="total_range",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: _num(c.data.get("fuelStatus", "totalRangeInKm")),
        exists_fn=_has("fuelStatus"),
    ),
    SkodaSensorDescription(
        key="adblue_range",
        translation_key="adblue_range",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: _num(c.data.get("fuelStatus", "adBlueRange")),
        exists_fn=lambda d: d.get("fuelStatus", "adBlueRange") is not None,
    ),
    # General
    SkodaSensorDescription(
        key="odometer",
        translation_key="odometer",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: _num(c.data.get("odometer", "mileageInKm")),
        exists_fn=_has("odometer"),
    ),
    SkodaSensorDescription(
        key="air_conditioning_state",
        translation_key="air_conditioning_state",
        device_class=SensorDeviceClass.ENUM,
        options=AIR_CONDITIONING_STATES,
        value_fn=lambda c: _enum(
            c.data.get("airConditioning", "state"), AIR_CONDITIONING_STATES
        ),
        exists_fn=_has("airConditioning"),
    ),
    SkodaSensorDescription(
        key="air_conditioning_target_temperature",
        translation_key="air_conditioning_target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: _num(
            c.data.get("airConditioning", "targetTemperature", "value")
        ),
        exists_fn=_has("airConditioning"),
    ),
    SkodaSensorDescription(
        key="air_conditioning_ready_at",
        translation_key="air_conditioning_ready_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: _ts(
            c.data.get("airConditioning", "estimatedReachOfTargetTemperatureAt")
        ),
        exists_fn=_has("airConditioning"),
    ),
    # API housekeeping
    SkodaSensorDescription(
        key="api_key_expires",
        translation_key="api_key_expires",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.client.key_expires_at,
    ),
    SkodaSensorDescription(
        key="api_requests_remaining",
        translation_key="api_requests_remaining",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.client.rate_limit.remaining,
    ),
    SkodaSensorDescription(
        key="next_update",
        translation_key="next_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: (
            c.data.fetched_at + c.update_interval
            if c.data.fetched_at and c.update_interval
            else None
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        SkodaSensor(coordinator, description)
        for description in SENSORS
        if description.exists_fn(coordinator.data)
    )


class SkodaSensor(SkodaEntity, SensorEntity):
    """Vehicle sensor."""

    entity_description: SkodaSensorDescription

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator)
