from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.http import StaticPathConfig
from .const import DOMAIN, CONF_HOST
from .client import FaberITCClient
from .coordinator import FaberITCUpdateCoordinator

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Faber ITC from a config entry."""
    # Registriert den Ordner 'branding' unter dem URL-Pfad '/faber_itc_static'
    hass.http.register_static_path(
        "/faber_itc_static",
        hass.config.path("custom_components/faber_itc/branding"),
        cache_headers=True,
    )
    
    host = entry.data[CONF_HOST]
    # Default port 5555 according to instructions
    client = FaberITCClient(host, 5555)
    
    coordinator = FaberITCUpdateCoordinator(hass, client)
    
    # First refresh
    await coordinator.async_config_entry_first_refresh()
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    await hass.config_entries.async_forward_entry_setups(entry, ["climate"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["climate"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
