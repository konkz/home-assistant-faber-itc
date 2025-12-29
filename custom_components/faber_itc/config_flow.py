import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_HOST, CONF_NAME, DEFAULT_PORT
from .client import FaberITCClient
from .discovery import async_discover_devices

class FaberITCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._discovered_devices = {}

    async def async_step_user(self, user_input=None):
        if user_input is None:
            return await self.async_step_discovery()
        return await self.async_step_setup(user_input)

    async def async_step_discovery(self, user_input=None):
        """Step to discover devices or proceed to manual entry."""
        if user_input is not None:
            if user_input.get("manual_entry") or user_input.get("selected_device") == "manual":
                return await self.async_step_setup()
            
            # User selected a discovered device
            host = user_input["selected_device"]
            name = self._discovered_devices.get(host, "Faber ITC")
            return await self.async_step_setup({CONF_HOST: host, CONF_NAME: name})

        # Perform discovery (35s timeout because devices broadcast every 30s)
        # async_show_progress will show a loading spinner/hourglass in the UI
        return self.async_show_progress(
            step_id="discovery",
            progress_action="discovery_action",
        )

    async def async_step_discovery_action(self, user_input=None):
        """Perform the actual discovery background task."""
        self._discovered_devices = await async_discover_devices(timeout=35.0)
        return self.async_show_progress_done(next_step_id="discovery_result")

    async def async_step_discovery_result(self, user_input=None):
        """Show results of discovery."""
        if not self._discovered_devices:
            return await self.async_step_setup()

        device_options = {
            ip: f"{name} ({ip})" for ip, name in self._discovered_devices.items()
        }
        device_options["manual"] = "Manuelle Eingabe"

        return self.async_show_form(
            step_id="discovery_result",
            data_schema=vol.Schema({
                vol.Required("selected_device", default=next(iter(device_options))): vol.In(device_options),
            })
        )

    async def async_step_setup(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                client = FaberITCClient(user_input[CONF_HOST], DEFAULT_PORT)
                if await client.connect():
                    # If we have no name yet, try to get it from the client after connection
                    if not user_input.get(CONF_NAME):
                        user_input[CONF_NAME] = client.device_info.get("model", "Faber ITC")
                    
                    await client.disconnect()
                    return self.async_create_entry(
                        title=user_input.get(CONF_NAME, f"Faber ITC ({user_input[CONF_HOST]})"), 
                        data=user_input
                    )
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"

        default_host = ""
        default_name = "Faber ITC"
        if user_input:
            default_host = user_input.get(CONF_HOST, "")
            default_name = user_input.get(CONF_NAME, "Faber ITC")

        return self.async_show_form(
            step_id="setup",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=default_host): str,
                vol.Required(CONF_NAME, default=default_name): str,
            }),
            errors=errors,
        )
