"""Component to integrate with Chargeamps."""

import logging
import secrets
from datetime import timedelta
from typing import Optional

from aiohttp.web import Response
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    CONF_API_KEY,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_URL,
)
from homeassistant.components.persistent_notification import async_create as notify_create
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import (
    ChargeAmpsClient,
    ChargePointMeasurement,
    ChargePointStatus,
    StartAuth,
)
from .const import (
    CONF_CHARGEPOINTS,
    CONF_WEBHOOK_SECRET,
    CONFIGURATION_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    PLATFORMS,
    WEBHOOK_AUTH_HEADER,
)
from .coordinator import ChargeAmpsDataUpdateCoordinator

_VIEWS_REGISTERED = "_views_registered"

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up this component using YAML."""
    if DOMAIN not in config:
        return True

    # Legacy YAML support - migrate to config flow
    conf = config[DOMAIN]
    hass.async_create_task(hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data=conf))

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
    chargepoint_ids = entry.options.get(CONF_CHARGEPOINTS) or None

    coordinator = ChargeAmpsDataUpdateCoordinator(hass, client, scan_interval, chargepoint_ids)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Register services once
    setup_services(hass)

    # Register HTTP views once — they route by entry_id internally
    if not hass.data[DOMAIN].get(_VIEWS_REGISTERED):
        hass.http.register_view(ChargeAmpsHealthView())
        hass.http.register_view(ChargeAmpsCallbackView())
        hass.http.register_view(ChargeAmpsConnectorCallbackView())
        hass.data[DOMAIN][_VIEWS_REGISTERED] = True

    try:
        base_url = get_url(hass, prefer_external=True)
    except NoURLAvailableError:
        base_url = "<your-ha-external-url>"

    webhook_base = f"{base_url}/api/chargeamps/{entry.entry_id}"

    # Generate webhook secret on first setup and notify the user
    if CONF_WEBHOOK_SECRET not in entry.data:
        secret = secrets.token_hex(32)
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_WEBHOOK_SECRET: secret})
        notify_create(
            hass,
            (
                f"## Charge Amps — Callback / Webhook Setup\n\n"
                f"To enable real-time updates, contact **Charge Amps support** and "
                f"provide the following details:\n\n"
                f"| | |\n"
                f"|---|---|\n"
                f"| **Base URL** | `{webhook_base}` |\n"
                f"| **Auth header key** | `{WEBHOOK_AUTH_HEADER}` |\n"
                f"| **Auth header value** | `{secret}` |\n\n"
                f"**Verify reachability first** — run this from a terminal outside your home network "
                f"(or use a tool like [reqbin.com](https://reqbin.com)):\n\n"
                f"```\nGET {webhook_base}\n{WEBHOOK_AUTH_HEADER}: {secret}\n```\n\n"
                f"- `200 OK` → ready to hand to Charge Amps support\n"
                f"- `401` → URL correct but secret wrong\n"
                f"- `404` → URL unreachable or wrong\n\n"
                f"You can dismiss this notification once you have noted the details. "
                f"The information is also available under **integration diagnostics**."
            ),
            title="Charge Amps Webhook Credentials",
            notification_id=f"{DOMAIN}_webhook_{entry.entry_id}",
        )

    return True


def setup_services(hass: HomeAssistant) -> None:
    """Register services for Chargeamps."""
    if hass.services.has_service(DOMAIN, "set_max_current"):
        return

    async def get_coordinator(chargepoint_id: str) -> Optional[ChargeAmpsDataUpdateCoordinator]:
        """Find the coordinator matching a charge point ID."""
        for value in hass.data[DOMAIN].values():
            if not isinstance(value, ChargeAmpsDataUpdateCoordinator):
                continue
            if chargepoint_id in value.data["chargepoints"]:
                return value
        return None

    async def async_set_max_current(call: ServiceCall):
        """Set the maximum charging current for a connector."""
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
        """Set the dimmer and/or downlight settings for a charge point."""
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
        """Enable EV charging on a connector."""
        cp_id = call.data["chargepoint"]
        conn_id = call.data["connector"]
        if coordinator := await get_coordinator(cp_id):
            settings = coordinator.data["connector_settings"].get((cp_id, conn_id))
            if settings:
                settings.mode = "On"
                await coordinator.client.set_chargepoint_connector_settings(settings)
                await coordinator.async_request_refresh()

    async def async_disable_ev(call: ServiceCall):
        """Disable EV charging on a connector."""
        cp_id = call.data["chargepoint"]
        conn_id = call.data["connector"]
        if coordinator := await get_coordinator(cp_id):
            settings = coordinator.data["connector_settings"].get((cp_id, conn_id))
            if settings:
                settings.mode = "Off"
                await coordinator.client.set_chargepoint_connector_settings(settings)
                await coordinator.async_request_refresh()

    async def async_cable_lock(call: ServiceCall):
        """Lock the cable on a connector."""
        cp_id = call.data["chargepoint"]
        conn_id = call.data["connector"]
        if coordinator := await get_coordinator(cp_id):
            settings = coordinator.data["connector_settings"].get((cp_id, conn_id))
            if settings:
                settings.cable_lock = True
                await coordinator.client.set_chargepoint_connector_settings(settings)
                await coordinator.async_request_refresh()

    async def async_cable_unlock(call: ServiceCall):
        """Unlock the cable on a connector."""
        cp_id = call.data["chargepoint"]
        conn_id = call.data["connector"]
        if coordinator := await get_coordinator(cp_id):
            settings = coordinator.data["connector_settings"].get((cp_id, conn_id))
            if settings:
                settings.cable_lock = False
                await coordinator.client.set_chargepoint_connector_settings(settings)
                await coordinator.async_request_refresh()

    async def async_remote_start(call: ServiceCall):
        """Remotely start a charging session on a connector."""
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
        """Remotely stop a charging session on a connector."""
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


def _get_coordinator_for_entry(hass: HomeAssistant, entry_id: str):
    """Return the coordinator for a given entry_id, or None."""
    return hass.data.get(DOMAIN, {}).get(entry_id)


def _auth_ok(request, entry) -> bool:
    """Validate the x-api-key header against the stored webhook secret."""
    expected = entry.data.get(CONF_WEBHOOK_SECRET)
    return expected and request.headers.get(WEBHOOK_AUTH_HEADER) == expected


class ChargeAmpsHealthView(HomeAssistantView):
    """Health-check endpoint — GET /api/chargeamps/{entry_id} returns 200 OK."""

    url = "/api/chargeamps/{entry_id}"
    name = "api:chargeamps:health"
    requires_auth = False

    async def get(self, request, entry_id: str):
        """Handle health-check GET request."""
        hass = request.app["hass"]
        entry = hass.config_entries.async_get_entry(entry_id)
        if not entry or not _auth_ok(request, entry):
            return Response(status=401)
        return Response(status=200)


class ChargeAmpsCallbackView(HomeAssistantView):
    """Handle boot / heartbeat / metervalue callbacks from Charge Amps."""

    url = "/api/chargeamps/{entry_id}/chargepoints/{chargepoint_id}/{event}"
    name = "api:chargeamps:callback"
    requires_auth = False

    async def post(self, request, entry_id: str, chargepoint_id: str, event: str):
        """Handle charge point event callback POST request."""
        hass = request.app["hass"]
        entry = hass.config_entries.async_get_entry(entry_id)
        if not entry or not _auth_ok(request, entry):
            return Response(status=401)

        coordinator = _get_coordinator_for_entry(hass, entry_id)
        if not coordinator:
            return Response(status=503)

        try:
            data = await request.json()
        except Exception:
            _LOGGER.error("Charge Amps callback: invalid JSON for event '%s'", event)
            return Response(status=400)

        _LOGGER.debug("Charge Amps callback: event=%s chargepoint=%s", event, chargepoint_id)

        if event == "boot":
            await coordinator.async_request_refresh()

        elif event == "heartbeat":
            try:
                status = ChargePointStatus.model_validate(data)
                coordinator.data["status"][chargepoint_id] = status
                coordinator.async_set_updated_data(coordinator.data)
            except Exception as exc:
                _LOGGER.error("Heartbeat parse error: %s", exc)
                return Response(status=422)

        elif event == "metervalue":
            for mv in data.get("meterValueList", []):
                conn_id = mv.get("connectorId")
                total_kwh = mv.get("totalConsumptionKWh")
                status = coordinator.data["status"].get(chargepoint_id)
                if not status:
                    continue
                new_statuses = [
                    cs.model_copy(
                        update={
                            "total_consumption_kwh": total_kwh or cs.total_consumption_kwh,
                            "measurements": [ChargePointMeasurement.model_validate(m) for m in mv.get("measurements") or []]
                            or cs.measurements,
                        }
                    )
                    if cs.connector_id == conn_id
                    else cs
                    for cs in status.connector_statuses
                ]
                coordinator.data["status"][chargepoint_id] = status.model_copy(update={"connector_statuses": new_statuses})
            coordinator.async_set_updated_data(coordinator.data)

        return Response(status=200)


class ChargeAmpsConnectorCallbackView(HomeAssistantView):
    """Handle connector Start / Stop callbacks from Charge Amps."""

    url = "/api/chargeamps/{entry_id}/chargepoints/{chargepoint_id}/connectors/{connector_id}/{event}"
    name = "api:chargeamps:connector_callback"
    requires_auth = False

    async def post(self, request, entry_id: str, chargepoint_id: str, connector_id: str, event: str):
        """Handle connector event callback POST request."""
        hass = request.app["hass"]
        entry = hass.config_entries.async_get_entry(entry_id)
        if not entry or not _auth_ok(request, entry):
            return Response(status=401)

        coordinator = _get_coordinator_for_entry(hass, entry_id)
        if not coordinator:
            return Response(status=503)

        _LOGGER.debug(
            "Charge Amps callback: event=%s chargepoint=%s connector=%s",
            event,
            chargepoint_id,
            connector_id,
        )

        # Trigger a full refresh so the new session data is fetched from the API
        await coordinator.async_request_refresh()
        return Response(status=200)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
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
        """Initialize the entity."""
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
