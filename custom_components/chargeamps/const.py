"""Constants for Chargeamps."""

from datetime import timedelta

# Base component constants
DOMAIN = "chargeamps"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "1.12.1"
PLATFORMS = ["sensor", "switch", "light", "button", "lock", "number", "binary_sensor"]
ISSUE_URL = "https://github.com/kirei/hass-chargeamps/issues"
CONFIGURATION_URL = "https://my.charge.space"
MANUFACTURER = "Charge Amps AB"

# Status Mappings from API v4
STATUS_OCPP_MAP = {
    "0": "Available",
    "1": "Preparing",
    "2": "Charging",
    "3": "SuspendedEVSE",
    "4": "SuspendedEV",
    "5": "Finishing",
    "6": "Reserved",
    "7": "Unavailable",
    "8": "Faulted",
    "9": "Unknown",
}

STATUS_CAPI_MAP = {
    "0": "Available",
    "1": "Charging",
    "2": "Connected",
    "3": "Error",
    "4": "Unknown",
}

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
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)
MIN_SCAN_INTERVAL = timedelta(seconds=10)

# Possible dimmer values
DIMMER_VALUES = ["off", "low", "medium", "high"]

# Overall scan interval
SCAN_INTERVAL = timedelta(seconds=10)

# Chargepoint online status
CHARGEPOINT_ONLINE = "Online"
