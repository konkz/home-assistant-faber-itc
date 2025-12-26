import logging
from homeassistant.components.climate import ClimateEntity, HVACMode, ClimateEntityFeature
from .const import DOMAIN, STATUS_ON, INTENSITY_LEVELS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    client = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FaberFireplace(client)], update_before_add=True)

class FaberFireplace(ClimateEntity):
    _attr_has_entity_name = True
    _attr_name = None # Übernimmt Name vom Gerät/Eintrag

    def __init__(self, client):
        self._client = client
        self._attr_unique_id = f"faber_fireplace_{id(client)}"
        self._attr_entity_picture = "/local/faber_icon.png"
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE | 
            ClimateEntityFeature.TURN_ON | 
            ClimateEntityFeature.TURN_OFF
        )
        self._attr_min_temp = 0
        self._attr_max_temp = 4
        self._attr_target_temperature = 1
        self._attr_target_temperature_step = 1
        self._client.register_callback(self._handle_status)

    def _handle_status(self, words):
        if len(words) < 6: return
        self._attr_hvac_mode = HVACMode.HEAT if words[3] == STATUS_ON else HVACMode.OFF
        for lvl, hex_val in INTENSITY_LEVELS.items():
            if words[5] == hex_val:
                self._attr_target_temperature = lvl
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode):
        on = (hvac_mode == HVACMode.HEAT)
        await self._client.set_state(power_on=on, level=int(self._attr_target_temperature))

    async def async_set_temperature(self, **kwargs):
        temp = kwargs.get("temperature")
        if temp is not None:
            self._attr_target_temperature = temp
            await self._client.set_state(power_on=(self._attr_hvac_mode == HVACMode.HEAT), level=int(temp))

    async def async_turn_on(self):
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self):
        await self.async_set_hvac_mode(HVACMode.OFF)
