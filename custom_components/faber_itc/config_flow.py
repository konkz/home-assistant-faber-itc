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
        """Handle the initial step."""
        if user_input is not None:
            if user_input.get("run_discovery"):
                return await self.async_step_discovery()
            
            if user_input.get(CONF_HOST):
                return await self.async_step_setup(user_input)

        # In Home Assistant, we can't truly "gray out" based on a checkbox in a single step 
        # without custom cards, but we can use a schema that suggests the alternative.
        # To meet the requirement "only one of both", we keep the toggle but make 
        # the fields optional and validate that if run_discovery is False, host is provided.
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Optional("run_discovery", default=True): bool,
                vol.Optional(CONF_HOST): str,
                vol.Optional(CONF_NAME, default="Faber ITC"): str,
            })
        )

    async def async_step_discovery(self, user_input=None):
        """Step to discover devices or proceed to manual entry."""
        if user_input is not None:
            # This is called when the progress task is done
            return self.async_show_progress_done(next_step_id="discovery_result")

        # Perform discovery (35s timeout because devices broadcast every 30s)
        return self.async_show_progress(
            step_id="discovery",
            progress_action="discovery_action",
            progress_task=self.hass.async_create_task(self._async_discovery_task()),
        )

    async def _async_discovery_task(self):
        """Perform the actual discovery background task."""
        self._discovered_devices = await async_discover_devices(timeout=35.0)
        self.hass.async_create_task(
            self.hass.config_entries.flow.async_configure(
                flow_id=self.flow_id, user_input={"done": True}
            )
        )

    async def async_step_discovery_action(self, user_input=None):
        """Not used but required by progress_action in older versions/specific flows."""
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
