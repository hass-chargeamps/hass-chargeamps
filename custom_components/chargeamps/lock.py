"""Lock platform for Chargeamps."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.lock import LockEntity, LockEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ChargeAmpsEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ChargeampsLockEntityDescription(LockEntityDescription):
    """Class describing Chargeamps lock entities."""


LOCKS: tuple[ChargeampsLockEntityDescription, ...] = (
    ChargeampsLockEntityDescription(
        key="cable_lock",
        translation_key="cable_lock",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Setup lock platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for cp_id, cp in coordinator.data["chargepoints"].items():
        for connector in cp.connectors:
            for description in LOCKS:
                entities.append(
                    ChargeampsCableLock(coordinator, cp_id, connector.connector_id, description)
                )

    async_add_entities(entities)


class ChargeampsCableLock(ChargeAmpsEntity, LockEntity):
    """Chargeamps Cable Lock class."""

    entity_description: ChargeampsLockEntityDescription

    def __init__(self, coordinator, charge_point_id, connector_id, description):
        super().__init__(coordinator, charge_point_id, connector_id)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{charge_point_id}_{connector_id}_{description.key}"

    @property
    def is_locked(self) -> bool:
        settings = self.coordinator.data["connector_settings"].get(
            (self.charge_point_id, self.connector_id)
        )
        return settings.cable_lock if settings else False

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the cable."""
        settings = self.coordinator.data["connector_settings"].get(
            (self.charge_point_id, self.connector_id)
        )
        if settings:
            settings.cable_lock = True
            await self.coordinator.client.set_chargepoint_connector_settings(settings)
            await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the cable."""
        settings = self.coordinator.data["connector_settings"].get(
            (self.charge_point_id, self.connector_id)
        )
        if settings:
            settings.cable_lock = False
            await self.coordinator.client.set_chargepoint_connector_settings(settings)
            await self.coordinator.async_request_refresh()
