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
    STATUS_ON,
    STATUS_OFF,
    STATUS_DUAL_BURNER,
    BURNER_ON_MASK,
    BURNER_DUAL_MASK,
    BURNER_OFF_MASK,
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

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Faber Kamin",
            manufacturer="Faber",
            model="Aspect Premium RD L",
        )

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
        self._attr_preset_modes = [PRESET_NONE, PRESET_BOOST]
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.PRESET_MODE
        )

        # Intensity steps 0-4
        self._attr_min_temp = 0
        self._attr_max_temp = 4
        self._attr_target_temperature_step = 1
        self._attr_icon = "mdi:fireplace"
        self._attr_entity_picture = "/faber_itc_static/icon.png"

    @property
    def hvac_mode(self):
        status = self.coordinator.data.get("status_main")
        if status in [STATUS_ON, STATUS_DUAL_BURNER]:
            return HVACMode.HEAT
        return HVACMode.OFF

    @property
    def target_temperature(self):
        intensity_val = self.coordinator.data.get("intensity", 0)
        for lvl, val in INTENSITY_LEVELS.items():
            if intensity_val == val:
                return float(lvl)
        return 0.0

    @property
    def preset_mode(self):
        status = self.coordinator.data.get("status_main")
        if status == STATUS_DUAL_BURNER:
            return PRESET_BOOST
        return PRESET_NONE

    @property
    def extra_state_attributes(self):
        intensity_val = self.coordinator.data.get("intensity", 0)
        burner_mask = self.coordinator.data.get("burner_mask")
        
        level = 0
        for lvl, val in INTENSITY_LEVELS.items():
            if intensity_val == val:
                level = lvl
                break
        
        burner_text = "Aus"
        if burner_mask == BURNER_ON_MASK:
            burner_text = "1 Brenner"
        elif burner_mask == BURNER_DUAL_MASK:
            burner_text = "2 Brenner"
            
        status_description = f"{burner_text}, Stufe {level}" if level > 0 else burner_text
        
        return {
            "status_description": status_description,
            "burner_mask": hex(burner_mask) if burner_mask is not None else None,
            "intensity_raw": intensity_val,
        }

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode == HVACMode.HEAT:
            # Default to 1 burner, level 1 if turning on
            await self._client.send_frame(STATUS_ON, 1, BURNER_ON_MASK)
        else:
            await self._client.send_frame(STATUS_OFF, 0, BURNER_OFF_MASK)
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs):
        temp = int(kwargs.get("temperature", 1))
        # Determine current burner/status
        current_mask = self.coordinator.data.get("burner_mask", BURNER_ON_MASK)
        current_status = self.coordinator.data.get("status_main", STATUS_ON)
        
        await self._client.send_frame(current_status, temp, current_mask)
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode):
        intensity = int(self.target_temperature)
        if intensity == 0: intensity = 1 # Minimum when turning on preset
        
        if preset_mode == PRESET_BOOST:
            await self._client.send_frame(STATUS_DUAL_BURNER, intensity, BURNER_DUAL_MASK)
        else:
            await self._client.send_frame(STATUS_ON, intensity, BURNER_ON_MASK)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self):
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self):
        await self.async_set_hvac_mode(HVACMode.OFF)
