"""Constants for Chargeamps."""

from datetime import timedelta

# Base component constants
DOMAIN = "chargeamps"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "1.12.1"
PLATFORMS = ["sensor", "switch", "light"]
ISSUE_URL = "https://github.com/hass-chargeamps/hass-chargeamps/issues"
CONFIGURATION_URL = "https://my.charge.space"
MANUFACTURER = "Charge Amps AB"

# Icons
DEFAULT_ICON = "mdi:car-electric"
ICON_MAP = {
    "Charger": "mdi:ev-plug-type2",
    "Schuko": "mdi:power-socket-de",
}

# Configuration
CONF_CHARGEPOINTS = "chargepoints"
CONF_READONLY = "readonly"

# Defaults
DEFAULT_NAME = DOMAIN

# Possible dimmer values
DIMMER_VALUES = ["off", "low", "medium", "high"]

# Overall scan interval
SCAN_INTERVAL = timedelta(seconds=10)

# Chargepoint online status
CHARGEPOINT_ONLINE = "Online"
