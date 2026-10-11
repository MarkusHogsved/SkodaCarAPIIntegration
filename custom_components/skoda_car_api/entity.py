"""Base entity for the Skoda Car API integration."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import COMMAND_REFRESH_DELAY, DOMAIN
from .coordinator import SkodaCoordinator

# Give up on an optimistic value if the vehicle never confirms it.
PENDING_TIMEOUT = timedelta(minutes=10)


class SkodaEntity(CoordinatorEntity[SkodaCoordinator]):
    """Entity bound to one vehicle."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: SkodaCoordinator, description: EntityDescription
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.vin}_{description.key}"
        data = coordinator.data
        name = (data.get("name") if data else None) or f"Škoda {coordinator.vin[-6:]}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.vin)},
            manufacturer="Škoda",
            name=name,
            serial_number=coordinator.vin,
        )


class SkodaCommandEntity(SkodaEntity):
    """Entity that sends commands and shows the requested value until confirmed.

    Commands are asynchronous: the API answers 202 and the vehicle acts later.
    The requested value is shown until a read-back taken after the command
    has had time to reach the vehicle, so the UI does not flip back.
    """

    _pending: Any = None
    _pending_since: datetime | None = None

    def _set_pending(self, value: Any) -> None:
        self._pending = value
        self._pending_since = dt_util.utcnow()
        self.async_write_ha_state()

    def _clear_pending(self) -> None:
        self._pending = None
        self._pending_since = None

    def _resolve(self, actual: Any) -> Any:
        """Return the pending value while it is still unconfirmed, else actual."""
        if self._pending_since is None:
            return actual
        now = dt_util.utcnow()
        fetched = self.coordinator.data.fetched_at
        confirmed = fetched is not None and fetched >= self._pending_since + timedelta(
            seconds=COMMAND_REFRESH_DELAY - 5
        )
        if (
            confirmed
            or actual == self._pending
            or now - self._pending_since > PENDING_TIMEOUT
        ):
            self._clear_pending()
            return actual
        return self._pending
