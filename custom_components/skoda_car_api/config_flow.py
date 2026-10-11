"""Config flow for the Skoda Car API integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .api import (
    SkodaApiClient,
    SkodaApiError,
    SkodaAuthError,
    SkodaConnectionError,
    SkodaNotFoundError,
    SkodaRateLimitError,
)
from .const import (
    CONF_CLIMATE_WITHOUT_EXTERNAL_POWER,
    CONF_INTERVAL_IDLE,
    CONF_INTERVAL_PLUGGED,
    CONF_QUOTA_RESERVE,
    CONF_VIN,
    DEFAULT_CLIMATE_WITHOUT_EXTERNAL_POWER,
    DEFAULT_INTERVAL_IDLE,
    DEFAULT_INTERVAL_PLUGGED,
    DEFAULT_QUOTA_RESERVE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _normalize_vin(vin: str) -> str:
    return vin.strip().upper().replace(" ", "")


async def _validate(
    hass: HomeAssistant, api_key: str, vin: str
) -> tuple[dict[str, Any] | None, dict[str, str]]:
    """Fetch basic vehicle info. Returns (vehicle, errors)."""
    client = SkodaApiClient(async_get_clientsession(hass), api_key.strip(), vin)
    try:
        payload = await client.get_vehicle(include=["info"])
    except SkodaAuthError as err:
        return None, {"base": "key_expired" if err.expired else "key_not_authorized"}
    except SkodaNotFoundError:
        return None, {CONF_VIN: "vehicle_not_found"}
    except SkodaRateLimitError:
        return None, {"base": "rate_limited"}
    except SkodaConnectionError:
        return None, {"base": "cannot_connect"}
    except SkodaApiError:
        _LOGGER.exception("Unexpected API response")
        return None, {"base": "unknown"}
    vehicle = payload.get("vehicle")
    return (vehicle if isinstance(vehicle, dict) else {}), {}


def _title(vehicle: dict[str, Any], vin: str) -> str:
    name = vehicle.get("name") or "Škoda"
    plate = vehicle.get("licensePlate")
    return f"{name} ({plate})" if plate else f"{name} ({vin[-6:]})"


class SkodaCarApiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for API key and VIN."""
        errors: dict[str, str] = {}
        if user_input is not None:
            vin = _normalize_vin(user_input[CONF_VIN])
            api_key = user_input[CONF_API_KEY].strip()
            if len(vin) != 17 or not vin.isalnum():
                errors[CONF_VIN] = "invalid_vin"
            else:
                await self.async_set_unique_id(vin)
                self._abort_if_unique_id_configured()
                vehicle, errors = await _validate(self.hass, api_key, vin)
                if vehicle is not None:
                    return self.async_create_entry(
                        title=_title(vehicle, vin),
                        data={CONF_API_KEY: api_key, CONF_VIN: vin},
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_API_KEY): _PASSWORD,
                        vol.Required(CONF_VIN): str,
                    }
                ),
                user_input,
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication when the key expired or was revoked."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new API key."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            vehicle, errors = await _validate(self.hass, api_key, entry.data[CONF_VIN])
            if vehicle is not None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: api_key}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): _PASSWORD}),
            description_placeholders={"vehicle": entry.title},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Replace the API key before it expires."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            vehicle, errors = await _validate(self.hass, api_key, entry.data[CONF_VIN])
            if vehicle is not None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: api_key}
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): _PASSWORD}),
            description_placeholders={"vehicle": entry.title},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return SkodaCarApiOptionsFlow()


class SkodaCarApiOptionsFlow(OptionsFlow):
    """Polling and command options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        def _minutes(lo: int, hi: int) -> NumberSelector:
            return NumberSelector(
                NumberSelectorConfig(
                    min=lo,
                    max=hi,
                    step=1,
                    unit_of_measurement="min",
                    mode=NumberSelectorMode.BOX,
                )
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_INTERVAL_PLUGGED, default=DEFAULT_INTERVAL_PLUGGED
                ): vol.All(_minutes(3, 60), vol.Coerce(int)),
                vol.Required(
                    CONF_INTERVAL_IDLE, default=DEFAULT_INTERVAL_IDLE
                ): vol.All(_minutes(5, 240), vol.Coerce(int)),
                vol.Required(
                    CONF_QUOTA_RESERVE, default=DEFAULT_QUOTA_RESERVE
                ): vol.All(
                    NumberSelector(
                        NumberSelectorConfig(
                            min=0, max=15, step=1, mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Coerce(int),
                ),
                vol.Required(
                    CONF_CLIMATE_WITHOUT_EXTERNAL_POWER,
                    default=DEFAULT_CLIMATE_WITHOUT_EXTERNAL_POWER,
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema, self.config_entry.options
            ),
        )
