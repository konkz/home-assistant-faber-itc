import logging
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE
from .const import DOMAIN, INTENSITY_LEVELS
from .entity import FaberEntity

_LOGGER = logging.getLogger(__name__)

# The controller knows 5 flame levels; their protocol values are percentages
FLAME_STEP = INTENSITY_LEVELS[1]

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Faber ITC number platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FaberFlameHeightNumber(coordinator, entry)])

def nearest_flame_value(value: float) -> int:
    """Snap a percentage to the closest flame level the controller accepts."""
    return min(INTENSITY_LEVELS.values(), key=lambda level: abs(level - value))

class FaberFlameHeightNumber(FaberEntity, NumberEntity):
    """Flame height in percent: 0 % = off, 25-100 % = level 1-4.

    Setting 25-100 % ignites a fireplace that is off, 0 % turns it off.
    A pilot flame (e.g. set by the thermostat or the remote) shows as 0 %.
    """

    _attr_icon = "mdi:fire"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_max_value = INTENSITY_LEVELS[4]
    _attr_native_step = FLAME_STEP
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_flame_height"
        self._attr_translation_key = "flame_height"

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        if not self.fireplace_burning:
            return 0
        if self.coordinator.pending_flame is not None:
            return self.coordinator.pending_flame
        return self.coordinator.data.get("flame_height")

    @property
    def extra_state_attributes(self):
        """`pending`: waiting for the fireplace to take over a new height."""
        coordinator = self.coordinator
        return {
            "pending": coordinator.pending_flame is not None
            or coordinator.is_pending("flame_height")
        }

    async def async_set_native_value(self, value: float) -> None:
        await self._set_flame(nearest_flame_value(value))
