import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.http import StaticPathConfig
from .const import DOMAIN, CONF_HOST, DEFAULT_PORT
from .client import FaberITCClient
from .coordinator import FaberITCUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Faber ITC from a config entry."""
    _LOGGER.warning("FABER ITC: async_setup_entry starting for host: %s", entry.data.get(CONF_HOST))
    
    # Registriert den Ordner 'branding' unter dem URL-Pfad '/faber_itc_static'
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                "/faber_itc_static",
                hass.config.path("custom_components/faber_itc/branding"),
                True,
            )
        ]
    )
    
    host = entry.data[CONF_HOST]
    client = FaberITCClient(host, DEFAULT_PORT)
    
    coordinator = FaberITCUpdateCoordinator(hass, client)
    
    # Initial load.
    await coordinator.async_config_entry_first_refresh()
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    _LOGGER.warning("FABER ITC: Forwarding setup to platform: climate")
    await hass.config_entries.async_forward_entry_setups(entry, ["climate"])
    _LOGGER.warning("FABER ITC: async_setup_entry finished successfully")
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["climate"])
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.disconnect()
    return unload_ok
