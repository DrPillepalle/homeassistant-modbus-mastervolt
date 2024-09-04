import logging
from homeassistant.helpers.discovery import load_platform

DOMAIN = "modbus_mastervolt"

_LOGGER = logging.getLogger(__name__)

def setup(hass, config):
    """Set up the Custom Modbus integration."""
    _LOGGER.info("Setting up Custom Modbus Mastervolt component")

    load_platform(hass, 'sensor', DOMAIN, {}, config)

    return True
