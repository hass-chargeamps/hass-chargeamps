"""Number platform for Chargeamps."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ChargeAmpsEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ChargeampsNumberEntityDescription(NumberEntityDescription):
    """Class describing Chargeamps number entities."""


NUMBERS: tuple[ChargeampsNumberEntityDescription, ...] = (
    ChargeampsNumberEntityDescription(
        key="max_current",
        translation_key="max_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class="current",
        mode=NumberMode.BOX,
        native_min_value=6,
        native_max_value=32,
        native_step=1,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Setup number platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for cp_id, cp in coordinator.data["chargepoints"].items():
        for connector in cp.connectors:
            for description in NUMBERS:
                entities.append(ChargeampsNumber(coordinator, cp_id, connector.connector_id, description))

    async_add_entities(entities)


class ChargeampsNumber(ChargeAmpsEntity, NumberEntity):
    """Chargeamps Number class."""

    entity_description: ChargeampsNumberEntityDescription

    def __init__(self, coordinator, charge_point_id, connector_id, description):
        """Initialize the number entity."""
        super().__init__(coordinator, charge_point_id, connector_id)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{charge_point_id}_{connector_id}_{description.key}"

    @property
    def native_value(self) -> float:
        """Return the current maximum current setting."""
        settings = self.coordinator.data["connector_settings"].get((self.charge_point_id, self.connector_id))
        return float(settings.max_current) if settings and settings.max_current else 6.0

    async def async_set_native_value(self, value: float) -> None:
        """Set the maximum current."""
        settings = self.coordinator.data["connector_settings"].get((self.charge_point_id, self.connector_id))
        if settings:
            settings.max_current = value
            await self.coordinator.client.set_chargepoint_connector_settings(settings)
            await self.coordinator.async_request_refresh()
