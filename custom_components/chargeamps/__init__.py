"""Component to integrate with Chargeamps."""

import logging
from datetime import timedelta
from typing import Optional

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_API_KEY,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import (
    ChargeAmpsClient,
    ChargePointConnectorStatus,
    ChargePointStatus,
    StartAuth,
)
from .const import (
    CONFIGURATION_URL,
    DEFAULT_SCAN_INTERVAL,
    DIMMER_VALUES,
    DOMAIN,
    MANUFACTURER,
    PLATFORMS,
)
from .coordinator import ChargeAmpsDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up this component using YAML."""
    if DOMAIN not in config:
        return True

    # Legacy YAML support - migrate to config flow
    conf = config[DOMAIN]
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "import"}, data=conf
        )
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up this component from a config entry."""
    client = ChargeAmpsClient(
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        api_key=entry.data[CONF_API_KEY],
        session=async_get_clientsession(hass),
        api_base_url=entry.data.get(CONF_URL),
    )

    scan_interval_seconds = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL.total_seconds())
    scan_interval = timedelta(seconds=scan_interval_seconds)

    coordinator = ChargeAmpsDataUpdateCoordinator(hass, client, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Register services once
    setup_services(hass)

    # Webhook support
    webhook_id = f"{DOMAIN}_{entry.entry_id}"
    webhook.async_register(
        hass,
        DOMAIN,
        "Chargeamps Callback",
        webhook_id,
        async_handle_webhook,
    )
    _LOGGER.info("Registered webhook: %s", webhook_id)

    return True


def setup_services(hass: HomeAssistant) -> None:
    """Register services for Chargeamps."""
    if hass.services.has_service(DOMAIN, "set_max_current"):
        return

    async def get_coordinator(chargepoint_id: str) -> Optional[ChargeAmpsDataUpdateCoordinator]:
        """Find the coordinator matching a charge point ID."""
        for coordinator in hass.data[DOMAIN].values():
            if chargepoint_id in coordinator.data["chargepoints"]:
                return coordinator
        return None

    async def async_set_max_current(call: ServiceCall):
        cp_id = call.data["chargepoint"]
        conn_id = call.data["connector"]
        max_curr = call.data["max_current"]
        
        if coordinator := await get_coordinator(cp_id):
            settings = coordinator.data["connector_settings"].get((cp_id, conn_id))
            if settings:
                settings.max_current = max_curr
                await coordinator.client.set_chargepoint_connector_settings(settings)
                await coordinator.async_request_refresh()
        else:
            _LOGGER.error("Chargepoint %s not found in any configured account", cp_id)

    async def async_set_light(call: ServiceCall):
        cp_id = call.data["chargepoint"]
        dimmer = call.data.get("dimmer")
        downlight = call.data.get("downlight")
        
        if coordinator := await get_coordinator(cp_id):
            settings = coordinator.data["settings"].get(cp_id)
            if settings:
                if dimmer:
                    settings.dimmer = dimmer.capitalize()
                if downlight is not None:
                    settings.down_light = downlight
                await coordinator.client.set_chargepoint_settings(settings)
                await coordinator.async_request_refresh()

    async def async_enable_ev(call: ServiceCall):
        cp_id = call.data["chargepoint"]
        conn_id = call.data["connector"]
        if coordinator := await get_coordinator(cp_id):
            settings = coordinator.data["connector_settings"].get((cp_id, conn_id))
            if settings:
                settings.mode = "On"
                await coordinator.client.set_chargepoint_connector_settings(settings)
                await coordinator.async_request_refresh()

    async def async_disable_ev(call: ServiceCall):
        cp_id = call.data["chargepoint"]
        conn_id = call.data["connector"]
        if coordinator := await get_coordinator(cp_id):
            settings = coordinator.data["connector_settings"].get((cp_id, conn_id))
            if settings:
                settings.mode = "Off"
                await coordinator.client.set_chargepoint_connector_settings(settings)
                await coordinator.async_request_refresh()

    async def async_cable_lock(call: ServiceCall):
        cp_id = call.data["chargepoint"]
        conn_id = call.data["connector"]
        if coordinator := await get_coordinator(cp_id):
            settings = coordinator.data["connector_settings"].get((cp_id, conn_id))
            if settings:
                settings.cable_lock = True
                await coordinator.client.set_chargepoint_connector_settings(settings)
                await coordinator.async_request_refresh()

    async def async_cable_unlock(call: ServiceCall):
        cp_id = call.data["chargepoint"]
        conn_id = call.data["connector"]
        if coordinator := await get_coordinator(cp_id):
            settings = coordinator.data["connector_settings"].get((cp_id, conn_id))
            if settings:
                settings.cable_lock = False
                await coordinator.client.set_chargepoint_connector_settings(settings)
                await coordinator.async_request_refresh()

    async def async_remote_start(call: ServiceCall):
        cp_id = call.data["chargepoint"]
        conn_id = call.data["connector"]
        auth = StartAuth(
            rfid_length=call.data.get("rfid_length", 4),
            rfid_format=call.data.get("rfid_format", "Dec"),
            rfid=call.data["rfid"],
            external_transaction_id=call.data.get("external_transaction_id", "0"),
        )
        if coordinator := await get_coordinator(cp_id):
            await coordinator.client.remote_start(cp_id, conn_id, auth)
            await coordinator.async_request_refresh()

    async def async_remote_stop(call: ServiceCall):
        cp_id = call.data["chargepoint"]
        conn_id = call.data["connector"]
        if coordinator := await get_coordinator(cp_id):
            await coordinator.client.remote_stop(cp_id, conn_id)
            await coordinator.async_request_refresh()

    services = {
        "set_max_current": async_set_max_current,
        "set_light": async_set_light,
        "enable": async_enable_ev,
        "disable": async_disable_ev,
        "cable_lock": async_cable_lock,
        "cable_unlock": async_cable_unlock,
        "remote_start": async_remote_start,
        "remote_stop": async_remote_stop,
    }

    for name, handler in services.items():
        hass.services.async_register(DOMAIN, name, handler)


async def async_handle_webhook(hass: HomeAssistant, webhook_id: str, request):
    """Handle incoming webhook from Charge Amps."""
    _LOGGER.debug("Received webhook: %s", webhook_id)
    try:
        data = await request.json()
    except Exception:
        _LOGGER.error("Received invalid JSON in webhook")
        return None

    cp_id = data.get("id") or data.get("chargePointId")
    if not cp_id:
        _LOGGER.warning("Webhook data missing charge point ID")
        return None

    target_coordinator = None
    for coordinator in hass.data[DOMAIN].values():
        if cp_id in coordinator.data["chargepoints"]:
            target_coordinator = coordinator
            break
    
    if not target_coordinator:
        _LOGGER.warning("No coordinator found for charge point %s", cp_id)
        return None

    # Heartbeat callback
    if "connectorStatuses" in data:
        try:
            status = ChargePointStatus.model_validate(data)
            target_coordinator.data["status"][cp_id] = status
            _LOGGER.debug("Updated status via heartbeat for %s", cp_id)
        except Exception as exc:
            _LOGGER.error("Error validating heartbeat webhook: %s", exc)
    
    # MeterValue callback
    elif "meterValueList" in data:
        for mv in data["meterValueList"]:
            conn_id = mv.get("connectorId")
            total_kwh = mv.get("totalConsumptionKWh")
            status = target_coordinator.data["status"].get(cp_id)
            if status:
                new_statuses = []
                for conn_status in status.connector_statuses:
                    if conn_status.connector_id == conn_id:
                        new_conn_status = conn_status.model_copy(update={
                            "total_consumption_kwh": total_kwh or conn_status.total_consumption_kwh,
                            "measurements": mv.get("measurements") or conn_status.measurements,
                        })
                        new_statuses.append(new_conn_status)
                    else:
                        new_statuses.append(conn_status)
                
                target_coordinator.data["status"][cp_id] = status.model_copy(update={
                    "connector_statuses": new_statuses
                })
        _LOGGER.debug("Updated measurements via metervalue for %s", cp_id)

    target_coordinator.async_set_updated_data(target_coordinator.data)
    return None


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        webhook_id = f"{DOMAIN}_{entry.entry_id}"
        webhook.async_unregister(hass, webhook_id)
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)


class ChargeAmpsEntity(CoordinatorEntity[ChargeAmpsDataUpdateCoordinator]):
    """Chargeamps Entity class."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChargeAmpsDataUpdateCoordinator,
        charge_point_id: str,
        connector_id: Optional[int] = None,
    ):
        super().__init__(coordinator)
        self.charge_point_id = charge_point_id
        self.connector_id = connector_id
        if connector_id is not None:
            self._attr_translation_placeholders = {"connector": self.connector_name}

    @property
    def charge_point_name(self) -> str:
        """Return the charge point name."""
        cp = self.coordinator.data["chargepoints"].get(self.charge_point_id)
        return cp.name if cp else self.charge_point_id

    @property
    def connector_name(self) -> str:
        """Return the connector name, handling Halo Schuko logic."""
        if self.connector_id is None:
            return ""
        cp = self.coordinator.data["chargepoints"].get(self.charge_point_id)
        if cp and cp.type == "Halo" and self.connector_id == 2:
            return "Schuko"
        return f"Connector {self.connector_id}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this entity."""
        cp = self.coordinator.data["chargepoints"].get(self.charge_point_id)
        return DeviceInfo(
            identifiers={(DOMAIN, self.charge_point_id)},
            name=self.charge_point_name,
            manufacturer=MANUFACTURER,
            model=cp.type if cp else None,
            sw_version=cp.firmware_version if cp else None,
            configuration_url=CONFIGURATION_URL,
        )
