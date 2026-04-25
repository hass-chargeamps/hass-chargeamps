"""Button platform for Chargeamps."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ChargeAmpsEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ChargeampsButtonEntityDescription(ButtonEntityDescription):
    """Class describing Chargeamps button entities."""


BUTTONS: tuple[ChargeampsButtonEntityDescription, ...] = (
    ChargeampsButtonEntityDescription(
        key="reboot",
        translation_key="reboot",
        device_class="restart",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Setup button platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for cp_id in coordinator.data["chargepoints"]:
        for description in BUTTONS:
            entities.append(ChargeampsButton(coordinator, cp_id, description))

    async_add_entities(entities)


class ChargeampsButton(ChargeAmpsEntity, ButtonEntity):
    """Chargeamps Button class."""

    entity_description: ChargeampsButtonEntityDescription

    def __init__(self, coordinator, charge_point_id, description):
        super().__init__(coordinator, charge_point_id)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{charge_point_id}_{description.key}"

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Rebooting chargepoint %s", self.charge_point_id)
        await self.coordinator.client.reboot(self.charge_point_id)
