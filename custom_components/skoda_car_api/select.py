"""Select entities for the Skoda Car API integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CHARGE_MODES, OP_SET_CHARGE_MODE
from .coordinator import SkodaConfigEntry
from .entity import SkodaCommandEntity

PARALLEL_UPDATES = 1

CHARGE_MODE = SelectEntityDescription(
    key="charge_mode",
    translation_key="charge_mode",
    options=CHARGE_MODES,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up select entities."""
    coordinator = entry.runtime_data
    if coordinator.data.has_part("charging") and coordinator.supports(
        OP_SET_CHARGE_MODE
    ):
        async_add_entities([SkodaChargeMode(coordinator, CHARGE_MODE)])


class SkodaChargeMode(SkodaCommandEntity, SelectEntity):
    """Preferred charge mode."""

    @property
    def options(self) -> list[str]:
        """Return the modes this vehicle offers (unknown future values are skipped)."""
        available = self.coordinator.data.get(
            "charging", "settings", "availableChargeModes"
        )
        if isinstance(available, list):
            modes = [m.lower() for m in available if isinstance(m, str)]
            filtered = [m for m in CHARGE_MODES if m in modes]
            if filtered:
                return filtered
        return CHARGE_MODES

    @property
    def current_option(self) -> str | None:
        """Return the active mode."""
        mode = self.coordinator.data.get("charging", "settings", "preferredChargeMode")
        actual = mode.lower() if isinstance(mode, str) else None
        return self._resolve(actual if actual in CHARGE_MODES else None)

    async def async_select_option(self, option: str) -> None:
        """Change the charge mode."""
        await self.coordinator.async_command(
            OP_SET_CHARGE_MODE,
            lambda: self.coordinator.client.set_charge_mode(option.upper()),
        )
        self._set_pending(option)
