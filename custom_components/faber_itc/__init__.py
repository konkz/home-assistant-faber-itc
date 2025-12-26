from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN, DEFAULT_PORT, CONF_HOST
from .client import FaberClient

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Faber ITC from a config entry."""
    # Registriert den Ordner 'branding' unter dem URL-Pfad '/faber_itc_static'
    hass.http.register_static_path(
        "/faber_itc_static",
        hass.config.path("custom_components/faber_itc/branding"),
        cache_headers=True
    )
    
    host = entry.data[CONF_HOST]
    client = FaberClient(host, DEFAULT_PORT)
    
    # Verbindung herstellen
    if not await client.connect():
        return False
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = client
    
    await hass.config_entries.async_forward_entry_setups(entry, ["climate"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["climate"])
    if unload_ok:
        client = hass.data[DOMAIN].pop(entry.entry_id)
        # Hier optional client.disconnect() aufrufen
    return unload_ok
