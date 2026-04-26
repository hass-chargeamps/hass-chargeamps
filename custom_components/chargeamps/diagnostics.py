"""Diagnostics support for Chargeamps."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import CONF_WEBHOOK_SECRET, DOMAIN, WEBHOOK_AUTH_HEADER

REDACT_KEYS = {CONF_API_KEY, CONF_EMAIL, CONF_PASSWORD, CONF_WEBHOOK_SECRET, "password", "rfid"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    try:
        base_url = get_url(hass, prefer_external=True)
        webhook_base = f"{base_url}/api/chargeamps/{entry.entry_id}"
    except NoURLAvailableError:
        webhook_base = f"<ha-external-url>/api/chargeamps/{entry.entry_id}"

    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(entry.data, REDACT_KEYS),
            "options": async_redact_data(entry.options, REDACT_KEYS),
        },
        "webhook": {
            "base_url": webhook_base,
            "auth_header_key": WEBHOOK_AUTH_HEADER,
            "auth_header_value": "<redacted>" if entry.data.get(CONF_WEBHOOK_SECRET) else "not yet generated",
        },
        "data": async_redact_data(coordinator.data, REDACT_KEYS),
    }
