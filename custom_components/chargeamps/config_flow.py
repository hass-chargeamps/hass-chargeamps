"""Config flow for Chargeamps integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import (
    CONF_API_KEY,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_URL,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import ChargeAmpsClient
from .const import CONF_CHARGEPOINTS, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_URL): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    client = ChargeAmpsClient(
        email=data[CONF_EMAIL],
        password=data[CONF_PASSWORD],
        api_key=data[CONF_API_KEY],
        session=async_get_clientsession(hass),
        api_base_url=data.get(CONF_URL),
    )

    await client.get_chargepoints()

    return {"title": data[CONF_EMAIL]}


class ChargeAmpsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Chargeamps."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ChargeAmpsOptionsFlowHandler:
        """Get the options flow for this handler."""
        return ChargeAmpsOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
            self._abort_if_unique_id_configured()

            try:
                info = await validate_input(self.hass, user_input)
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Import a config entry from YAML without API validation."""
        if "username" in import_data and CONF_EMAIL not in import_data:
            import_data[CONF_EMAIL] = import_data.pop("username")

        await self.async_set_unique_id(import_data[CONF_EMAIL].lower())
        self._abort_if_unique_id_configured()

        options = {}
        if CONF_SCAN_INTERVAL in import_data:
            options[CONF_SCAN_INTERVAL] = import_data.pop(CONF_SCAN_INTERVAL)
        if CONF_CHARGEPOINTS in import_data:
            options[CONF_CHARGEPOINTS] = import_data.pop(CONF_CHARGEPOINTS)

        clean_data = {k: v for k, v in import_data.items() if k in (CONF_EMAIL, CONF_PASSWORD, CONF_API_KEY, CONF_URL)}
        return self.async_create_entry(title=clean_data[CONF_EMAIL], data=clean_data, options=options)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Handle re-authentication — show the form immediately."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Confirm re-authentication."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)
            except Exception:
                _LOGGER.exception("Unexpected exception during re-auth")
                errors["base"] = "unknown"
            else:
                entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
                self.hass.config_entries.async_update_entry(entry, data={**entry.data, **user_input})
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_DATA_SCHEMA, entry.data if entry else {}),
            errors=errors,
        )


class ChargeAmpsOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Chargeamps."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        coordinator = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        chargepoints: dict[str, str] = {}
        if coordinator and coordinator.data:
            chargepoints = {cp_id: cp.name or cp_id for cp_id, cp in coordinator.data.get("chargepoints", {}).items()}

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL.total_seconds()),
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
                    vol.Optional(
                        CONF_CHARGEPOINTS,
                        default=self.config_entry.options.get(CONF_CHARGEPOINTS, []),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[selector.SelectOptionDict(value=cp_id, label=name) for cp_id, name in chargepoints.items()],
                            multiple=True,
                        )
                    ),
                }
            ),
        )
