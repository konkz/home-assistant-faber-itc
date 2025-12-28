import logging
from homeassistant.components.climate import (
    ClimateEntity,
    HVACMode,
    ClimateEntityFeature,
    PRESET_NONE,
    PRESET_BOOST,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import (
    DOMAIN,
    INTENSITY_LEVELS,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Faber ITC climate platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FaberFireplace(coordinator, entry)])

class FaberFireplace(CoordinatorEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._client = coordinator.client
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_fireplace_entity"

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
        self._attr_preset_modes = [PRESET_NONE, PRESET_BOOST]
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.PRESET_MODE
        )

        self._attr_min_temp = 0
        self._attr_max_temp = 4
        self._attr_target_temperature_step = 1
        self._attr_icon = "mdi:fireplace"
        self._attr_entity_picture = "/faber_itc_static/icon.png"

    @property
    def device_info(self) -> DeviceInfo:
        """Return dynamic device info from client."""
        data = self.coordinator.data or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Faber Kamin",
            manufacturer=data.get("manufacturer", "Faber"),
            model=data.get("model", "Faber ITC Fireplace"),
            hw_version=data.get("serial"),
        )

    @property
    def hvac_mode(self):
        if not self.coordinator.data:
            return HVACMode.OFF
        state = self.coordinator.data.get("state", 0)
        # 0x01 is often "on/ignited" in many ITC versions, 0x00 is off
        if state > 0:
            return HVACMode.HEAT
        return HVACMode.OFF

    @property
    def target_temperature(self):
        if not self.coordinator.data:
            return 0.0
        intensity_val = self.coordinator.data.get("flame_height", 0)
        # Best match for intensity/flame height
        closest_lvl = 0
        min_diff = 999
        for lvl, val in INTENSITY_LEVELS.items():
            diff = abs(intensity_val - val)
            if diff < min_diff:
                min_diff = diff
                closest_lvl = lvl
        return float(closest_lvl)

    @property
    def preset_mode(self):
        if not self.coordinator.data:
            return PRESET_NONE
        # flame_width 1 usually means dual burner / wide
        width = self.coordinator.data.get("flame_width", 0)
        if width > 0:
            return PRESET_BOOST
        return PRESET_NONE

    @property
    def extra_state_attributes(self):
        if not self.coordinator.data:
            return {}
            
        intensity_val = self.coordinator.data.get("flame_height", 0)
        width = self.coordinator.data.get("flame_width", 0)
        
        level = 0
        for lvl, val in INTENSITY_LEVELS.items():
            if intensity_val == val:
                level = lvl
                break
        
        burner_text = "2 Brenner (Breit)" if width > 0 else "1 Brenner (Schmal)"
        if self.hvac_mode == HVACMode.OFF:
            burner_text = "Aus"
            
        status_description = f"{burner_text}, Flammenhöhe Stufe {level}" if level > 0 else burner_text
        
        attrs = {
            "status_description": status_description,
            "flame_width_raw": width,
            "flame_height_raw": intensity_val,
            "serial_number": self.coordinator.data.get("serial"),
            "model_name": self.coordinator.data.get("model"),
        }
        
        # Merge mined raw sensors into attributes
        raw_sensors = self.coordinator.data.get("raw_sensors", {})
        attrs.update(raw_sensors)
        
        return attrs

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode == HVACMode.HEAT:
            await self._client.turn_on()
        else:
            await self._client.turn_off()
        # Non-blocking refresh to avoid UI lag and race conditions
        self.hass.async_create_task(self.coordinator.async_request_refresh())

    async def async_set_temperature(self, **kwargs):
        level_idx = int(kwargs.get("temperature", 1))
        # Map 0-4 to protocol values (0x00, 0x19, etc.)
        protocol_value = INTENSITY_LEVELS.get(level_idx, 0x19)
        
        await self._client.set_flame_height(protocol_value)
        self.hass.async_create_task(self.coordinator.async_request_refresh())

    async def async_set_preset_mode(self, preset_mode):
        if preset_mode == PRESET_BOOST:
            await self._client.set_flame_width(True)
        else:
            await self._client.set_flame_width(False)
        self.hass.async_create_task(self.coordinator.async_request_refresh())

    async def async_turn_on(self):
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self):
        await self.async_set_hvac_mode(HVACMode.OFF)
