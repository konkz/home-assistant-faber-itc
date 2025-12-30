import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_HOST, CONF_NAME, CONF_SENDER_ID, DEFAULT_PORT
from .client import FaberITCClient
from .discovery import async_discover_devices

class FaberITCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._discovered_devices = {} # ip -> {name, sender_id}
        self._discovered_host = None
        self._discovered_name = None
        self._discovered_sender_id = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step - start discovery immediately."""
        return await self.async_step_discovery()

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
        current_entries = self._async_current_entries()
        current_hosts = {entry.data.get(CONF_HOST) for entry in current_entries}
        current_ids = {entry.unique_id for entry in current_entries if entry.unique_id}

        def is_new_device(ip, sender_id=None):
            if sender_id and sender_id in current_ids:
                return False
            return ip not in current_hosts

        self._discovered_devices = await async_discover_devices(
            timeout=35.0, 
            is_new_device=is_new_device
        )
        
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
        if user_input is not None and "selected_device" in user_input:
            if user_input["selected_device"] == "manual":
                return await self.async_step_setup()
            
            host = user_input["selected_device"]
            device_info = self._discovered_devices.get(host, {})
            name = device_info.get("name")
            sender_id = device_info.get("sender_id")
            
            self._discovered_host = host
            self._discovered_name = name
            self._discovered_sender_id = sender_id
            
            # Directly try to setup with the discovered host, skipping the manual setup form
            return await self.async_step_setup({
                CONF_HOST: host,
                CONF_NAME: name,
                CONF_SENDER_ID: sender_id,
            })

        if not self._discovered_devices:
            return await self.async_step_setup()

        device_options = {
            ip: f"ITC Controller ({ip})" for ip in self._discovered_devices
        }
        device_options["manual"] = "Enter IP address"

        return self.async_show_form(
            step_id="discovery_result",
            data_schema=vol.Schema({
                vol.Required("selected_device", default=next(iter(device_options))): vol.In(device_options),
            })
        )

    async def async_step_setup(self, user_input=None):
        errors = {}
        
        # If we have a discovered sender_id, set unique_id early
        if self._discovered_sender_id:
            await self.async_set_unique_id(self._discovered_sender_id)
            self._abort_if_unique_id_configured()

        if user_input is not None and CONF_HOST in user_input:
            host = user_input[CONF_HOST]
            # Priority: 1. Name from user_input, 2. Discovered name
            name = user_input.get(CONF_NAME) or self._discovered_name
            sender_id = user_input.get(CONF_SENDER_ID) or self._discovered_sender_id
            
            if sender_id:
                await self.async_set_unique_id(sender_id)
                self._abort_if_unique_id_configured()

            try:
                client = FaberITCClient(host, DEFAULT_PORT)
                if await client.connect():
                    # Request more info to be sure about the model
                    await client.request_info()
                    
                    # Fallback to model name if still no name
                    if not name:
                        name = client.device_info.get("model", "Faber Fireplace")
                    
                    await client.disconnect()
                    
                    return self.async_create_entry(
                        title=f"ITC Controller ({host})", 
                        data={
                            CONF_HOST: host,
                            CONF_NAME: name,
                            CONF_SENDER_ID: sender_id,
                        }
                    )
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"

        # Pre-fill with discovered data or previous user input
        default_host = self._discovered_host or ""
        
        if user_input:
            default_host = user_input.get(CONF_HOST, default_host)

        return self.async_show_form(
            step_id="setup",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=default_host): str,
            }),
            errors=errors,
        )
