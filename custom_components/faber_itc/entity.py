"""Shared base for Faber ITC entities."""
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_SENDER_ID,
    DOMAIN,
    STATE_IGNITING,
    STATE_OFF,
    STATE_ON,
    STATE_SHUTTING_DOWN,
)


class FaberEntity(CoordinatorEntity):
    """Coordinator entity attached to the fireplace device."""

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

    @property
    def fireplace_burning(self) -> bool:
        """True while the fireplace is on or igniting (accepts flame commands)."""
        state = (self.coordinator.data or {}).get("state", STATE_OFF)
        return state not in (STATE_OFF, STATE_SHUTTING_DOWN)

    def _require_burning(self):
        """Flame commands are only sent to a burning fireplace, never ignite it."""
        if not self.fireplace_burning:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="fireplace_off"
            )

    async def _set_power(self, on: bool, flame=None):
        """Ignite (then set `flame`) or turn off; HA shows the transition meanwhile."""
        coordinator = self.coordinator
        transition = coordinator.power_transition
        if on:
            if transition == STATE_OFF:
                # Never re-ignite a fireplace that is still going out
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="shutting_down"
                )
            if transition == STATE_ON or self.fireplace_burning:
                if flame is not None:
                    await self._set_flame(flame)
                return
            coordinator.async_begin_power(STATE_ON, flame)
            expected, command = {"state": STATE_IGNITING}, self._client.turn_on
        else:
            if transition == STATE_OFF or not self.fireplace_burning:
                return
            coordinator.async_begin_power(STATE_OFF)
            expected, command = {"state": STATE_SHUTTING_DOWN}, self._client.turn_off
        try:
            await self._send(expected, command)
        except HomeAssistantError:
            coordinator.async_end_power()
            raise

    async def _set_flame(self, flame: int, zero_is_off: bool = True):
        """Set the flame height of a burning fireplace, ignite it if needed.

        0 turns the fireplace off ("off is off"), unless `zero_is_off` is False
        (then 0 is the pilot flame).
        """
        coordinator = self.coordinator
        coordinator.async_manual_flame_change()
        if flame == 0 and zero_is_off:
            await self._set_power(False)
            return
        if coordinator.power_transition == STATE_ON:
            # Still igniting: the height is sent once the fireplace burns
            coordinator.pending_flame = flame
            coordinator.async_set_expected_state({"flame_height": flame})
            return
        if not self.fireplace_burning:
            await self._set_power(True, flame)
            return
        await self._send(
            {"flame_height": flame}, lambda: self._client.set_flame_height(flame)
        )

    async def _send(self, expected: dict, command):
        """Show the expected state, send the command and roll back if it fails.

        Flame height / width stay at the requested value until the controller
        reports it (it does so a few seconds later), so the UI does not jump back.
        """
        previous = self.coordinator.data
        settings = [key for key in expected if key != "state"]
        for key in settings:
            self.coordinator.async_expect(key, expected[key])
        self.coordinator.async_set_expected_state(expected)
        try:
            await command()
        except Exception as err:
            for key in settings:
                self.coordinator.async_forget(key)
            if previous is not None:
                self.coordinator.async_set_updated_data(previous)
            raise HomeAssistantError(f"Faber ITC: command not sent ({err})") from err
        await self.coordinator.async_request_refresh()
