"""Light platform for Chargeamps."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.light import (
    ColorMode,
    LightEntity,
    LightEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ChargeAmpsEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ChargeampsLightEntityDescription(LightEntityDescription):
    """Class describing Chargeamps light entities."""


LIGHTS: tuple[ChargeampsLightEntityDescription, ...] = (
    ChargeampsLightEntityDescription(
        key="dimmer",
        translation_key="dimmer",
    ),
    ChargeampsLightEntityDescription(
        key="downlight",
        translation_key="downlight",
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Setup light platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for cp_id, _cp in coordinator.data["chargepoints"].items():
        cp_settings = coordinator.data["settings"].get(cp_id)
        if cp_settings:
            if cp_settings.dimmer is not None:
                entities.append(ChargeampsLight(coordinator, cp_id, LIGHTS[0]))
            if cp_settings.down_light is not None:
                entities.append(ChargeampsLight(coordinator, cp_id, LIGHTS[1]))

    async_add_entities(entities)


class ChargeampsLight(ChargeAmpsEntity, LightEntity):
    """Chargeamps Light class."""

    entity_description: ChargeampsLightEntityDescription

    def __init__(self, coordinator, charge_point_id, description):
        """Initialize the light."""
        super().__init__(coordinator, charge_point_id)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{charge_point_id}_{description.key}"
        if description.key == "dimmer":
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_supported_color_modes = {ColorMode.ONOFF}
            self._attr_color_mode = ColorMode.ONOFF

    @property
    def is_on(self) -> bool:
        """Return true if the light is on."""
        settings = self.coordinator.data["settings"].get(self.charge_point_id)
        if not settings:
            return False
        if self.entity_description.key == "downlight":
            return bool(settings.down_light)
        return settings.dimmer not in ("Off", "off", None)

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        if self.entity_description.key != "dimmer":
            return None
        settings = self.coordinator.data["settings"].get(self.charge_point_id)
        if not settings:
            return None
        brightness_map = {"Off": 0, "Low": 85, "Medium": 170, "High": 255}
        return brightness_map.get(settings.dimmer, 0)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        settings = self.coordinator.data["settings"].get(self.charge_point_id)
        if not settings:
            return

        if self.entity_description.key == "dimmer":
            brightness = kwargs.get("brightness")
            if brightness is not None:
                if brightness == 0:
                    settings.dimmer = "Off"
                elif brightness < 128:
                    settings.dimmer = "Low"
                elif brightness < 192:
                    settings.dimmer = "Medium"
                else:
                    settings.dimmer = "High"
            else:
                settings.dimmer = "High"
        else:
            settings.down_light = True

        await self.coordinator.client.set_chargepoint_settings(settings)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        settings = self.coordinator.data["settings"].get(self.charge_point_id)
        if not settings:
            return

        if self.entity_description.key == "dimmer":
            settings.dimmer = "Off"
        else:
            settings.down_light = False

        await self.coordinator.client.set_chargepoint_settings(settings)
        await self.coordinator.async_request_refresh()
