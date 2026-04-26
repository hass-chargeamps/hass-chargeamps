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

    @property
    def is_on(self) -> bool:
        """Return true if charging is enabled."""
        settings = self.coordinator.data["connector_settings"].get((self.charge_point_id, self.connector_id))
        return settings.mode == "On" if settings else False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        settings = self.coordinator.data["connector_settings"].get((self.charge_point_id, self.connector_id))
        if settings:
            settings.mode = "On"
            await self.coordinator.client.set_chargepoint_connector_settings(settings)
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        settings = self.coordinator.data["connector_settings"].get((self.charge_point_id, self.connector_id))
        if settings:
            settings.mode = "Off"
            await self.coordinator.client.set_chargepoint_connector_settings(settings)
            await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        attrs = {"charge_point_id": self.charge_point_id, "connector_id": self.connector_id}
        settings = self.coordinator.data["connector_settings"].get((self.charge_point_id, self.connector_id))
        if settings:
            attrs["cable_lock"] = settings.cable_lock
            attrs["max_current"] = round(settings.max_current or 0)
        return attrs
