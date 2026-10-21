"""Constants for the AC MITM integration."""

DOMAIN = "ac_mitm"

CONF_HOST = "host"
CONF_PORT = "port"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8090

# How often the climate entity polls the MITM control API.
SCAN_INTERVAL = 10

# Payload keys used by the Panasonic Mirae MQTT protocol.
KEY_POWER = "ps"
KEY_MODE = "acmd"
KEY_TARGET_TEMP = "actmp"
KEY_ROOM_TEMP = "rmtmp"
KEY_FAN = "acfs"
KEY_SWING_VERTICAL = "acvs"
KEY_SWING_HORIZONTAL = "achs"
KEY_ONLINE = "onlineStatus"
KEY_NANOE = "acng"
KEY_POWERFUL = "acpm"
KEY_ECONOMY = "acem"
KEY_COIL_CLEANING = "acec"
KEY_DISPLAY = "acdc"
KEY_CAPACITY = "cnv"
KEY_FILTER_DUST = "filterDustLevel"
KEY_FILTER_CLEANING = "filterCleaningRequired"
