"""Constants for the Skoda Car API integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "skoda_car_api"

API_BASE_URL: Final = "https://public.api.connect.skoda-auto.cz/api/v1"
PROBLEM_BASE_URL: Final = "https://public.api.connect.skoda-auto.cz/problems/"

CONF_VIN: Final = "vin"
CONF_INTERVAL_PLUGGED: Final = "interval_plugged_in"
CONF_INTERVAL_IDLE: Final = "interval_idle"
CONF_QUOTA_RESERVE: Final = "quota_reserve"
CONF_CLIMATE_WITHOUT_EXTERNAL_POWER: Final = "climate_without_external_power"

DEFAULT_INTERVAL_PLUGGED: Final = 6  # minutes
DEFAULT_INTERVAL_IDLE: Final = 20  # minutes
DEFAULT_QUOTA_RESERVE: Final = 4  # requests kept free for commands
DEFAULT_CLIMATE_WITHOUT_EXTERNAL_POWER: Final = True

MIN_INTERVAL: Final = timedelta(minutes=3)

# Delay before reading back the vehicle state after a command was accepted.
COMMAND_REFRESH_DELAY: Final = 90  # seconds

# Raise a repair issue when the API key expires within this period.
KEY_EXPIRY_WARNING: Final = timedelta(days=7)

DEFAULT_CLIMATE_TEMPERATURE: Final = 21.0

# Problem types (RFC 9457 `type` member, without the base URL)
PROBLEM_KEY_EXPIRED: Final = "api-key-expired"
PROBLEM_KEY_NOT_AUTHORIZED: Final = "api-key-not-authorized"
PROBLEM_OPERATION_NOT_AUTHORIZED: Final = "operation-not-authorized"
PROBLEM_OPERATION_NOT_SUPPORTED: Final = "operation-not-supported"
PROBLEM_OPERATION_DISABLED: Final = "operation-disabled"
PROBLEM_RATE_LIMIT: Final = "rate-limit-exceeded"
PROBLEM_VEHICLE_BUSY: Final = "vehicle-not-accepting-requests"

# Operation names as reported in `vehicle.operations`
OP_START_CHARGING: Final = "startCharging"
OP_STOP_CHARGING: Final = "stopCharging"
OP_SET_CHARGING_LIMIT: Final = "setChargingLimit"
OP_SET_CHARGE_MODE: Final = "setChargeMode"
OP_START_AIR_CONDITIONING: Final = "startAirConditioning"
OP_STOP_AIR_CONDITIONING: Final = "stopAirConditioning"
OP_START_AUXILIARY_HEATING: Final = "startAuxiliaryHeating"
OP_STOP_AUXILIARY_HEATING: Final = "stopAuxiliaryHeating"
OP_START_ACTIVE_VENTILATION: Final = "startActiveVentilation"
OP_STOP_ACTIVE_VENTILATION: Final = "stopActiveVentilation"

CHARGING_STATES: Final = [
    "connect_cable",
    "charging",
    "conserving",
    "ready_for_charging",
    "discharging",
    "charging_interrupted",
]

AIR_CONDITIONING_STATES: Final = [
    "off",
    "cooling",
    "heating",
    "heating_auxiliary",
    "ventilation",
    "completed",
    "unknown",
    "unsupported",
]

CHARGE_MODES: Final = [
    "manual",
    "timer",
    "timer_charging_with_climatisation",
    "preferred_charging_times",
    "only_own_current",
    "immediate_discharging",
    "home_storage_charging",
]

ACTIVE_CLIMATE_STATES: Final = {
    "cooling",
    "heating",
    "heating_auxiliary",
    "ventilation",
}
