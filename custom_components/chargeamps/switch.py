"""Switch platform for Chargeamps."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ChargeAmpsEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ChargeampsSwitchEntityDescription(SwitchEntityDescription):
    """Class describing Chargeamps switch entities."""


SWITCHES: tuple[ChargeampsSwitchEntityDescription, ...] = (
    ChargeampsSwitchEntityDescription(
        key="enable",
        translation_key="enable",
    ),
    ChargeampsSwitchEntityDescription(
        key="schedule",
        translation_key="schedule",
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Setup switch platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for cp_id, cp in coordinator.data["chargepoints"].items():
        for connector in cp.connectors:
            for description in SWITCHES:
                entities.append(ChargeampsSwitch(coordinator, cp_id, connector.connector_id, description))

    async_add_entities(entities)


class ChargeampsSwitch(ChargeAmpsEntity, SwitchEntity):
    """Chargeamps Switch class."""

    entity_description: ChargeampsSwitchEntityDescription

    def __init__(self, coordinator, charge_point_id, connector_id, description):
        """Initialize the switch."""
        super().__init__(coordinator, charge_point_id, connector_id)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{charge_point_id}_{connector_id}_{description.key}"

    def _mode(self) -> str | None:
        settings = self.coordinator.data["connector_settings"].get((self.charge_point_id, self.connector_id))
        return settings.mode if settings else None

    async def _set_mode(self, mode: str) -> None:
        settings = self.coordinator.data["connector_settings"].get((self.charge_point_id, self.connector_id))
        if settings:
            settings.mode = mode
            await self.coordinator.client.set_chargepoint_connector_settings(settings)
            await self.coordinator.async_request_refresh()

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        mode = self._mode()
        if self.entity_description.key == "enable":
            # On when charging is authorized — either directly (On) or via schedule (Schedule)
            return mode in ("On", "Schedule")
        if self.entity_description.key == "schedule":
            return mode == "Schedule"
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        if self.entity_description.key == "enable":
            # No-op if schedule is active — don't silently exit schedule mode
            if self._mode() != "Schedule":
                await self._set_mode("On")
        elif self.entity_description.key == "schedule":
            await self._set_mode("Schedule")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        if self.entity_description.key == "enable":
            # Always sets Off — explicitly overrides the schedule if one is active
            await self._set_mode("Off")
        elif self.entity_description.key == "schedule":
            # Return to unrestricted charging rather than leaving the charger off
            await self._set_mode("On")

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        attrs = {"charge_point_id": self.charge_point_id, "connector_id": self.connector_id}
        settings = self.coordinator.data["connector_settings"].get((self.charge_point_id, self.connector_id))
        if settings:
            attrs["mode"] = settings.mode
            attrs["cable_lock"] = settings.cable_lock
            attrs["max_current"] = round(settings.max_current or 0)
        return attrs
