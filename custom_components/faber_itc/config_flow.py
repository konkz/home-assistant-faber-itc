import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_HOST, DEFAULT_PORT
from .client import FaberITCClient

class FaberITCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                client = FaberITCClient(user_input[CONF_HOST], DEFAULT_PORT)
                if await client.connect():
                    await client.disconnect()
                    return self.async_create_entry(
                        title=f"Faber ITC Controller ({user_input[CONF_HOST]})", data=user_input
                    )
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"


        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): str,
            }),
            errors=errors,
        )
