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
    _LOGGER.warning("Setting up Faber ITC integration entry for host: %s", entry.data.get(CONF_HOST))
    
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
    
    # Non-blocking first refresh: We try once, but don't fail setup if it takes too long.
    # The integration will start, entities will be 'unavailable' until first data arrives.
    hass.async_create_task(coordinator.async_refresh())
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    await hass.config_entries.async_forward_entry_setups(entry, ["climate"])
    _LOGGER.warning("Faber ITC integration setup complete (refresh pending in background)")
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["climate"])
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.disconnect()
    return unload_ok
