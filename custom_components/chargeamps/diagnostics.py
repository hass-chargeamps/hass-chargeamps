"""Diagnostics support for Chargeamps."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import redact_datacyclic
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import DOMAIN

REDACT_KEYS = {CONF_API_KEY, CONF_EMAIL, CONF_PASSWORD, "password", "rfid"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    diagnostics_data = {
        "entry": {
            "title": entry.title,
            "data": redact_datacyclic(entry.data, REDACT_KEYS),
            "options": redact_datacyclic(entry.options, REDACT_KEYS),
        },
        "data": redact_datacyclic(coordinator.data, REDACT_KEYS),
    }

    return diagnostics_data
