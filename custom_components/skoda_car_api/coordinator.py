"""Data update coordinator for the Skoda Car API integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    SkodaApiClient,
    SkodaApiError,
    SkodaAuthError,
    SkodaConnectionError,
    SkodaNotFoundError,
    SkodaOperationError,
    SkodaRateLimitError,
)
from .const import (
    COMMAND_REFRESH_DELAY,
    CONF_INTERVAL_IDLE,
    CONF_INTERVAL_PLUGGED,
    CONF_QUOTA_RESERVE,
    DEFAULT_CLIMATE_TEMPERATURE,
    DEFAULT_INTERVAL_IDLE,
    DEFAULT_INTERVAL_PLUGGED,
    DEFAULT_QUOTA_RESERVE,
    DOMAIN,
    KEY_EXPIRY_WARNING,
    MIN_INTERVAL,
    PROBLEM_OPERATION_DISABLED,
)

_LOGGER = logging.getLogger(__name__)

type SkodaConfigEntry = ConfigEntry[SkodaCoordinator]

_PLUGGED_STATES = {"CHARGING", "CONSERVING", "READY_FOR_CHARGING", "DISCHARGING"}

_PART_ERROR_PREFIX = {
    "status": "VEHICLE_STATUS",
    "fuelStatus": "FUEL_STATUS",
    "odometer": "ODOMETER",
    "parkingPosition": "PARKING_POSITION",
    "airConditioning": "AIR_CONDITIONING",
    "auxiliaryHeating": "AUXILIARY_HEATING",
    "activeVentilation": "ACTIVE_VENTILATION",
    "charging": "CHARGING",
    "chargingProfiles": "CHARGING_PROFILES",
}


@dataclass
class VehicleData:
    """Snapshot of one vehicle as returned by the API."""

    vehicle: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    fetched_at: datetime | None = None

    def get(self, *path: str) -> Any:
        """Return a nested value, or None when any level is missing."""
        node: Any = self.vehicle
        for key in path:
            if not isinstance(node, dict):
                return None
            node = node.get(key)
        return node

    def has_part(self, part: str) -> bool:
        """Return True if the vehicle reports this part, now or when it recovers.

        A part that is temporarily unavailable or disabled is still supported,
        so its entities are created and simply show as unknown for now.
        """
        if part in self.vehicle:
            return True
        prefix = _PART_ERROR_PREFIX.get(part)
        if prefix is None:
            return False
        return any(
            t in (f"{prefix}_UNAVAILABLE", f"{prefix}_DISABLED")
            for t in self.error_types
        )

    @property
    def operations(self) -> set[str] | None:
        """Supported remote operations, or None when unknown."""
        ops = self.vehicle.get("operations")
        if not isinstance(ops, list):
            return None
        return {op["name"] for op in ops if isinstance(op, dict) and "name" in op}

    @property
    def error_types(self) -> list[str]:
        """Machine-readable error types for omitted parts."""
        return [e["type"] for e in self.errors if isinstance(e, dict) and "type" in e]

    @property
    def plugged_in(self) -> bool | None:
        """Return True if a charging cable is connected."""
        plug = self.get("charging", "status", "plugConnectionState")
        if plug == "CONNECTED":
            return True
        if self.get("charging", "status", "state") in _PLUGGED_STATES:
            return True
        if plug == "DISCONNECTED":
            return False
        return None


class SkodaCoordinator(DataUpdateCoordinator[VehicleData]):
    """Polls one vehicle while staying inside the per-VIN request quota."""

    config_entry: SkodaConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: SkodaConfigEntry, client: SkodaApiClient
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {client.vin}",
            update_interval=self._interval_idle_for(entry),
        )
        self.client = client
        self.vin = client.vin
        self.last_command_at: datetime | None = None
        # Target temperature for climate commands, kept by the number entity
        self.climate_temperature: float = DEFAULT_CLIMATE_TEMPERATURE
        self._unsub_command_refresh: CALLBACK_TYPE | None = None

    @staticmethod
    def _interval_idle_for(entry: ConfigEntry) -> timedelta:
        return timedelta(
            minutes=entry.options.get(CONF_INTERVAL_IDLE, DEFAULT_INTERVAL_IDLE)
        )

    @property
    def _interval_plugged(self) -> timedelta:
        return timedelta(
            minutes=self.config_entry.options.get(
                CONF_INTERVAL_PLUGGED, DEFAULT_INTERVAL_PLUGGED
            )
        )

    @property
    def _interval_idle(self) -> timedelta:
        return self._interval_idle_for(self.config_entry)

    @property
    def _quota_reserve(self) -> int:
        return int(
            self.config_entry.options.get(CONF_QUOTA_RESERVE, DEFAULT_QUOTA_RESERVE)
        )

    async def _async_update_data(self) -> VehicleData:
        try:
            payload = await self.client.get_vehicle()
        except SkodaAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="key_expired" if err.expired else "key_rejected",
            ) from err
        except SkodaRateLimitError as err:
            wait = timedelta(seconds=(err.retry_after or 600) + 5)
            self.update_interval = max(wait, MIN_INTERVAL)
            raise UpdateFailed(
                f"Rate limited, next attempt in {int(self.update_interval.total_seconds())} s",
                retry_after=self.update_interval.total_seconds(),
            ) from err
        except SkodaNotFoundError as err:
            raise UpdateFailed(f"Vehicle {self.vin} not found") from err
        except SkodaConnectionError as err:
            if err.retry_after:
                self.update_interval = max(
                    timedelta(seconds=err.retry_after + 5), MIN_INTERVAL
                )
            raise UpdateFailed(str(err)) from err
        except SkodaApiError as err:
            raise UpdateFailed(str(err)) from err

        vehicle = payload.get("vehicle")
        errors = payload.get("errors")
        data = VehicleData(
            vehicle=vehicle if isinstance(vehicle, dict) else {},
            errors=errors if isinstance(errors, list) else [],
            fetched_at=dt_util.utcnow(),
        )
        self.update_interval = self._next_interval(data)
        self._check_key_expiry()
        return data

    def _next_interval(self, data: VehicleData) -> timedelta:
        """Choose the next poll interval from plug state and remaining quota."""
        interval = self._interval_plugged if data.plugged_in else self._interval_idle
        rl = self.client.rate_limit
        if (
            rl.remaining is not None
            and rl.remaining <= self._quota_reserve
            and rl.reset_at is not None
        ):
            until_reset = rl.reset_at - dt_util.utcnow() + timedelta(seconds=10)
            interval = max(interval, until_reset)
        return max(interval, MIN_INTERVAL)

    def _check_key_expiry(self) -> None:
        expires = self.client.key_expires_at
        issue_id = f"api_key_expiring_{self.config_entry.entry_id}"
        if expires is not None and expires - dt_util.utcnow() < KEY_EXPIRY_WARNING:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="api_key_expiring",
                translation_placeholders={
                    "vehicle": self.config_entry.title,
                    "expires": dt_util.as_local(expires).strftime("%Y-%m-%d %H:%M"),
                },
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    def supports(self, operation: str) -> bool:
        """Return True unless the vehicle is known not to support the operation."""
        if self.data is None:
            return True
        ops = self.data.operations
        return ops is None or operation in ops

    async def async_command(
        self, operation: str, call: Callable[[], Awaitable[None]]
    ) -> None:
        """Run a remote command and schedule a read-back of the vehicle state."""
        if not self.supports(operation):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="operation_not_supported",
                translation_placeholders={"operation": operation},
            )
        try:
            await call()
        except SkodaAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="key_rejected"
            ) from err
        except SkodaRateLimitError as err:
            key = "vehicle_busy" if err.vehicle_busy else "rate_limited"
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=key,
                translation_placeholders={"retry_after": str(err.retry_after or "?")},
            ) from err
        except SkodaOperationError as err:
            key = (
                "operation_disabled"
                if err.problem == PROBLEM_OPERATION_DISABLED
                else "operation_rejected"
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=key,
                translation_placeholders={
                    "operation": operation,
                    "detail": err.detail or str(err),
                },
            ) from err
        except SkodaApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"operation": operation, "detail": str(err)},
            ) from err

        self.last_command_at = dt_util.utcnow()
        self._schedule_command_refresh()

    @callback
    def _schedule_command_refresh(self) -> None:
        if self._unsub_command_refresh:
            self._unsub_command_refresh()

        @callback
        def _refresh(_now: datetime) -> None:
            self._unsub_command_refresh = None
            rl = self.client.rate_limit
            if rl.remaining is not None and rl.remaining <= 1:
                _LOGGER.debug("Skipping read-back after command, quota nearly used")
                return
            self.hass.async_create_task(self.async_request_refresh())

        self._unsub_command_refresh = async_call_later(
            self.hass, COMMAND_REFRESH_DELAY, _refresh
        )

    async def async_shutdown(self) -> None:
        """Cancel pending callbacks."""
        if self._unsub_command_refresh:
            self._unsub_command_refresh()
            self._unsub_command_refresh = None
        await super().async_shutdown()
