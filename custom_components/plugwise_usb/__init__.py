"""Support for Plugwise devices connected to a Plugwise USB-stick."""
import logging
from typing import TypedDict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.storage import STORAGE_DIR

from .const import (
    CONF_USB_PATH,
    DOMAIN,
    NODES,
    PLUGWISE_USB_PLATFORMS,
    STICK,
)
from .coordinator import PlugwiseUSBDataUpdateCoordinator
from .plugwise_usb import Stick
from .plugwise_usb.exceptions import StickError

_LOGGER = logging.getLogger(__name__)


class NodeConfigEntry(TypedDict):
    """Plugwise node config entry"""

    mac: str
    coordinator: PlugwiseUSBDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Establish connection with plugwise USB-stick."""
    hass.data.setdefault(DOMAIN, {})

    api_stick = Stick(config_entry.data[CONF_USB_PATH])
    api_stick.cache_folder = hass.config.path(
        STORAGE_DIR, f"plugwisecache-{config_entry.entry_id}"
    )
    hass.data[DOMAIN][config_entry.entry_id] = {STICK: api_stick}

    _LOGGER.debug("Connect to Plugwise USB-Stick")
    try:
        await api_stick.connect()
    except StickError:
        raise ConfigEntryNotReady(
            f"Failed to open connection to Plugwise USB stick at {config_entry.data[CONF_USB_PATH]}"
        ) from StickError

    _LOGGER.debug("Initialize Plugwise USB-Stick")
    try:
        await api_stick.initialize()
    except StickError:
        await api_stick.isconnect()
        raise ConfigEntryNotReady(
            "Failed to initialize connection to Plugwise USB-Stick"
        ) from StickError

    _LOGGER.debug("Discover registered Plugwise nodes")
    try:
        await api_stick.setup(discover=True, load=False)
    except StickError:
        await api_stick.disconnect()
        raise ConfigEntryNotReady(
            "Failed to discover Plugwise USB nodes"
        ) from StickError

    hass.data[DOMAIN][config_entry.entry_id][NODES]: NodeConfigEntry = {}

    # Setup a 'Data Update Coordinator' for each plugwise node
    try:
        for mac, node in api_stick.nodes.items():
            _LOGGER.info("Try to load Plugwise USB-Stick node %s", mac)
            if node.available:
                await node.load()
                _LOGGER.info("Try to load Plugwise USB-Stick node %s", mac)
                coordinator = PlugwiseUSBDataUpdateCoordinator(hass, node)
                await coordinator.async_config_entry_first_refresh()
                hass.data[DOMAIN][config_entry.entry_id][NODES][mac] = coordinator
    except Exception as e:
        logging.exception(e)
    await hass.config_entries.async_forward_entry_setups(
        config_entry, PLUGWISE_USB_PLATFORMS
    )
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Unload the Plugwise USB stick connection."""
    unload = await hass.config_entries.async_unload_platforms(
        config_entry, PLUGWISE_USB_PLATFORMS
    )
    api_stick = hass.data[DOMAIN][config_entry.entry_id][STICK]
    await api_stick.disconnect()
    return unload
