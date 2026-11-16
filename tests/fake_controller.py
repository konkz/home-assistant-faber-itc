"""Minimal stand-in for the ITC controller's TCP side (port 58779)."""
import asyncio
import struct

from custom_components.faber_itc.const import (
    MAGIC_END,
    MAGIC_START,
    OP_CONTROL,
    OP_STATUS,
    PROTO_HEADER,
)

SERVER_ID = b"\xFA\xC4\x2C\xD8"


def frame(opcode: int, payload: bytes) -> bytes:
    return MAGIC_START + PROTO_HEADER + SERVER_ID + struct.pack(">I", opcode) + payload + MAGIC_END


def status_frame(state=0, flame=0, width=0x64, temp=20.5) -> bytes:
    data = bytearray(32)
    data[2] = state
    data[6] = flame
    data[7] = width
    data[11:13] = struct.pack(">H", int(round(temp * 10)))
    return frame(0x10000000 | OP_STATUS, b"\x00" * 8 + bytes([len(data)]) + bytes(data))


class FakeController:
    """Answers status requests, records control commands and applies them."""

    def __init__(self, temp=20.5, state=0, flame=0, width=0x64):
        self.temp = temp
        self.state = state
        self.flame = flame
        self.width = width
        # The real controller reports a new power state only ~40 s later
        self.apply_power = True
        # ... and a new flame height / width a few seconds later
        self.apply_settings = True
        self.controls = []  # (connection number, param_id, value)
        self.connections = 0
        self._writers = []
        self._server = None
        self.port = None

    async def start(self):
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def stop(self):
        self.drop_clients()
        self._server.close()
        await self._server.wait_closed()

    def drop_clients(self):
        for writer in self._writers:
            writer.close()
        self._writers.clear()

    async def _handle(self, reader, writer):
        self.connections += 1
        conn = self.connections
        self._writers.append(writer)
        buffer = b""
        try:
            while chunk := await reader.read(4096):
                buffer += chunk
                while (end := buffer.find(MAGIC_END)) != -1:
                    raw, buffer = buffer[: end + 4], buffer[end + 4 :]
                    opcode = struct.unpack(">I", raw[12:16])[0]
                    payload = raw[16:-4]
                    if opcode == OP_STATUS:
                        writer.write(
                            status_frame(self.state, self.flame, self.width, self.temp)
                        )
                        await writer.drain()
                    elif opcode == OP_CONTROL:
                        param = struct.unpack(">H", payload[2:4])[0]
                        value = struct.unpack("<H", payload[7:9])[0]
                        self.controls.append((conn, param, value))
                        self._apply(param, value)
        except ConnectionError:
            pass


    def _apply(self, param, value):
        if param in (0x0001, 0x0002, 0x0020) and not self.apply_power:
            return
        if param in (0x0005, 0x0006, 0x0009) and not self.apply_settings:
            return
        if param == 0x0001:
            self.state = 0
        elif param == 0x0020:
            self.state = 1
        elif param == 0x0005:
            self.width = 0x32
        elif param == 0x0006:
            self.width = 0x64
        elif param == 0x0009:
            self.flame = value


def closed_port() -> int:
    """A local port nobody listens on (connect is refused)."""
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port
