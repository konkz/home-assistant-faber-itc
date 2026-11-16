"""Thermostat: modulates the flame height towards a target room temperature.

The ITC protocol has no thermostat of its own (the remote's thermostat runs in
the handset), so the regulation runs in Home Assistant. It only changes the
flame height of a burning fireplace: it never ignites it and never turns it
off, its lowest step is the pilot flame.
"""
import logging
import time

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_TENTHS, UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers.restore_state import RestoreEntity
from .const import DOMAIN, INTENSITY_LEVELS, STATE_IGNITING, STATE_ON
from .entity import FaberEntity

_LOGGER = logging.getLogger(__name__)

DEFAULT_TARGET = 21.0
# Kelvin below the target from which flame level 1, 2, 3, 4 is used;
# at or above the target the fireplace burns with the pilot flame only
LEVEL_THRESHOLDS = (0.0, 0.5, 1.0, 1.5)
# A level is only left once the temperature is this far past the edge
HYSTERESIS = 0.2
# Seconds between two thermostat commands (a fireplace reacts slowly)
MIN_COMMAND_INTERVAL = 60
# Seconds the controller gets to report a commanded flame height; a different
# height after that was set by someone else (remote, app)
OVERRIDE_GRACE = 30

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Faber ITC climate platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FaberThermostat(coordinator, entry)])

def _level_for(diff: float) -> int:
    return sum(1 for threshold in LEVEL_THRESHOLDS if diff >= threshold)

def flame_level_for(diff: float, current_level: int | None = None) -> int:
    """Flame level (0 = pilot ... 4) for a room `diff` Kelvin below the target."""
    level = _level_for(diff)
    if current_level is None or level == current_level:
        return level
    if level > current_level:
        return max(current_level, _level_for(diff - HYSTERESIS))
    return min(current_level, _level_for(diff + HYSTERESIS))

def level_of(flame_height: int) -> int:
    """Closest flame level for a protocol flame height."""
    return min(INTENSITY_LEVELS, key=lambda lvl: abs(INTENSITY_LEVELS[lvl] - flame_height))

class FaberThermostat(FaberEntity, ClimateEntity, RestoreEntity):
    """Room thermostat on top of the flame height."""

    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = PRECISION_TENTHS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 15
    _attr_max_temp = 28

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_thermostat"
        self._attr_translation_key = "thermostat"
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_target_temperature = DEFAULT_TARGET
        self._commanded = None  # flame height last sent by the thermostat
        self._commanded_at = 0.0  # when it was sent (grace for the controller)
        self._next_command_at = 0.0  # no new command before this
        self._task = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.coordinator.thermostat = self
        last = await self.async_get_last_state()
        if last is not None:
            if last.state in self._attr_hvac_modes:
                self._attr_hvac_mode = HVACMode(last.state)
            if (target := last.attributes.get(ATTR_TEMPERATURE)) is not None:
                self._attr_target_temperature = float(target)
        self._regulate()

    async def async_will_remove_from_hass(self):
        if self.coordinator.thermostat is self:
            self.coordinator.thermostat = None
        if self._task:
            self._task.cancel()
        await super().async_will_remove_from_hass()

    @property
    def current_temperature(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("temp")

    @property
    def hvac_action(self):
        data = self.coordinator.data or {}
        if not self.fireplace_burning:
            return HVACAction.OFF
        if data.get("state") == STATE_IGNITING:
            return HVACAction.PREHEATING
        return HVACAction.HEATING if data.get("flame_height", 0) > 0 else HVACAction.IDLE

    async def async_set_temperature(self, **kwargs):
        """A new target never switches the thermostat on or off."""
        if (target := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        self._attr_target_temperature = float(target)
        self._next_command_at = 0.0  # react to a new target right away
        self._regulate()
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode):
        self._attr_hvac_mode = HVACMode(hvac_mode)
        self._commanded = None
        self._next_command_at = 0.0
        self._regulate()
        self.async_write_ha_state()

    async def async_turn_on(self):
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self):
        await self.async_set_hvac_mode(HVACMode.OFF)

    @callback
    def async_manual_override(self):
        """The flame was set by hand: hand control back, like the remote does."""
        if self._attr_hvac_mode == HVACMode.OFF:
            return
        _LOGGER.info("Flame height set manually, thermostat switched off")
        self._stop()
        self.async_write_ha_state()

    def _stop(self):
        self._attr_hvac_mode = HVACMode.OFF
        self._commanded = None
        if self._task and not self._task.done():
            self._task.cancel()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._regulate()
        super()._handle_coordinator_update()

    @callback
    def _regulate(self):
        """Send a new flame height if the room temperature asks for one."""
        data = self.coordinator.data or {}
        if self._attr_hvac_mode != HVACMode.HEAT or data.get("state") != STATE_ON:
            self._commanded = None
            return
        temp = data.get("temp")
        if not temp or self._attr_target_temperature is None:
            return
        if self._task and not self._task.done():
            return

        now = time.monotonic()
        flame = data.get("flame_height", 0)
        unconfirmed = self._commanded is not None and flame != self._commanded
        if unconfirmed and now - self._commanded_at > OVERRIDE_GRACE:
            _LOGGER.info(
                "Flame height changed outside Home Assistant (%s, expected %s), "
                "thermostat switched off", flame, self._commanded
            )
            self._stop()
            return
        if now < self._next_command_at:
            return

        # A command the controller has not reported yet counts as the current height
        current = self._commanded if unconfirmed else flame
        level = flame_level_for(self._attr_target_temperature - temp, level_of(current))
        value = INTENSITY_LEVELS[level]
        if value == current:
            self._commanded = value
            return
        self._commanded = value
        self._commanded_at = now
        self._next_command_at = now + MIN_COMMAND_INTERVAL
        _LOGGER.debug("Thermostat: %.1f °C, target %.1f °C -> level %s", temp, self._attr_target_temperature, level)
        self._task = self.hass.async_create_task(self._apply(value))

    async def _apply(self, value: int):
        try:
            await self._client.set_flame_height(value)
        except Exception as err:
            # Retried after MIN_COMMAND_INTERVAL; no override detection meanwhile
            self._commanded = None
            _LOGGER.warning("Thermostat could not set the flame height: %s", err)
