"""Sensor platform for Chargeamps."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    STATE_UNAVAILABLE,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ChargeAmpsEntity
from .const import CHARGEPOINT_ONLINE, DOMAIN, ICON_MAP, DEFAULT_ICON, STATUS_OCPP_MAP, STATUS_CAPI_MAP

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ChargeampsSensorEntityDescription(SensorEntityDescription):
    """Class describing Chargeamps sensor entities."""


CONNECTOR_SENSORS: tuple[ChargeampsSensorEntityDescription, ...] = (
    ChargeampsSensorEntityDescription(
        key="status",
        translation_key="status",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ChargeampsSensorEntityDescription(
        key="power",
        translation_key="power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ChargeampsSensorEntityDescription(
        key="l1_current",
        translation_key="l1_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ChargeampsSensorEntityDescription(
        key="l2_current",
        translation_key="l2_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ChargeampsSensorEntityDescription(
        key="l3_current",
        translation_key="l3_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ChargeampsSensorEntityDescription(
        key="l1_voltage",
        translation_key="l1_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ChargeampsSensorEntityDescription(
        key="l2_voltage",
        translation_key="l2_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ChargeampsSensorEntityDescription(
        key="l3_voltage",
        translation_key="l3_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

CHARGEPOINT_SENSORS: tuple[ChargeampsSensorEntityDescription, ...] = (
    ChargeampsSensorEntityDescription(
        key="total_energy",
        translation_key="total_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Setup sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for cp_id, cp in coordinator.data["chargepoints"].items():
        for description in CHARGEPOINT_SENSORS:
            entities.append(ChargeampsChargePointSensor(coordinator, cp_id, description))

        for connector in cp.connectors:
            for description in CONNECTOR_SENSORS:
                entities.append(ChargeampsConnectorSensor(coordinator, cp_id, connector.connector_id, description))

    async_add_entities(entities)


class ChargeampsConnectorSensor(ChargeAmpsEntity, SensorEntity):
    """Chargeamps Connector Sensor class."""

    entity_description: ChargeampsSensorEntityDescription

    def __init__(self, coordinator, charge_point_id, connector_id, description):
        """Initialize the connector sensor."""
        super().__init__(coordinator, charge_point_id, connector_id)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{charge_point_id}_{connector_id}_{description.key}"

    @property
    def native_value(self) -> float | str | None:
        """Return the current sensor value."""
        cp_status = self.coordinator.data["status"].get(self.charge_point_id)
        if not cp_status:
            return None

        for conn_status in cp_status.connector_statuses:
            if conn_status.connector_id == self.connector_id:
                if self.entity_description.key == "status":
                    if cp_status.status != CHARGEPOINT_ONLINE:
                        return STATE_UNAVAILABLE
                    raw_status = str(conn_status.status)
                    return STATUS_OCPP_MAP.get(raw_status, STATUS_CAPI_MAP.get(raw_status, raw_status))

                if self.entity_description.key == "power":
                    if conn_status.measurements:
                        return round(sum((m.current or 0.0) * (m.voltage or 0.0) for m in conn_status.measurements), 1)
                    return 0.0

                if "current" in self.entity_description.key or "voltage" in self.entity_description.key:
                    phase = self.entity_description.key.split("_")[0].upper()
                    if conn_status.measurements:
                        for m in conn_status.measurements:
                            if m.phase == phase:
                                if "current" in self.entity_description.key:
                                    return round(m.current, 2) if m.current is not None else 0.0
                                return round(m.voltage, 1) if m.voltage is not None else 0.0
                    return 0.0
        return None

    @property
    def icon(self) -> str | None:
        """Return the icon for the sensor."""
        if self.entity_description.key == "status":
            if self.connector_name == "Schuko":
                return ICON_MAP.get("Schuko", DEFAULT_ICON)
            cp = self.coordinator.data["chargepoints"].get(self.charge_point_id)
            if cp:
                for conn in cp.connectors:
                    if conn.connector_id == self.connector_id:
                        return ICON_MAP.get(conn.type, DEFAULT_ICON)
        return super().icon

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        attrs = {"charge_point_id": self.charge_point_id, "connector_id": self.connector_id}
        if self.entity_description.key == "status":
            cp_status = self.coordinator.data["status"].get(self.charge_point_id)
            if cp_status:
                for conn_status in cp_status.connector_statuses:
                    if conn_status.connector_id == self.connector_id:
                        attrs["total_consumption_kwh"] = round(conn_status.total_consumption_kwh, 3)
                        attrs["raw_status"] = conn_status.status
                        break
        return attrs


class ChargeampsChargePointSensor(ChargeAmpsEntity, SensorEntity):
    """Chargeamps ChargePoint Sensor class."""

    entity_description: ChargeampsSensorEntityDescription

    def __init__(self, coordinator, charge_point_id, description):
        """Initialize the charge point sensor."""
        super().__init__(coordinator, charge_point_id)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{charge_point_id}_{description.key}"

    @property
    def native_value(self) -> float | None:
        """Return the current sensor value."""
        if self.entity_description.key == "total_energy":
            return self.coordinator.data["total_energy"].get(self.charge_point_id)
        return None
