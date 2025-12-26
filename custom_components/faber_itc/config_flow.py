import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_HOST

class FaberITCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # Hier könnte man eine kurze Test-Verbindung einbauen
            return self.async_create_entry(title=f"Faber Kamin ({user_input[CONF_HOST]})", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): str,
            }),
            errors=errors,
        )
