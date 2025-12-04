"""Constants for the WaterSmart integration."""

from datetime import timedelta
from enum import StrEnum, auto
from typing import Final

ATTRIBUTION: Final = "Data scraped from WaterSmart"
DOMAIN: Final = "watersmart"
MANUFACTURER: Final = "WaterSmart by VertexOne"
DEFAULT_SCAN_INTERVAL = timedelta(hours=1)
DEFAULT_IMAP_PORT = 993
DEFAULT_IMAP_FOLDER = "INBOX"
CONF_IMAP_HOST: Final = "imap_host"
CONF_IMAP_USERNAME: Final = "imap_username"
CONF_IMAP_PASSWORD: Final = "imap_password"
CONF_IMAP_PORT: Final = "imap_port"
CONF_IMAP_FOLDER: Final = "imap_folder"


class SensorKey(StrEnum):
    """Converter key enumeration class."""

    GALLONS_FOR_MOST_RECENT_HOUR = auto()
    GALLONS_FOR_MOST_RECENT_FULL_DAY_KEY = auto()
