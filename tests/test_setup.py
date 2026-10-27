"""Config entry setup: an unreachable controller must not block the HA start."""
import asyncio
from types import MappingProxyType

import pytest
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError

import custom_components.faber_itc as integration
from custom_components.faber_itc import client as client_mod
from custom_components.faber_itc import coordinator as coordinator_mod
from custom_components.faber_itc.const import CONF_HOST, DOMAIN
from custom_components.faber_itc.switch import FaberPowerSwitch
from fake_controller import FakeController, closed_port


class FakeHttp:
    def __init__(self):
        self.registrations = 0

    async def async_register_static_paths(self, configs):
        self.registrations += 1


class FakeConfigEntries:
    def __init__(self):
        self.forwarded = []

    async def async_forward_entry_setups(self, entry, platforms):
        self.forwarded.append(list(platforms))


def _entry():
    return ConfigEntry(
        data={CONF_HOST: "127.0.0.1"},
        discovery_keys=MappingProxyType({}),
        domain=DOMAIN,
        minor_version=1,
        options={},
        source="user",
        state=ConfigEntryState.SETUP_IN_PROGRESS,
        subentries_data=None,
        title="ITC Controller (test)",
        unique_id=None,
        version=1,
    )


async def _hass(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    hass.http = FakeHttp()
    hass.config_entries = FakeConfigEntries()
    return hass


async def _hanging_open_connection(*args, **kwargs):
    await asyncio.sleep(3600)


def test_setup_with_unresponsive_controller_is_retried(tmp_path, monkeypatch):
    """27.10.2026: setup hung until HA's stage-2 timeout cancelled it."""
    monkeypatch.setattr(client_mod, "TCP_TIMEOUT", 0.05)
    monkeypatch.setattr(client_mod.asyncio, "open_connection", _hanging_open_connection)

    async def scenario():
        hass = await _hass(tmp_path)
        with pytest.raises(ConfigEntryNotReady):
            await asyncio.wait_for(integration.async_setup_entry(hass, _entry()), 5)
        assert DOMAIN not in hass.data or not hass.data[DOMAIN]
        assert hass.config_entries.forwarded == []
        # retry (HA calls setup again) must not register the static path twice
        with pytest.raises(ConfigEntryNotReady):
            await asyncio.wait_for(integration.async_setup_entry(hass, _entry()), 5)
        assert hass.http.registrations == 1

    asyncio.run(scenario())


def test_setup_with_refused_connection_is_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(integration, "DEFAULT_PORT", closed_port())

    async def scenario():
        hass = await _hass(tmp_path)
        with pytest.raises(ConfigEntryNotReady):
            await asyncio.wait_for(integration.async_setup_entry(hass, _entry()), 5)

    asyncio.run(scenario())


def test_slow_refresh_is_cut_off(tmp_path, monkeypatch):
    """Whatever hangs inside a refresh, the overall timeout ends it."""
    monkeypatch.setattr(coordinator_mod, "UPDATE_TIMEOUT", 0.2)

    async def hanging_fetch(self):
        await asyncio.sleep(3600)

    monkeypatch.setattr(client_mod.FaberITCClient, "fetch_data", hanging_fetch)

    async def scenario():
        hass = await _hass(tmp_path)
        with pytest.raises(ConfigEntryNotReady):
            await asyncio.wait_for(integration.async_setup_entry(hass, _entry()), 5)

    asyncio.run(scenario())


def test_setup_with_controller_loads(tmp_path, monkeypatch):
    async def scenario():
        fake = await FakeController(temp=22.4).start()
        monkeypatch.setattr(integration, "DEFAULT_PORT", fake.port)
        hass = await _hass(tmp_path)
        entry = _entry()
        try:
            assert await asyncio.wait_for(integration.async_setup_entry(hass, entry), 5)
            assert hass.config_entries.forwarded == [["sensor", "switch"]]
            coordinator = hass.data[DOMAIN][entry.entry_id]
            await asyncio.sleep(0.3)
            assert coordinator.data["temp"] == 22.4
        finally:
            await hass.data[DOMAIN][entry.entry_id].client.disconnect()
            await fake.stop()

    asyncio.run(scenario())


def test_switch_rolls_back_when_command_fails(tmp_path):
    async def scenario():
        hass = await _hass(tmp_path)
        client = client_mod.FaberITCClient("127.0.0.1", closed_port())
        coordinator = coordinator_mod.FaberITCUpdateCoordinator(hass, client, _entry())
        coordinator.async_set_updated_data({"state": 0, "flame_height": 0, "flame_width": 0x64, "temp": 20.0})
        switch = FaberPowerSwitch(coordinator, _entry())
        assert not switch.is_on
        with pytest.raises(HomeAssistantError):
            await asyncio.wait_for(switch.async_turn_on(), 5)
        assert coordinator.data["state"] == 0
        assert not switch.is_on

    asyncio.run(scenario())
