"""Diagnostics support for Chargeamps."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import redact_datacyclic
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import CONF_WEBHOOK_SECRET, DOMAIN, WEBHOOK_AUTH_HEADER

# webhook_secret is intentionally NOT redacted — it is an inbound-only token
# that lets Charge Amps authenticate callbacks to HA. It does not grant access
# to the Charge Amps API or the user's account.
REDACT_KEYS = {CONF_API_KEY, CONF_EMAIL, CONF_PASSWORD, "password", "rfid"}


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
            "data": redact_datacyclic(entry.data, REDACT_KEYS),
            "options": redact_datacyclic(entry.options, REDACT_KEYS),
        },
        "webhook": {
            "base_url": webhook_base,
            "auth_header_key": WEBHOOK_AUTH_HEADER,
            "auth_header_value": entry.data.get(CONF_WEBHOOK_SECRET, "not yet generated"),
        },
        "data": redact_datacyclic(coordinator.data, REDACT_KEYS),
    }
