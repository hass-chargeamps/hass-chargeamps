"""Light platform for Chargeamps."""

import logging

from homeassistant.components.light import (
    ColorMode,
    LightEntity,
    filter_supported_color_modes,
)

from . import ChargeampsEntity
from .const import DOMAIN, DOMAIN_DATA, SCAN_INTERVAL  # noqa

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):  # pylint: disable=unused-argument
    """Setup light platform."""
    lights = []
    handler = hass.data[DOMAIN_DATA]["handler"]
    for cp_id in handler.charge_point_ids:
        cp_info = handler.get_chargepoint_info(cp_id)
        cp_settings = handler.get_chargepoint_settings(cp_id)
        _LOGGER.debug("%s", cp_settings)
        _type_to_snake = {"dimmer": "dimmer", "downlight": "down_light"}
        for _type in ("dimmer", "downlight"):
            val = getattr(cp_settings, _type_to_snake[_type], None) if cp_settings else None
            if val is not None:
                lights.append(ChargeampsLight(hass, f"{cp_info.name}_{cp_id}_{_type}", cp_id, _type))
                _LOGGER.info(
                    "Adding chargepoint %s light %s",
                    cp_id,
                    _type,
                )
    async_add_entities(lights, True)


class ChargeampsLight(LightEntity, ChargeampsEntity):
    """Chargeamps Light class."""

    def __init__(self, hass, name, charge_point_id, light_type):
        super().__init__(hass, name, charge_point_id)
        self._light_type = light_type
        self._attributes["light_type"] = light_type
        supported_color_modes = set()
        if light_type == "dimmer":
            supported_color_modes.add(ColorMode.BRIGHTNESS)
        else:
            supported_color_modes.add(ColorMode.ONOFF)
        supported_color_modes = filter_supported_color_modes(supported_color_modes)
        self._attr_supported_color_modes = supported_color_modes
        self._attr_color_mode = next(iter(self._attr_supported_color_modes))

    @property
    def unique_id(self):
        """Return a unique ID to use for this sensor."""
        return f"{DOMAIN}_{self.charge_point_id}_{self._light_type}"

    @property
    def is_on(self):
        settings = self.handler.get_chargepoint_settings(self.charge_point_id)
        if self._light_type == "downlight":
            status = settings.down_light
        elif self._light_type == "dimmer":
            status = settings.dimmer
        else:
            return None
        return status not in (False, None, "Off")

    async def async_turn_on(self, brightness=None):
        if brightness:
            if brightness < 128:
                brightness = "low"
            elif brightness < 192:
                brightness = "medium"
            else:
                brightness = "high"
        else:
            brightness = True if self._light_type == "downlight" else "high"
        await self.handler.async_set_light({"chargepoint": self.charge_point_id, self._light_type: brightness})

    async def async_turn_off(self):
        await self.handler.async_set_light(
            {
                "chargepoint": self.charge_point_id,
                self._light_type: False if self._light_type == "downlight" else "off",
            }
        )

    @property
    def brightness(self):
        """Return the brightness of this light between 0..255."""
        brightness = {"Off": 0, "Low": 85, "Medium": 170, "High": 255}
        return brightness.get(self.handler.get_chargepoint_settings(self.charge_point_id).dimmer)
