"""TCP client: no deadlock on failed connects, commands never vanish silently."""
import asyncio

import pytest

from custom_components.faber_itc import client as client_mod
from custom_components.faber_itc.client import FaberITCClient
from fake_controller import FakeController, closed_port


async def _hanging_open_connection(*args, **kwargs):
    await asyncio.sleep(3600)


def test_connect_timeout_releases_lock(monkeypatch):
    """27.10.2026: a TCP timeout in connect() deadlocked on its own lock."""
    monkeypatch.setattr(client_mod, "TCP_TIMEOUT", 0.05)
    monkeypatch.setattr(client_mod.asyncio, "open_connection", _hanging_open_connection)

    async def scenario():
        client = FaberITCClient("192.0.2.1")
        assert await asyncio.wait_for(client.connect(), 2) is False
        assert not client._lock.locked()
        await asyncio.wait_for(client.disconnect(), 2)
        with pytest.raises(ConnectionError):
            await asyncio.wait_for(client.fetch_data(), 2)
        # a second failed attempt must not hang either
        assert await asyncio.wait_for(client.connect(), 2) is False

    asyncio.run(scenario())


def test_connect_refused_returns_false():
    async def scenario():
        client = FaberITCClient("127.0.0.1", closed_port())
        assert await asyncio.wait_for(client.connect(), 2) is False
        assert client._writer is None
        assert not client._lock.locked()

    asyncio.run(scenario())


def test_status_and_control_roundtrip():
    async def scenario():
        fake = await FakeController(temp=21.7).start()
        client = FaberITCClient("127.0.0.1", fake.port)
        updates = []
        client.set_callback(updates.append)
        try:
            await client.fetch_data()
            await client.update()
            await asyncio.sleep(0.2)
            assert updates and updates[-1]["temp"] == 21.7
            assert updates[-1]["flame_width"] == 0x64

            await client.set_flame_height(0x32)
            await asyncio.sleep(0.1)
            assert (1, 0x0009, 0x32) in fake.controls
        finally:
            await client.disconnect()
            await fake.stop()

    asyncio.run(scenario())


def test_control_reconnects_after_connection_loss():
    """Commands after a dropped connection used to be discarded silently."""

    async def scenario():
        fake = await FakeController().start()
        client = FaberITCClient("127.0.0.1", fake.port)
        try:
            assert await client.connect()
            fake.drop_clients()
            await asyncio.sleep(0.2)
            assert client._writer is None  # read loop noticed the loss

            await client.turn_off()
            await asyncio.sleep(0.1)
            assert fake.connections == 2
            assert (2, 0x0001, 0) in fake.controls
        finally:
            await client.disconnect()
            await fake.stop()

    asyncio.run(scenario())


def test_control_raises_when_unreachable():
    async def scenario():
        client = FaberITCClient("127.0.0.1", closed_port())
        with pytest.raises(ConnectionError):
            await asyncio.wait_for(client.turn_on(), 2)
        with pytest.raises(ConnectionError):
            await asyncio.wait_for(client.update(), 2)

    asyncio.run(scenario())


def test_old_read_loop_does_not_drop_new_connection():
    async def scenario():
        fake = await FakeController().start()
        client = FaberITCClient("127.0.0.1", fake.port)
        try:
            assert await client.connect()
            await client.disconnect()
            assert await client.connect()
            await asyncio.sleep(0.2)
            assert client._writer is not None
            await client.update()
        finally:
            await client.disconnect()
            await fake.stop()

    asyncio.run(scenario())
