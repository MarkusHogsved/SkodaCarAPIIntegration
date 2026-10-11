"""Async client for the MyŠkoda Public API."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import logging
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout
from homeassistant.util import dt as dt_util
from homeassistant.util.json import json_loads

from .const import (
    API_BASE_URL,
    PROBLEM_BASE_URL,
    PROBLEM_KEY_EXPIRED,
    PROBLEM_OPERATION_NOT_AUTHORIZED,
    PROBLEM_RATE_LIMIT,
    PROBLEM_VEHICLE_BUSY,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = ClientTimeout(total=60)


class SkodaApiError(Exception):
    """Base error for API failures."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        problem: str | None = None,
        detail: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        """Initialize the error."""
        super().__init__(message)
        self.status = status
        self.problem = problem
        self.detail = detail
        self.retry_after = retry_after


class SkodaAuthError(SkodaApiError):
    """The API key is invalid, expired or does not cover the vehicle (401/403)."""

    @property
    def expired(self) -> bool:
        """Return True if the key has expired."""
        return self.problem == PROBLEM_KEY_EXPIRED


class SkodaRateLimitError(SkodaApiError):
    """The request was rejected with 429."""

    @property
    def vehicle_busy(self) -> bool:
        """Return True if the vehicle itself declined the request."""
        return self.problem == PROBLEM_VEHICLE_BUSY

    @property
    def quota_exceeded(self) -> bool:
        """Return True if the per-VIN quota is used up."""
        return self.problem == PROBLEM_RATE_LIMIT


class SkodaNotFoundError(SkodaApiError):
    """No vehicle found for the VIN (404)."""


class SkodaOperationError(SkodaApiError):
    """The vehicle cannot execute the operation (422)."""


class SkodaConnectionError(SkodaApiError):
    """Network error, timeout or 5xx."""


@dataclass
class RateLimit:
    """Rate-limit state from the most recent response."""

    limit: int | None = None
    remaining: int | None = None
    reset_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class ApiResult:
    """Parsed response."""

    status: int
    data: dict[str, Any] = field(default_factory=dict)


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _parse_timestamp(value: str | None) -> datetime | None:
    """Parse an ISO 8601 or HTTP-date timestamp."""
    if not value:
        return None
    parsed = dt_util.parse_datetime(value.strip())
    if parsed is None:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return parsed


class SkodaApiClient:
    """Client bound to one API key and one VIN."""

    def __init__(self, session: ClientSession, api_key: str, vin: str) -> None:
        """Initialize the client."""
        self._session = session
        self._api_key = api_key
        self.vin = vin.upper()
        self.rate_limit = RateLimit()
        self.key_expires_at: datetime | None = None
        self._lock = asyncio.Lock()

    @property
    def _vehicle_url(self) -> str:
        return f"{API_BASE_URL}/vehicles/{self.vin}"

    async def get_vehicle(self, include: list[str] | None = None) -> dict[str, Any]:
        """Return the vehicle and its current state."""
        params = {"include": ",".join(include)} if include else None
        result = await self._request("GET", self._vehicle_url, params=params)
        return result.data

    async def start_charging(self) -> None:
        """Start charging."""
        await self._request("POST", f"{self._vehicle_url}/charging/start")

    async def stop_charging(self) -> None:
        """Stop charging."""
        await self._request("POST", f"{self._vehicle_url}/charging/stop")

    async def set_charging_limit(self, percent: int) -> None:
        """Set the target state of charge."""
        await self._request(
            "PUT",
            f"{self._vehicle_url}/charging/limit",
            json={"targetStateOfChargeInPercent": percent},
        )

    async def set_charge_mode(self, mode: str) -> None:
        """Set the charge mode (API value, e.g. MANUAL)."""
        await self._request(
            "PUT", f"{self._vehicle_url}/charging/mode", json={"chargeMode": mode}
        )

    async def update_charging_profile(
        self, profile_id: int, profile: dict[str, Any]
    ) -> None:
        """Replace a charging profile."""
        await self._request(
            "PUT",
            f"{self._vehicle_url}/charging-profiles/{profile_id}",
            json=profile,
        )

    async def start_air_conditioning(
        self, temperature: float | None, without_external_power: bool | None
    ) -> None:
        """Start air conditioning."""
        body: dict[str, Any] = {}
        if temperature is not None:
            body["targetTemperature"] = {"value": temperature, "unit": "CELSIUS"}
        if without_external_power is not None:
            body["airConditioningWithoutExternalPower"] = without_external_power
        await self._request(
            "POST", f"{self._vehicle_url}/air-conditioning/start", json=body
        )

    async def stop_air_conditioning(self) -> None:
        """Stop air conditioning."""
        await self._request("POST", f"{self._vehicle_url}/air-conditioning/stop")

    async def start_auxiliary_heating(
        self,
        spin: str,
        temperature: float | None = None,
        duration: int | None = None,
        start_mode: str | None = None,
    ) -> None:
        """Start auxiliary heating."""
        body: dict[str, Any] = {"spin": spin}
        if temperature is not None:
            body["targetTemperature"] = {"value": temperature, "unit": "CELSIUS"}
        if duration is not None:
            body["durationInSeconds"] = duration
        if start_mode is not None:
            body["startMode"] = start_mode
        await self._request(
            "POST", f"{self._vehicle_url}/auxiliary-heating/start", json=body
        )

    async def stop_auxiliary_heating(self) -> None:
        """Stop auxiliary heating."""
        await self._request("POST", f"{self._vehicle_url}/auxiliary-heating/stop")

    async def start_active_ventilation(self) -> None:
        """Start active ventilation."""
        await self._request("POST", f"{self._vehicle_url}/active-ventilation/start")

    async def stop_active_ventilation(self) -> None:
        """Stop active ventilation."""
        await self._request("POST", f"{self._vehicle_url}/active-ventilation/stop")

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> ApiResult:
        headers = {
            "X-API-Key": self._api_key,
            "Accept": "application/json, application/problem+json",
        }
        async with self._lock:
            try:
                async with self._session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json,
                    timeout=REQUEST_TIMEOUT,
                ) as resp:
                    self._read_headers(resp)
                    return await self._handle(resp)
            except TimeoutError as err:
                raise SkodaConnectionError(f"Timeout on {method} {url}") from err
            except ClientError as err:
                raise SkodaConnectionError(
                    f"Connection error on {method} {url}: {err}"
                ) from err

    def _read_headers(self, resp: ClientResponse) -> None:
        h = resp.headers
        limit = _parse_int(h.get("RateLimit-Limit"))
        remaining = _parse_int(h.get("RateLimit-Remaining"))
        reset = _parse_int(h.get("RateLimit-Reset"))
        if limit is not None or remaining is not None:
            now = dt_util.utcnow()
            self.rate_limit = RateLimit(
                limit=limit,
                remaining=remaining,
                reset_at=now + timedelta(seconds=reset) if reset is not None else None,
                updated_at=now,
            )
        expires = _parse_timestamp(h.get("X-API-Key-Expires-At"))
        if expires is not None:
            self.key_expires_at = expires

    @staticmethod
    async def _json(resp: ClientResponse) -> Any:
        """Return the JSON body, or None for an empty or non-JSON body."""
        text = await resp.text()
        if not text.strip():
            return None
        try:
            return json_loads(text)
        except ValueError:
            return None

    async def _handle(self, resp: ClientResponse) -> ApiResult:
        status = resp.status
        if 200 <= status < 300:
            payload = await self._json(resp)
            return ApiResult(
                status=status, data=payload if isinstance(payload, dict) else {}
            )

        problem: str | None = None
        detail: str | None = None
        body = await self._json(resp)
        if isinstance(body, dict):
            ptype = body.get("type")
            if isinstance(ptype, str) and ptype.startswith(PROBLEM_BASE_URL):
                problem = ptype.removeprefix(PROBLEM_BASE_URL)
            detail = body.get("detail") or body.get("title")

        retry_after = _parse_int(resp.headers.get("Retry-After"))
        message = f"HTTP {status}" + (f" {problem}" if problem else "")
        if detail:
            message += f": {detail}"
        kwargs: dict[str, Any] = {
            "status": status,
            "problem": problem,
            "detail": detail,
            "retry_after": retry_after,
        }
        _LOGGER.debug("Request to %s failed: %s", resp.url.path, message)

        if status == 403 and problem == PROBLEM_OPERATION_NOT_AUTHORIZED:
            # The key is fine; the vehicle refused this operation for the user.
            raise SkodaOperationError(message, **kwargs)
        if status in (401, 403):
            raise SkodaAuthError(message, **kwargs)
        if status == 404:
            raise SkodaNotFoundError(message, **kwargs)
        if status == 422:
            raise SkodaOperationError(message, **kwargs)
        if status == 429:
            raise SkodaRateLimitError(message, **kwargs)
        if status >= 500:
            raise SkodaConnectionError(message, **kwargs)
        raise SkodaApiError(message, **kwargs)
