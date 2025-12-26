from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.http import StaticPathConfig
from homeassistant.exceptions import ConfigEntryNotReady
from .const import DOMAIN, CONF_HOST, DEFAULT_PORT
from .client import FaberITCClient
from .coordinator import FaberITCUpdateCoordinator

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Faber ITC from a config entry."""
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
    # Use DEFAULT_PORT from const.py
    client = FaberITCClient(host, DEFAULT_PORT)
    
    coordinator = FaberITCUpdateCoordinator(hass, client)
    
    # First refresh with error handling to prevent bootstrap hangs
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Timeout while connecting to fireplace at {host}") from err
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    await hass.config_entries.async_forward_entry_setups(entry, ["climate"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["climate"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
