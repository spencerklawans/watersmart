"""The WaterSmart integration."""

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .client import WaterSmartClient
from .const import (
    CONF_IMAP_FOLDER,
    CONF_IMAP_HOST,
    CONF_IMAP_PASSWORD,
    CONF_IMAP_PORT,
    CONF_IMAP_USERNAME,
    DEFAULT_IMAP_FOLDER,
    DEFAULT_IMAP_PORT,
    DOMAIN,
)
from .coordinator import WaterSmartUpdateCoordinator
from .services import async_setup_services
from .types import WaterSmartConfigEntry, WaterSmartData

PLATFORMS: list[Platform] = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(  # noqa: RUF029
    hass: HomeAssistant,
    config: ConfigType,  # noqa: ARG001
) -> bool:
    """Set up WaterSmart services.

    Returns:
        If the setup was successful.
    """

    async_setup_services(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: WaterSmartConfigEntry) -> bool:
    """Set up WaterSmart from a config entry.

    Returns:
        If the setup was successful.
    """

    hostname: str = entry.data[CONF_HOST]
    username: str = entry.data[CONF_USERNAME]
    password: str = entry.data[CONF_PASSWORD]
    imap_host: str | None = entry.data.get(CONF_IMAP_HOST)
    imap_username: str | None = entry.data.get(CONF_IMAP_USERNAME)
    imap_password: str | None = entry.data.get(CONF_IMAP_PASSWORD)
    imap_port: int = entry.data.get(CONF_IMAP_PORT, DEFAULT_IMAP_PORT)
    imap_folder: str = entry.data.get(CONF_IMAP_FOLDER, DEFAULT_IMAP_FOLDER)

    session = async_get_clientsession(hass)
    watersmart = WaterSmartClient(
        hostname,
        username,
        password,
        session=session,
        imap_config=
        {
            "host": imap_host,
            "username": imap_username,
            "password": imap_password,
            "port": imap_port,
            "folder": imap_folder,
        }
        if imap_host and imap_username and imap_password
        else None,
    )

    coordinator = WaterSmartUpdateCoordinator(
        hass,
        watersmart,
        hostname,
        username,
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = WaterSmartData(
        coordinator=coordinator,
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = entry.runtime_data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: WaterSmartConfigEntry) -> bool:
    """Unload a config entry.

    Returns:
        If the unload was successful.
    """
    return bool(await hass.config_entries.async_unload_platforms(entry, PLATFORMS))
