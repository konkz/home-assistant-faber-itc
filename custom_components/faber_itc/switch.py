import logging
from homeassistant.components.switch import SwitchEntity
from .const import (
    DOMAIN,
    INTENSITY_LEVELS,
    STATE_IGNITING,
    STATE_OFF,
    STATE_ON,
    STATE_SHUTTING_DOWN,
    WIDTH_WIDE,
    WIDTH_NARROW,
)
from .entity import FaberEntity

_LOGGER = logging.getLogger(__name__)

STATUS_NAMES = {
    STATE_OFF: "off",
    STATE_ON: "on",
    STATE_IGNITING: "igniting",
    STATE_SHUTTING_DOWN: "shutting_down",
}

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

class FaberBaseSwitch(FaberEntity, SwitchEntity):
    """Base class for Faber switches."""

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
        return self.fireplace_burning

    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes."""
        state = (self.coordinator.data or {}).get("state", STATE_OFF)
        return {
            "hint": "hold_to_toggle",
            "status": STATUS_NAMES.get(state, "on"),
        }

    async def async_turn_on(self, **kwargs):
        await self._set_power(True)

    async def async_turn_off(self, **kwargs):
        await self._set_power(False)

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
            return "mdi:fire" if self.is_on else "mdi:fire-off"
        return self._attr_icon

    @property
    def is_on(self):
        if not self.coordinator.data:
            return False

        is_fireplace_on = self.fireplace_burning

        # Pilot flame (level 0) is "on" whenever the fireplace is on
        if self._level == 0:
            return is_fireplace_on

        # For other levels, check if fireplace is on and matches intensity
        if not is_fireplace_on:
            return False

        intensity_val = self.coordinator.data.get("flame_height", 0)
        closest_lvl = 0
        min_diff = 999
        for lvl, val in INTENSITY_LEVELS.items():
            diff = abs(intensity_val - val)
            if diff < min_diff:
                min_diff = diff
                closest_lvl = lvl

        return self._level == closest_lvl

    async def async_turn_on(self, **kwargs):
        # Ignites the fireplace if needed; level 0 is the pilot flame here
        await self._set_flame(INTENSITY_LEVELS[self._level], zero_is_off=False)

    async def async_turn_off(self, **kwargs):
        # Off is off: turning off the active level turns the fireplace off
        # (it used to fall back to the pilot flame, which kept burning)
        if self.is_on:
            self.coordinator.async_manual_flame_change()
            await self._set_power(False)

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
        protocol_value = WIDTH_WIDE if self._wide else WIDTH_NARROW
        await self._send(
            {"flame_width": protocol_value},
            lambda: self._client.set_flame_width(self._wide),
        )

    async def async_turn_off(self, **kwargs):
        # Turning off a burner mode just re-sends the command for the current mode
        await self.async_turn_on()
