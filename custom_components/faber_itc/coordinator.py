import asyncio
from datetime import timedelta
import logging
import time

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import STATE_IGNITING, STATE_OFF, STATE_ON, STATE_SHUTTING_DOWN

_LOGGER = logging.getLogger(__name__)

# Upper bound for one refresh (TCP connect alone may take 10 s). Keeps a slow or
# unreachable controller from blocking the HA start: the first refresh fails in
# time and setup is retried via ConfigEntryNotReady.
UPDATE_TIMEOUT = 20

# After a power command the controller keeps reporting the old state until the
# fireplace has ignited / gone out (about 40 s each). Until then, at most this
# long, the coordinator reports "igniting" / "shutting down".
POWER_TRANSITION_TIMEOUT = 90
# A new flame height / width is reported a few seconds after the command; the
# coordinator keeps reporting the requested value until then, at most this long.
SETTING_TIMEOUT = 30

class FaberITCUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Faber ITC data."""

    def __init__(self, hass, client, config_entry=None):
        """Initialize."""
        self.client = client
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="Faber ITC Status",
            update_interval=timedelta(seconds=10),
        )
        self._initial_info_fetched = False
        # Thermostat entity (climate platform), notified about manual flame changes
        self.thermostat = None
        self._power_target = None  # STATE_ON / STATE_OFF while switching
        self._power_deadline = 0.0
        self.pending_flame = None  # flame height to set once ignited
        self._expected = {}  # data key -> (requested value, deadline)
        
        # Register callback for event-driven updates from the client's read loop
        self.client.set_callback(self._handle_client_update)

    @callback
    def _handle_client_update(self, data):
        """Handle status update from client read loop."""
        self.async_set_updated_data(self._with_transition(data))

    @property
    def power_transition(self):
        """STATE_ON / STATE_OFF while the fireplace ignites / goes out, else None."""
        if self._power_target is not None and time.monotonic() > self._power_deadline:
            return None
        return self._power_target

    @callback
    def async_begin_power(self, target, flame=None):
        """A power command is on its way; `flame` is set once ignited."""
        self._power_target = target
        self._power_deadline = time.monotonic() + POWER_TRANSITION_TIMEOUT
        self.pending_flame = flame if target == STATE_ON else None

    @callback
    def async_end_power(self):
        """Forget a power transition (command failed)."""
        self._power_target = None
        self.pending_flame = None

    @callback
    def async_expect(self, key, value):
        """A command for `key` is on its way: report `value` until confirmed."""
        self._expected[key] = (value, time.monotonic() + SETTING_TIMEOUT)

    @callback
    def async_forget(self, key):
        self._expected.pop(key, None)

    def is_pending(self, key) -> bool:
        """True while the controller has not confirmed a requested value yet."""
        expected = self._expected.get(key)
        return expected is not None and time.monotonic() <= expected[1]

    def _with_transition(self, data):
        """Report the state the fireplace is heading to instead of the old one."""
        if data is None:
            return data
        if self._expected:
            data = dict(data)
            now = time.monotonic()
            for key, (value, deadline) in list(self._expected.items()):
                if data.get(key) == value or now > deadline:
                    del self._expected[key]
                else:
                    data[key] = value
        target = self._power_target
        if target is None:
            return data
        state = data.get("state")
        reached = state == target
        if reached or time.monotonic() > self._power_deadline:
            self._power_target = None
            flame, self.pending_flame = self.pending_flame, None
            if reached and target == STATE_ON and flame is not None:
                self.async_expect("flame_height", flame)
                data = dict(data, flame_height=flame)
                self.hass.async_create_task(self._set_pending_flame(flame))
            return data
        data = dict(data)
        data["state"] = STATE_IGNITING if target == STATE_ON else STATE_SHUTTING_DOWN
        return data

    async def _set_pending_flame(self, flame):
        try:
            await self.client.set_flame_height(flame)
        except Exception as err:
            self.async_forget("flame_height")
            _LOGGER.warning("Could not set the flame height after ignition: %s", err)

    @callback
    def async_set_expected_state(self, updates: dict):
        """Optimistically update the coordinator data."""
        if self.data:
            new_data = dict(self.data)
            new_data.update(updates)
            self.async_set_updated_data(new_data)

    @callback
    def async_manual_flame_change(self):
        """A user set the flame height by hand: the thermostat steps back."""
        if self.thermostat is not None:
            self.thermostat.async_manual_override()

    async def _async_update_data(self):
        """Fetch data from client."""
        try:
            async with asyncio.timeout(UPDATE_TIMEOUT):
                # Connect first, otherwise the requests below go nowhere
                await self.client.fetch_data()

                # Fetch device info if missing
                info = self.client.device_info
                if not info.get("serial") or not info.get("installer_name"):
                    _LOGGER.debug("Missing device or installer info, requesting...")
                    await self.client.request_info()

                await self.client.update()
            # Latest status, the answer to update() may already be in
            return self._with_transition(dict(self.client.last_status))
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")
