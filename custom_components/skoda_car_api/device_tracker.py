"""Parking position tracker for the Skoda Car API integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SkodaConfigEntry
from .entity import SkodaEntity

PARALLEL_UPDATES = 0

DESCRIPTION = EntityDescription(
    key="parking_position", translation_key="parking_position"
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the tracker."""
    coordinator = entry.runtime_data
    if coordinator.data.has_part("parkingPosition"):
        async_add_entities([SkodaParkingTracker(coordinator, DESCRIPTION)])


class SkodaParkingTracker(SkodaEntity, TrackerEntity):
    """Last known parking position.

    While the vehicle is moving the API returns no coordinates; the last
    parked position is kept and `in_motion` is exposed as an attribute.
    """

    _attr_source_type = SourceType.GPS

    def __init__(self, *args: Any) -> None:
        """Initialize the tracker."""
        super().__init__(*args)
        self._lat: float | None = None
        self._lon: float | None = None
        self._address: str | None = None
        self._update_position()

    def _update_position(self) -> None:
        data = self.coordinator.data
        coords = data.get("parkingPosition", "gpsCoordinates")
        if isinstance(coords, dict):
            lat, lon = coords.get("latitude"), coords.get("longitude")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                self._lat, self._lon = float(lat), float(lon)
                self._address = data.get("parkingPosition", "formattedAddress")

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_position()
        super()._handle_coordinator_update()

    @property
    def latitude(self) -> float | None:
        """Return latitude."""
        return self._lat

    @property
    def longitude(self) -> float | None:
        """Return longitude."""
        return self._lon

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return {
            "address": self._address,
            "in_motion": self.coordinator.data.get("parkingPosition", "state")
            == "IN_MOTION",
        }
