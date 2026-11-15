"""Power transitions, flame height ("off is off"), width and the thermostat."""
import asyncio

import pytest
from homeassistant.components.climate import HVACAction, HVACMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.faber_itc import climate as climate_mod
from custom_components.faber_itc import coordinator as coordinator_mod
from custom_components.faber_itc.client import FaberITCClient
from custom_components.faber_itc.climate import FaberThermostat, flame_level_for
from custom_components.faber_itc.const import STATE_IGNITING, STATE_ON, STATE_SHUTTING_DOWN
from custom_components.faber_itc.coordinator import FaberITCUpdateCoordinator
from custom_components.faber_itc.number import FaberFlameHeightNumber
from custom_components.faber_itc.select import FaberFlameWidthSelect
from custom_components.faber_itc.switch import FaberFlameLevelSwitch, FaberPowerSwitch
from fake_controller import FakeController
from test_setup import _entry, _hass


def run(tmp_path, scenario, **fake_state):
    """Run `scenario(fake, coordinator)` against a fake controller."""

    async def main():
        fake = await FakeController(**fake_state).start()
        hass = await _hass(tmp_path)
        client = FaberITCClient("127.0.0.1", fake.port)
        coordinator = FaberITCUpdateCoordinator(hass, client, _entry())
        try:
            await refresh(coordinator)
            await scenario(fake, coordinator)
        finally:
            await client.disconnect()
            await fake.stop()

    asyncio.run(main())


async def refresh(coordinator):
    await coordinator.async_refresh()
    await asyncio.sleep(0.25)  # status answer and follow-up commands


def params(fake):
    return [(param, value) for _, param, value in fake.controls]


def test_flame_level_for():
    assert [flame_level_for(d) for d in (2.0, 1.2, 0.7, 0.1, -0.1)] == [4, 3, 2, 1, 0]
    # hysteresis: a level is only left 0.2 K past its edge
    assert flame_level_for(1.05, 2) == 2
    assert flame_level_for(1.25, 2) == 3
    assert flame_level_for(-0.1, 1) == 1
    assert flame_level_for(-0.25, 1) == 0


def test_power_on_shows_igniting_until_controller_confirms(tmp_path):
    async def scenario(fake, coordinator):
        fake.apply_power = False
        switch = FaberPowerSwitch(coordinator, _entry())
        await switch.async_turn_on()
        await refresh(coordinator)
        # controller still reports "off", HA keeps showing the ignition
        assert coordinator.data["state"] == STATE_IGNITING
        assert switch.is_on
        assert switch.extra_state_attributes["status"] == "igniting"
        await switch.async_turn_on()
        assert params(fake) == [(0x0002, 0), (0x0020, 0)]

        fake.state = STATE_ON
        await refresh(coordinator)
        assert coordinator.data["state"] == STATE_ON
        assert coordinator.power_transition is None

    run(tmp_path, scenario)


def test_no_ignition_while_going_out(tmp_path, monkeypatch):
    monkeypatch.setattr(coordinator_mod, "POWER_TRANSITION_TIMEOUT", 2)

    async def scenario(fake, coordinator):
        fake.apply_power = False
        switch = FaberPowerSwitch(coordinator, _entry())
        await switch.async_turn_off()
        await refresh(coordinator)
        assert coordinator.data["state"] == STATE_SHUTTING_DOWN
        assert not switch.is_on
        with pytest.raises(HomeAssistantError):
            await switch.async_turn_on()
        assert params(fake) == [(0x0001, 0)]

        # the controller never confirmed: after the timeout its state counts again
        await asyncio.sleep(2)
        await refresh(coordinator)
        assert coordinator.data["state"] == STATE_ON

    run(tmp_path, scenario, state=STATE_ON, flame=0x32)


def test_flame_height_ignites_then_sets_level_and_zero_is_off(tmp_path):
    async def scenario(fake, coordinator):
        fake.apply_power = False
        number = FaberFlameHeightNumber(coordinator, _entry())
        assert number.native_value == 0
        await number.async_set_native_value(60)  # snaps to 50 %
        assert params(fake) == [(0x0002, 0), (0x0020, 0)]
        await refresh(coordinator)
        assert number.native_value == 50

        fake.state = STATE_ON  # ignition finished
        await refresh(coordinator)
        assert params(fake)[-1] == (0x0009, 50)
        await refresh(coordinator)
        assert number.native_value == 50

        await number.async_set_native_value(0)
        assert params(fake)[-1] == (0x0001, 0)
        assert (0x0009, 0) not in params(fake)

    run(tmp_path, scenario)


def test_new_setting_is_held_until_the_controller_confirms(tmp_path):
    """01.11.2026: 100 % -> 75 % showed 100 % again until the controller caught up."""

    async def scenario(fake, coordinator):
        fake.apply_settings = False
        number = FaberFlameHeightNumber(coordinator, _entry())
        select = FaberFlameWidthSelect(coordinator, _entry())
        await number.async_set_native_value(75)
        await select.async_select_option("narrow")
        await refresh(coordinator)
        # controller still reports 100 % / wide
        assert number.native_value == 75
        assert number.extra_state_attributes["pending"]
        assert select.current_option == "narrow"
        assert select.extra_state_attributes["pending"]

        fake.flame, fake.width = 75, 0x32
        await refresh(coordinator)
        assert number.native_value == 75
        assert not number.extra_state_attributes["pending"]
        assert not select.extra_state_attributes["pending"]

        # a controller that never takes the value over wins after the timeout
        coordinator_mod_timeout = coordinator_mod.SETTING_TIMEOUT
        coordinator_mod.SETTING_TIMEOUT = 0.3
        try:
            await number.async_set_native_value(50)
            await asyncio.sleep(0.4)
            await refresh(coordinator)
            assert number.native_value == 75
        finally:
            coordinator_mod.SETTING_TIMEOUT = coordinator_mod_timeout

    run(tmp_path, scenario, state=STATE_ON, flame=100)


def test_level_switch_off_turns_fireplace_off(tmp_path):
    async def scenario(fake, coordinator):
        level_2 = FaberFlameLevelSwitch(coordinator, _entry(), 2)
        level_3 = FaberFlameLevelSwitch(coordinator, _entry(), 3)
        assert level_2.is_on and not level_3.is_on
        await level_3.async_turn_off()
        assert params(fake) == []
        await level_2.async_turn_off()
        assert params(fake) == [(0x0001, 0)]

    run(tmp_path, scenario, state=STATE_ON, flame=0x32)


def test_width_select(tmp_path):
    async def scenario(fake, coordinator):
        select = FaberFlameWidthSelect(coordinator, _entry())
        assert select.current_option == "wide"
        await select.async_select_option("narrow")
        await refresh(coordinator)
        assert params(fake) == [(0x0005, 0)]
        assert select.current_option == "narrow"

        fake.state = 0
        await refresh(coordinator)
        with pytest.raises(HomeAssistantError):
            await select.async_select_option("wide")

    run(tmp_path, scenario, state=STATE_ON, flame=0x32)


def test_thermostat(tmp_path, monkeypatch):
    monkeypatch.setattr(climate_mod, "MIN_COMMAND_INTERVAL", 0)
    monkeypatch.setattr(climate_mod, "OVERRIDE_GRACE", 0)

    async def scenario(fake, coordinator):
        thermostat = FaberThermostat(coordinator, _entry())
        thermostat.hass = coordinator.hass
        thermostat.async_write_ha_state = lambda: None
        coordinator.thermostat = thermostat

        async def step():
            await refresh(coordinator)
            thermostat._regulate()
            if thermostat._task:
                await thermostat._task
            await refresh(coordinator)

        await thermostat.async_set_temperature(temperature=21)
        assert params(fake) == []  # thermostat is off
        await thermostat.async_set_hvac_mode(HVACMode.HEAT)
        await step()
        assert params(fake)[-1] == (0x0009, 100)  # 2 K too cold
        assert thermostat.hvac_action == HVACAction.HEATING

        fake.temp = 21.3
        await step()
        # warm enough: pilot flame, the fireplace keeps burning
        assert params(fake)[-1] == (0x0009, 0)
        assert (0x0001, 0) not in params(fake)
        assert thermostat.hvac_action == HVACAction.IDLE

        fake.flame = 0x32  # someone uses the remote
        await step()
        assert thermostat.hvac_mode == HVACMode.OFF

        await thermostat.async_set_hvac_mode(HVACMode.HEAT)
        await FaberFlameHeightNumber(coordinator, _entry()).async_set_native_value(75)
        assert thermostat.hvac_mode == HVACMode.OFF

        fake.state = 0
        await refresh(coordinator)
        assert thermostat.hvac_action == HVACAction.OFF

    run(tmp_path, scenario, state=STATE_ON, flame=0, temp=19.0)


def test_new_target_keeps_the_thermostat_on(tmp_path):
    """Changing the target neither switches the thermostat off nor on."""

    async def scenario(fake, coordinator):
        thermostat = FaberThermostat(coordinator, _entry())
        thermostat.hass = coordinator.hass
        thermostat.async_write_ha_state = lambda: None
        coordinator.thermostat = thermostat
        fake.apply_settings = False  # the controller reports the height later

        await thermostat.async_set_temperature(temperature=21)
        assert thermostat.hvac_mode == HVACMode.OFF
        assert params(fake) == []

        await thermostat.async_set_hvac_mode(HVACMode.HEAT)
        await thermostat._task
        assert params(fake)[-1] == (0x0009, 0)  # warm enough: pilot flame

        # New targets while the controller still reports the old height
        for target in (22.0, 22.5, 24.5):
            await thermostat.async_set_temperature(temperature=target)
            if thermostat._task:
                await thermostat._task
            await refresh(coordinator)
            assert thermostat.hvac_mode == HVACMode.HEAT
        assert params(fake)[-1] == (0x0009, 100)  # 2 K too cold now

        fake.apply_settings = True
        fake.flame = 100
        await refresh(coordinator)
        await thermostat.async_set_temperature(temperature=23.5)
        assert thermostat.hvac_mode == HVACMode.HEAT

    run(tmp_path, scenario, state=STATE_ON, flame=100, temp=22.5)
