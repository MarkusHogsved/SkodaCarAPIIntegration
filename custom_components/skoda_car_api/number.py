"""Number entities for the Skoda Car API integration."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DEFAULT_CLIMATE_TEMPERATURE, OP_SET_CHARGING_LIMIT
from .coordinator import SkodaConfigEntry
from .entity import SkodaCommandEntity, SkodaEntity

PARALLEL_UPDATES = 1

CHARGING_LIMIT = NumberEntityDescription(
    key="charging_limit",
    translation_key="charging_limit",
    native_min_value=50,
    native_max_value=100,
    native_step=10,
    native_unit_of_measurement=PERCENTAGE,
    mode=NumberMode.SLIDER,
)

CLIMATE_TEMPERATURE = NumberEntityDescription(
    key="climate_temperature",
    translation_key="climate_temperature",
    device_class=NumberDeviceClass.TEMPERATURE,
    native_min_value=16,
    native_max_value=29.5,
    native_step=0.5,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    entity_category=EntityCategory.CONFIG,
    mode=NumberMode.BOX,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up number entities."""
    coordinator = entry.runtime_data
    entities: list[NumberEntity] = []
    if coordinator.data.has_part("charging") and coordinator.supports(
        OP_SET_CHARGING_LIMIT
    ):
        entities.append(SkodaChargingLimit(coordinator, CHARGING_LIMIT))
    if coordinator.data.has_part("airConditioning"):
        entities.append(SkodaClimateTemperature(coordinator, CLIMATE_TEMPERATURE))
    async_add_entities(entities)


class SkodaChargingLimit(SkodaCommandEntity, NumberEntity):
    """Target state of charge."""

    @property
    def native_value(self) -> float | None:
        """Return the current limit."""
        value = self.coordinator.data.get(
            "charging", "settings", "targetStateOfChargeInPercent"
        )
        return self._resolve(value if isinstance(value, (int, float)) else None)

    async def async_set_native_value(self, value: float) -> None:
        """Set the limit."""
        percent = int(round(value / 10) * 10)
        await self.coordinator.async_command(
            OP_SET_CHARGING_LIMIT,
            lambda: self.coordinator.client.set_charging_limit(percent),
        )
        self._set_pending(percent)


class SkodaClimateTemperature(SkodaEntity, RestoreNumber):
    """Target temperature used when climate is started from Home Assistant.

    Stored locally; changing it does not call the API.
    """

    _attr_native_value: float | None = DEFAULT_CLIMATE_TEMPERATURE

    async def async_added_to_hass(self) -> None:
        """Restore the last value, or start from the vehicle's own setting."""
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = last.native_value
            self.coordinator.climate_temperature = last.native_value
            return
        vehicle_value = self.coordinator.data.get(
            "airConditioning", "targetTemperature", "value"
        )
        if isinstance(vehicle_value, (int, float)):
            self._attr_native_value = float(vehicle_value)
            self.coordinator.climate_temperature = float(vehicle_value)

    async def async_set_native_value(self, value: float) -> None:
        """Store the value."""
        self._attr_native_value = value
        self.coordinator.climate_temperature = value
        self.async_write_ha_state()
