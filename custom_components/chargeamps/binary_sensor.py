"""Binary sensor platform for Chargeamps."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ChargeAmpsEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Statuses that indicate a cable is plugged in
CONNECTED_STATUSES = [
    "Preparing",
    "Charging",
    "Connected",
    "SuspendedEVSE",
    "SuspendedEV",
    "Finishing",
    "1",  # Preparing (mapped)
    "2",  # Charging (mapped)
    "3",  # SuspendedEVSE (mapped)
    "4",  # SuspendedEV (mapped)
    "5",  # Finishing (mapped)
]


@dataclass(frozen=True, kw_only=True)
class ChargeampsBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Class describing Chargeamps binary sensor entities."""


BINARY_SENSORS: tuple[ChargeampsBinarySensorEntityDescription, ...] = (
    ChargeampsBinarySensorEntityDescription(
        key="cable_connected",
        translation_key="cable_connected",
        device_class=BinarySensorDeviceClass.PLUG,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Setup binary sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for cp_id, cp in coordinator.data["chargepoints"].items():
        for connector in cp.connectors:
            for description in BINARY_SENSORS:
                entities.append(ChargeampsBinarySensor(coordinator, cp_id, connector.connector_id, description))

    async_add_entities(entities)


class ChargeampsBinarySensor(ChargeAmpsEntity, BinarySensorEntity):
    """Chargeamps Binary Sensor class."""

    entity_description: ChargeampsBinarySensorEntityDescription

    def __init__(self, coordinator, charge_point_id, connector_id, description):
        """Initialize the binary sensor."""
        super().__init__(coordinator, charge_point_id, connector_id)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{charge_point_id}_{connector_id}_{description.key}"

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        cp_status = self.coordinator.data["status"].get(self.charge_point_id)
        if not cp_status:
            return False

        for conn_status in cp_status.connector_statuses:
            if conn_status.connector_id == self.connector_id and self.entity_description.key == "cable_connected":
                return str(conn_status.status) in CONNECTED_STATUSES
        return False
