"""Charge-Amps API Client."""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import jwt
from aiohttp import ClientResponse, ClientResponseError, ClientSession
from pydantic import BaseModel, ConfigDict, model_validator
from pydantic.alias_generators import to_camel

API_BASE_URL = "https://eapi.charge.space"
API_VERSION = "v5"

# Statuses that mean "this account cannot see that" rather than "something went wrong":
# 401/403 for an account without the Enterprise role, 404 for an API base URL that
# predates the organisation endpoints.
_NO_ACCESS_STATUSES = (401, 403, 404)


class ChargeAmpsBaseModel(BaseModel):
    """Base model for Charge-Amps API data."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    @model_validator(mode="before")
    @classmethod
    def _nulls_as_missing(cls, data: Any) -> Any:
        """Treat an explicit null like an absent key so field defaults apply.

        Nearly every property in the API schema is nullable, and which ones actually
        come back null depends on the caller's access level — an administrator who does
        not own a chargepoint gets no password for it, for instance.
        """
        if not isinstance(data, dict):
            return data
        return {key: value for key, value in data.items() if value is not None}


class ChargePointConnector(ChargeAmpsBaseModel):
    """Charge point connector model."""

    charge_point_id: str | None = None
    connector_id: int
    type: str | None = None


class ChargePoint(ChargeAmpsBaseModel):
    """Charge point model."""

    id: str
    name: str | None = None
    password: str | None = None
    type: str | None = None
    is_loadbalanced: bool = False
    firmware_version: str | None = None
    hardware_version: str | None = None
    owner_read_only: bool = False
    ocpp_version: str | None = None
    connectors: list[ChargePointConnector] = []


class Organisation(ChargeAmpsBaseModel):
    """Organisation model."""

    id: str
    name: str | None = None
    description: str | None = None


class ChargePointMeasurement(ChargeAmpsBaseModel):
    """Charge point measurement model."""

    phase: str
    current: float | None = None
    voltage: float | None = None


class ChargePointConnectorStatus(ChargeAmpsBaseModel):
    """Charge point connector status model."""

    charge_point_id: str
    connector_id: int
    total_consumption_kwh: float
    charging_power_kw: float | None = None
    status: str
    measurements: list[ChargePointMeasurement] | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    session_id: int | None = None


class ChargePointStatus(ChargeAmpsBaseModel):
    """Charge point status model."""

    id: str
    status: str
    connector_statuses: list[ChargePointConnectorStatus] = []


class ChargePointSettings(ChargeAmpsBaseModel):
    """Charge point settings model."""

    id: str
    dimmer: str
    down_light: bool | None = None
    max_current: float | None = None
    installation_current: int | None = None


class ChargePointConnectorSettings(ChargeAmpsBaseModel):
    """Charge point connector settings model."""

    charge_point_id: str
    connector_id: int
    mode: str
    rfid_lock: bool
    cable_lock: bool
    max_current: float | None = None
    installation_current: int | None = None


class ChargingSession(ChargeAmpsBaseModel):
    """Charging session model."""

    id: int
    charge_point_id: str
    connector_id: int
    session_type: str
    total_consumption_kwh: float
    start_time: datetime | None = None
    end_time: datetime | None = None


class StartAuth(ChargeAmpsBaseModel):
    """Start auth model."""

    rfid_length: int
    rfid_format: str
    rfid: str
    external_transaction_id: str | None = None


class ChargeAmpsClient:
    """API Client for Charge-Amps."""

    def __init__(
        self,
        email: str,
        password: str,
        api_key: str,
        session: ClientSession,
        api_base_url: str | None = None,
        organisation_id: str | None = None,
    ):
        """Initialize."""
        self._logger = logging.getLogger(__name__).getChild(self.__class__.__name__)
        self._email = email
        self._password = password
        self._api_key = api_key
        self._session = session
        self._headers = {}
        self._base_url = api_base_url or API_BASE_URL
        self._organisation_id = organisation_id
        self._discovered_organisation_ids: list[str] | None = None
        self._ssl = True
        self._token = None
        self._token_expire = 0
        self._refresh_token = None
        self._token_lock = asyncio.Lock()

    async def _handle_response(self, response: ClientResponse, expected_errors: tuple[int, ...] = ()) -> ClientResponse:
        """Handle response and log errors.

        Statuses listed in expected_errors still raise, but are logged at debug level —
        the caller handles them as a normal outcome rather than a fault.
        """
        if response.status >= 400:
            error_text = await response.text()
            if response.status in expected_errors:
                self._logger.debug("API returned expected %d for %s", response.status, response.url)
            else:
                self._logger.error("API Error %d: %s for %s", response.status, error_text, response.url)
            response.raise_for_status()
        return response

    async def _ensure_token(self) -> None:
        """Ensure we have a valid authentication token."""
        async with self._token_lock:
            if self._token_expire > time.time():
                return

            if self._token is None:
                self._logger.info("Token not found")
            elif self._token_expire > 0:
                self._logger.info("Token expired")

            response = None

            if self._refresh_token:
                try:
                    self._logger.info("Found refresh token, try refresh")
                    response = await self._session.post(
                        urljoin(self._base_url, f"/api/{API_VERSION}/auth/refreshtoken"),
                        ssl=self._ssl,
                        headers={"apiKey": self._api_key},
                        json={"token": self._token, "refreshToken": self._refresh_token},
                    )
                    await self._handle_response(response)
                    self._logger.debug("Refresh successful")
                except Exception:
                    self._logger.warning("Token refresh failed")
                    self._token = None
                    self._refresh_token = None
                    response = None
            else:
                self._token = None

            if self._token is None:
                try:
                    self._logger.debug("Try login")
                    response = await self._session.post(
                        urljoin(self._base_url, f"/api/{API_VERSION}/auth/login"),
                        ssl=self._ssl,
                        headers={"apiKey": self._api_key},
                        json={"email": self._email, "password": self._password},
                    )
                    await self._handle_response(response)
                    self._logger.debug("Login successful")
                except Exception as exc:
                    self._logger.error("Login failed: %s", exc)
                    self._token = None
                    self._refresh_token = None
                    self._token_expire = 0
                    raise exc

            if response is None:
                self._logger.error("No response during authentication")
                return

            response_payload = await response.json()

            self._token = response_payload["token"]
            self._refresh_token = response_payload["refreshToken"]

            token_payload = jwt.decode(self._token, options={"verify_signature": False})
            self._token_expire = token_payload.get("exp", 0)

            self._headers["Authorization"] = f"Bearer {self._token}"

    async def _post(self, path, **kwargs) -> ClientResponse:
        """Perform a POST request."""
        await self._ensure_token()
        headers = kwargs.pop("headers", self._headers)
        response = await self._session.post(urljoin(self._base_url, path), ssl=self._ssl, headers=headers, **kwargs)
        return await self._handle_response(response)

    async def _get(self, path, expected_errors: tuple[int, ...] = (), **kwargs) -> ClientResponse:
        """Perform a GET request."""
        await self._ensure_token()
        headers = kwargs.pop("headers", self._headers)
        response = await self._session.get(urljoin(self._base_url, path), ssl=self._ssl, headers=headers, **kwargs)
        return await self._handle_response(response, expected_errors)

    async def _put(self, path, **kwargs) -> ClientResponse:
        """Perform a PUT request."""
        await self._ensure_token()
        headers = kwargs.pop("headers", self._headers)
        response = await self._session.put(urljoin(self._base_url, path), ssl=self._ssl, headers=headers, **kwargs)
        return await self._handle_response(response)

    async def get_organisations(self) -> list[Organisation]:
        """Get all organisations the account is a member of.

        Requires the "Enterprise" role on the account. A private-only account gets 401/403,
        and an API base URL without the endpoint gets 404 — both mean "no organisations"
        rather than a failure, since this is only ever a fallback lookup.
        """
        request_uri = f"/api/{API_VERSION}/organisations"
        try:
            response = await self._get(request_uri, expected_errors=_NO_ACCESS_STATUSES)
        except ClientResponseError as exc:
            if exc.status in _NO_ACCESS_STATUSES:
                self._logger.debug("Account has no access to organisations (HTTP %d)", exc.status)
                return []
            raise
        return [Organisation.model_validate(org) for org in await response.json()]

    async def get_owned_chargepoints(self) -> list[ChargePoint]:
        """Get the chargepoints owned by the account itself."""
        request_uri = f"/api/{API_VERSION}/chargepoints/owned"
        self._logger.debug("Fetching owned chargepoints: %s", request_uri)
        response = await self._get(request_uri)
        return [ChargePoint.model_validate(cp) for cp in await response.json()]

    async def get_organisation_chargepoints(self, organisation_id: str, expected_errors: tuple[int, ...] = ()) -> list[ChargePoint]:
        """Get the chargepoints belonging to a single organisation."""
        request_uri = f"/api/{API_VERSION}/organisations/{organisation_id}/chargepoints"
        self._logger.debug("Fetching chargepoints for organisation %s: %s", organisation_id, request_uri)
        response = await self._get(request_uri, expected_errors=expected_errors)
        return [ChargePoint.model_validate(cp) for cp in await response.json()]

    async def get_chargepoints(self) -> list[ChargePoint]:
        """Get all chargepoints reachable by the account.

        With an explicit organisation ID configured, only that organisation is queried.
        Otherwise the owned chargepoints are returned, falling back to a lookup of the
        account's organisations when the account owns nothing itself — an org admin who
        is not the owner of any chargepoint would otherwise see an empty integration.
        """
        if self._organisation_id:
            return await self.get_organisation_chargepoints(self._organisation_id)

        chargepoints = await self.get_owned_chargepoints()
        if chargepoints:
            return chargepoints

        organisation_ids = self._discovered_organisation_ids
        if organisation_ids is None:
            organisations = await self.get_organisations()
            self._logger.debug(
                "No owned chargepoints, discovered %d organisation(s): %s",
                len(organisations),
                ", ".join(f"{org.name or '?'} ({org.id})" for org in organisations),
            )
            organisation_ids = [org.id for org in organisations]
            self._discovered_organisation_ids = organisation_ids

        by_id: dict[str, ChargePoint] = {}
        failed: list[str] = []
        for organisation_id in organisation_ids:
            try:
                chargepoints = await self.get_organisation_chargepoints(organisation_id, expected_errors=_NO_ACCESS_STATUSES)
            except ClientResponseError as exc:
                # Membership does not guarantee chargepoint access in every organisation.
                # Skip the ones that deny us rather than losing the ones that do not.
                if exc.status not in _NO_ACCESS_STATUSES:
                    raise
                self._logger.debug("No chargepoint access in organisation %s (HTTP %d)", organisation_id, exc.status)
                failed.append(organisation_id)
                continue
            for chargepoint in chargepoints:
                by_id.setdefault(chargepoint.id, chargepoint)

        if failed and len(failed) == len(organisation_ids):
            self._logger.warning("Chargepoint access denied in all %d organisation(s) of this account", len(failed))

        if not by_id:
            # Membership may have changed since discovery — re-discover on the next poll.
            self._discovered_organisation_ids = None
            self._logger.warning("Account owns no chargepoints and none were found via its organisations")
        return list(by_id.values())

    async def get_all_chargingsessions(
        self,
        charge_point_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[ChargingSession]:
        """Get all charging sessions."""
        query_params = {}
        if start_time:
            query_params["startTime"] = start_time.isoformat()
        if end_time:
            query_params["endTime"] = end_time.isoformat()
        request_uri = f"/api/{API_VERSION}/chargepoints/{charge_point_id}/chargingsessions"
        response = await self._get(request_uri, params=query_params)
        res = []
        for session in await response.json():
            res.append(ChargingSession.model_validate(session))
        return res

    async def get_chargingsession(self, charge_point_id: str, session: int) -> ChargingSession:
        """Get charging session."""
        request_uri = f"/api/{API_VERSION}/chargepoints/{charge_point_id}/chargingsessions/{session}"
        response = await self._get(request_uri)
        payload = await response.json()
        return ChargingSession.model_validate(payload)

    async def get_chargepoint_status(self, charge_point_id: str) -> ChargePointStatus:
        """Get charge point status."""
        request_uri = f"/api/{API_VERSION}/chargepoints/{charge_point_id}/status"
        response = await self._get(request_uri)
        payload = await response.json()
        return ChargePointStatus.model_validate(payload)

    async def get_chargepoint_settings(self, charge_point_id: str) -> ChargePointSettings:
        """Get chargepoint settings."""
        request_uri = f"/api/{API_VERSION}/chargepoints/{charge_point_id}/settings"
        response = await self._get(request_uri)
        payload = await response.json()
        return ChargePointSettings.model_validate(payload)

    async def set_chargepoint_settings(self, settings: ChargePointSettings) -> None:
        """Set chargepoint settings."""
        payload = settings.model_dump(by_alias=True, mode="json")
        charge_point_id = settings.id
        request_uri = f"/api/{API_VERSION}/chargepoints/{charge_point_id}/settings"
        await self._put(request_uri, json=payload)

    async def get_chargepoint_connector_settings(self, charge_point_id: str, connector_id: int) -> ChargePointConnectorSettings:
        """Get chargepoint connector settings."""
        request_uri = f"/api/{API_VERSION}/chargepoints/{charge_point_id}/connectors/{connector_id}/settings"
        response = await self._get(request_uri)
        payload = await response.json()
        return ChargePointConnectorSettings.model_validate(payload)

    async def set_chargepoint_connector_settings(self, settings: ChargePointConnectorSettings) -> None:
        """Set chargepoint connector settings."""
        payload = settings.model_dump(by_alias=True, mode="json")
        charge_point_id = settings.charge_point_id
        connector_id = settings.connector_id
        request_uri = f"/api/{API_VERSION}/chargepoints/{charge_point_id}/connectors/{connector_id}/settings"
        await self._put(request_uri, json=payload)

    async def remote_start(self, charge_point_id: str, connector_id: int, start_auth: StartAuth) -> None:
        """Remote start chargepoint."""
        payload = start_auth.model_dump(by_alias=True, mode="json")
        request_uri = f"/api/{API_VERSION}/chargepoints/{charge_point_id}/connectors/{connector_id}/remotestart"
        await self._put(request_uri, json=payload)

    async def remote_stop(self, charge_point_id: str, connector_id: int) -> None:
        """Remote stop chargepoint."""
        request_uri = f"/api/{API_VERSION}/chargepoints/{charge_point_id}/connectors/{connector_id}/remotestop"
        await self._put(request_uri, json={})

    async def reboot(self, charge_point_id) -> None:
        """Reboot chargepoint."""
        request_uri = f"/api/{API_VERSION}/chargepoints/{charge_point_id}/reboot"
        await self._put(request_uri, json={})
