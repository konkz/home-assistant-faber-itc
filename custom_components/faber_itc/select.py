import logging
from homeassistant.components.select import SelectEntity
from .const import DOMAIN, PRESET_NARROW, PRESET_WIDE, WIDTH_NARROW, WIDTH_WIDE
from .entity import FaberEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Faber ITC select platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FaberFlameWidthSelect(coordinator, entry)])

class FaberFlameWidthSelect(FaberEntity, SelectEntity):
    """Burner width: narrow or wide."""

    _attr_icon = "mdi:arrow-expand-horizontal"
    _attr_options = [PRESET_NARROW, PRESET_WIDE]

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_flame_width"
        self._attr_translation_key = "flame_width"

    @property
    def current_option(self):
        if not self.coordinator.data:
            return None
        width = self.coordinator.data.get("flame_width", 0)
        if width >= WIDTH_WIDE:
            return PRESET_WIDE
        if width == WIDTH_NARROW:
            return PRESET_NARROW
        return None

    @property
    def extra_state_attributes(self):
        """`pending`: waiting for the fireplace to take over a new width."""
        return {"pending": self.coordinator.is_pending("flame_width")}

    async def async_select_option(self, option: str) -> None:
        self._require_burning()
        wide = option == PRESET_WIDE
        await self._send(
            {"flame_width": WIDTH_WIDE if wide else WIDTH_NARROW},
            lambda: self._client.set_flame_width(wide),
        )
