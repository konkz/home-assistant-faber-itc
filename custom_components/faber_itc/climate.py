import asyncio
import logging
from homeassistant.components.climate import (
    ClimateEntity,
    HVACMode,
    ClimateEntityFeature,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import (
    DOMAIN,
    INTENSITY_LEVELS,
    PRESET_NARROW,
    PRESET_WIDE,
    STATE_OFF,
    WIDTH_WIDE,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Faber ITC climate platform."""
    _LOGGER.debug("Setting up climate platform")
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
        self._attr_translation_key = "fireplace"

        # Optimistic UI states
        self._ovr_hvac_mode = None
        self._ovr_target_temp = None
        self._ovr_preset_mode = None

        self._attr_temperature_unit = None
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
        self._attr_preset_modes = [PRESET_NARROW, PRESET_WIDE]
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
            name="Faber Fireplace",
            manufacturer=data.get("manufacturer", "Faber"),
            model=data.get("model", "Faber ITC Fireplace"),
            serial_number=data.get("serial"),
        )

    @property
    def hvac_mode(self):
        if self._ovr_hvac_mode is not None:
            return self._ovr_hvac_mode
        if not self.coordinator.data:
            return HVACMode.OFF
        state = self.coordinator.data.get("state", STATE_OFF)
        _LOGGER.debug("Climate UI hvac_mode read state: %s", state)
        if state != STATE_OFF:
            return HVACMode.HEAT
        return HVACMode.OFF

    @property
    def target_temperature(self):
        if self._ovr_target_temp is not None:
            return self._ovr_target_temp
        if not self.coordinator.data:
            return 0.0
        intensity_val = self.coordinator.data.get("flame_height", 0)
        _LOGGER.debug("Climate UI target_temp read flame_height: %s", intensity_val)
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
        if self._ovr_preset_mode is not None:
            return self._ovr_preset_mode
        if not self.coordinator.data:
            return PRESET_NARROW
        # width >= WIDTH_WIDE (0x40/64) means dual burner / wide
        width = self.coordinator.data.get("flame_width", 0)
        _LOGGER.debug("Climate UI preset_mode read flame_width: %s", width)
        if width >= WIDTH_WIDE:
            return PRESET_WIDE
        return PRESET_NARROW

    @property
    def preset_icon(self):
        """Return the icon to use for the current preset mode."""
        if self.preset_mode == PRESET_WIDE:
            return "mdi:arrow-expand-horizontal"
        return "mdi:format-horizontal-align-center"

    @property
    def extra_state_attributes(self):
        """Return device specific state attributes."""
        if not self.coordinator.data:
            return {}
        
        intensity_val = self.coordinator.data.get("flame_height", 0)
        width = self.coordinator.data.get("flame_width", 0)
        
        level = 0
        for lvl, val in INTENSITY_LEVELS.items():
            if intensity_val == val:
                level = lvl
                break
        
        # burner_text = "2 Brenner (Breit)" if width >= WIDTH_WIDE else "1 Brenner (Schmal)"
        # if self.hvac_mode == HVACMode.OFF:
        #     burner_text = "Aus"
            
        # status_description = f"{burner_text}, Flammenhöhe Stufe {level}" if level > 0 else burner_text
        
        attrs = {
            "flame_width_raw": width,
            "flame_height_raw": intensity_val,
            "flame_level": level,
            "serial_number": self.coordinator.data.get("serial"),
            "model_name": self.coordinator.data.get("model"),
        }
        
        return attrs

    async def async_set_hvac_mode(self, hvac_mode):
        _LOGGER.info("Climate UI: Set HVAC Mode to %s (Optimistic)", hvac_mode)
        self._ovr_hvac_mode = hvac_mode
        self.async_write_ha_state()
        
        if hvac_mode == HVACMode.HEAT:
            await self._client.turn_on()
        else:
            await self._client.turn_off()
            
        await asyncio.sleep(2)
        self._ovr_hvac_mode = None
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs):
        level_idx = int(kwargs.get("temperature", 1))
        # Clamp value to min/max temp
        level_idx = max(int(self.min_temp), min(int(self.max_temp), level_idx))
        
        _LOGGER.info("Climate UI: Set Flame Level to %s (Optimistic)", level_idx)
        self._ovr_target_temp = float(level_idx)
        self.async_write_ha_state()

        protocol_value = INTENSITY_LEVELS.get(level_idx, 0x19)
        await self._client.set_flame_height(protocol_value)
        
        await asyncio.sleep(2)
        self._ovr_target_temp = None
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode):
        _LOGGER.info("Climate UI: Set Preset Mode to %s (Optimistic)", preset_mode)
        self._ovr_preset_mode = preset_mode
        self.async_write_ha_state()

        if preset_mode == PRESET_WIDE:
            await self._client.set_flame_width(True)
        else:
            await self._client.set_flame_width(False)
            
        await asyncio.sleep(2)
        self._ovr_preset_mode = None
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self):
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self):
        await self.async_set_hvac_mode(HVACMode.OFF)
