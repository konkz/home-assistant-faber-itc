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
    """Answers status requests and records control commands."""

    def __init__(self, temp=20.5):
        self.temp = temp
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
                        writer.write(status_frame(temp=self.temp))
                        await writer.drain()
                    elif opcode == OP_CONTROL:
                        param = struct.unpack(">H", payload[2:4])[0]
                        value = struct.unpack("<H", payload[7:9])[0]
                        self.controls.append((conn, param, value))
        except ConnectionError:
            pass


def closed_port() -> int:
    """A local port nobody listens on (connect is refused)."""
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port
