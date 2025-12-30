import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import (
    DOMAIN,
    CONF_SENDER_ID,
    INTENSITY_LEVELS,
    STATE_OFF,
    WIDTH_WIDE,
    WIDTH_NARROW,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Faber ITC switch platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    # Flame level switches (0-4)
    for level in range(5):
        entities.append(FaberFlameLevelSwitch(coordinator, entry, level))

    # Main power switch
    entities.append(FaberPowerSwitch(coordinator, entry))
        
    # Burner mode switches
    entities.append(FaberBurnerModeSwitch(coordinator, entry, True))  # Wide
    entities.append(FaberBurnerModeSwitch(coordinator, entry, False)) # Narrow
    
    async_add_entities(entities)

class FaberBaseSwitch(CoordinatorEntity, SwitchEntity):
    """Base class for Faber switches."""
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._client = coordinator.client

    @property
    def device_info(self) -> DeviceInfo:
        info = self.coordinator.client.device_info
        model_name = info.get("model")
        if not model_name or model_name == "Faber ITC Fireplace":
            model_name = self._entry.data.get("name") or "Faber ITC Fireplace"
            
        sender_id = self._entry.data.get(CONF_SENDER_ID)
        
        identifiers = {(DOMAIN, self._entry.entry_id)}
        connections = set()
        if sender_id:
            identifiers.add((DOMAIN, sender_id))
            formatted_mac = ":".join(sender_id[i:i+2] for i in range(0, len(sender_id), 2))
            connections.add((dr.CONNECTION_NETWORK_MAC, formatted_mac))

        return DeviceInfo(
            identifiers=identifiers,
            connections=connections,
            name=model_name,
            manufacturer=info.get("manufacturer", "Faber"),
            model=model_name,
            serial_number=info.get("serial"),
        )

class FaberPowerSwitch(FaberBaseSwitch):
    """Main power switch for the fireplace."""

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_power"
        self._attr_translation_key = "power"

    @property
    def icon(self):
        """Return dynamic icon based on state."""
        return "mdi:fireplace" if self.is_on else "mdi:fireplace-off"

    @property
    def is_on(self):
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get("state", STATE_OFF) != STATE_OFF

    async def async_turn_on(self, **kwargs):
        await self._client.turn_on()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self._client.turn_off()
        await self.coordinator.async_request_refresh()

class FaberFlameLevelSwitch(FaberBaseSwitch):
    """Switch representing a specific flame level."""

    def __init__(self, coordinator, entry, level):
        super().__init__(coordinator, entry)
        self._level = level
        self._attr_unique_id = f"{entry.entry_id}_flame_level_{level}"
        if level == 0:
            self._attr_translation_key = "flame_off"
        else:
            self._attr_translation_key = f"flame_level_{level}"
            self._attr_icon = f"mdi:tally-mark-{level}"

    @property
    def icon(self):
        """Return dynamic icon for level 0."""
        if self._level == 0:
            return "mdi:fire-off" if self.is_on else "mdi:fire"
        return self._attr_icon

    @property
    def is_on(self):
        if not self.coordinator.data:
            return False
        
        # If fireplace is off, only level 0 is "on"
        is_fireplace_on = self.coordinator.data.get("state", STATE_OFF) != STATE_OFF
        if not is_fireplace_on:
            return self._level == 0

        # Fireplace is on, check intensity
        intensity_val = self.coordinator.data.get("flame_height", 0)
        
        # Find closest level
        closest_lvl = 0
        min_diff = 999
        for lvl, val in INTENSITY_LEVELS.items():
            diff = abs(intensity_val - val)
            if diff < min_diff:
                min_diff = diff
                closest_lvl = lvl
        
        return self._level == closest_lvl

    async def async_turn_on(self, **kwargs):
        if self._level == 0:
            await self._client.turn_off()
        else:
            # Ensure fireplace is on
            if self.coordinator.data.get("state", STATE_OFF) == STATE_OFF:
                await self._client.turn_on()
            
            protocol_value = INTENSITY_LEVELS.get(self._level, 0x19)
            await self._client.set_flame_height(protocol_value)
            
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        # Turning off a level switch doesn't make much sense in mutual exclusive UI,
        # but we map it to turning off the fireplace or level 0 for consistency.
        if self._level != 0:
            await self._client.turn_off()
            await self.coordinator.async_request_refresh()

class FaberBurnerModeSwitch(FaberBaseSwitch):
    """Switch representing burner width (Narrow/Wide)."""

    def __init__(self, coordinator, entry, wide: bool):
        super().__init__(coordinator, entry)
        self._wide = wide
        self._attr_unique_id = f"{entry.entry_id}_mode_{'wide' if wide else 'narrow'}"
        self._attr_translation_key = f"mode_{'wide' if wide else 'narrow'}"
        self._attr_icon = "mdi:arrow-expand-horizontal" if wide else "mdi:format-horizontal-align-center"

    @property
    def is_on(self):
        if not self.coordinator.data:
            return False
        width = self.coordinator.data.get("flame_width", 0)
        is_wide_active = width >= WIDTH_WIDE
        return is_wide_active if self._wide else not is_wide_active

    async def async_turn_on(self, **kwargs):
        await self._client.set_flame_width(self._wide)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        # Toggle to the other mode
        await self._client.set_flame_width(not self._wide)
        await self.coordinator.async_request_refresh()
