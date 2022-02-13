"""Constants for the OpenRGB integration."""

from datetime import timedelta

DOMAIN = "openrgb"
CONFIG_VERSION = 2

ORGB_DATA = "openrgb_data"
ORGB_TRACKER = "openrgb_tracker"
ORGB_DISCOVERY_NEW = "openrgb_discovery_new_{}"

SERVICE_FORCE_UPDATE = "force_update"
SERVICE_PULL_DEVICES = "pull_devices"

ENTRY_IS_SETUP = "openrgb_entry_is_setup"

SIGNAL_DELETE_ENTITY = "openrgb_delete"
SIGNAL_UPDATE_ENTITY = "openrgb_update"

TRACK_INTERVAL = timedelta(seconds=30)

CONF_ADD_LEDS = "add_leds"

DEFAULT_PORT = 6742
DEFAULT_CLIENT_ID = "Home Assistant"
DEFAULT_ADD_LEDS = False

CONN_TIMEOUT = 5.0
