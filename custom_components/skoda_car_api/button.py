"""Buttons for the Skoda Car API integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SkodaConfigEntry
from .entity import SkodaEntity

PARALLEL_UPDATES = 1

REFRESH = ButtonEntityDescription(
    key="refresh",
    translation_key="refresh",
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    async_add_entities([SkodaRefreshButton(entry.runtime_data, REFRESH)])


class SkodaRefreshButton(SkodaEntity, ButtonEntity):
    """Fetch the vehicle state now (uses one request from the quota)."""

    async def async_press(self) -> None:
        """Refresh."""
        await self.coordinator.async_request_refresh()
