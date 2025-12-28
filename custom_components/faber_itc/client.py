import asyncio
import logging
import struct
import re
from .const import (
    DEFAULT_PORT,
    MAGIC_START,
    MAGIC_END,
    PROTO_HEADER,
    SENDER_ID,
    OP_IDENTIFY,
    OP_INFO_410,
    OP_INFO_1010,
    OP_STATUS,
    OP_CONTROL,
    OP_HEARTBEAT,
)

_LOGGER = logging.getLogger(__name__)

TCP_TIMEOUT = 10.0
WATCHDOG_TIMEOUT = 120.0

class FaberITCClient:
    def __init__(self, host, port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self._lock = asyncio.Lock()
        self._reader = None
        self._writer = None
        self._read_task = None
        self._callback = None
        self._last_data_time = 0
        self._reconnect_delay = 1
        self.device_info = {
            "model": "Faber ITC Fireplace",
            "manufacturer": "Faber",
            "serial": None,
        }
        self.last_status = {
            "state": 0,
            "flame_height": 0,
            "flame_width": 0,
            "temp": 0.0,
        }

    def set_callback(self, callback):
        """Set callback for status updates."""
        self._callback = callback

    async def connect(self):
        """Establish connection and start read loop."""
        async with self._lock:
            if self._writer:
                return True
            
            try:
                _LOGGER.warning("FABER ITC: Attempting connection to %s:%s", self.host, self.port)
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), timeout=TCP_TIMEOUT
                )
                
                # Discovery / Handshake
                await self._send_frame(OP_IDENTIFY, b"\x00" * 9)

                # Start background read loop
                if self._read_task:
                    self._read_task.cancel()
                self._read_task = asyncio.create_task(self._read_loop())
                self._last_data_time = asyncio.get_running_loop().time()
                
                _LOGGER.info("Connected to Faber ITC at %s:%s", self.host, self.port)
                return True
            except Exception as e:
                _LOGGER.error("Connection failed: %s", e)
                await self.disconnect()
                return False

    async def disconnect(self):
        """Close connection."""
        async with self._lock:
            if self._read_task:
                self._read_task.cancel()
                self._read_task = None
            if self._writer:
                try:
                    self._writer.close()
                    await self._writer.wait_closed()
                except:
                    pass
                finally:
                    self._writer = None
            self._reader = None

    async def _send_frame(self, opcode: int, payload: bytes):
        """Build and send a protocol frame."""
        # Opcode is 4 bytes Big Endian
        frame = (
            MAGIC_START
            + PROTO_HEADER
            + SENDER_ID
            + struct.pack(">I", opcode)
            + payload
            + MAGIC_END
        )
        if self._writer:
            self._writer.write(frame)
            await self._writer.drain()
            _LOGGER.debug("Sent Opcode 0x%08X, Payload: %s", opcode, payload.hex())

    async def _read_loop(self):
        """Background loop to process incoming frames."""
        buffer = b""
        try:
            while True:
                chunk = await self._reader.read(4096)
                if not chunk:
                    _LOGGER.warning("Connection closed by device")
                    break

                self._last_data_time = asyncio.get_running_loop().time()
                buffer += chunk

                while True:
                    start_idx = buffer.find(MAGIC_START)
                    if start_idx == -1:
                        buffer = buffer[-3:]
                        break

                    end_idx = buffer.find(MAGIC_END, start_idx)
                    if end_idx == -1:
                        break

                    frame = buffer[start_idx : end_idx + 4]
                    buffer = buffer[end_idx + 4:]
                    self._handle_frame(frame)
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            _LOGGER.error("Read loop error: %s", e)
        finally:
            asyncio.create_task(self.disconnect())

    def _handle_frame(self, data: bytes):
        """Parse received frames."""
        # Header(16) | Opcode(4) | Payload(var) | End(4)
        # Minimal frame: Magic(4) + Header(4) + ID(4) + Opcode(4) + End(4) = 20 bytes
        if len(data) < 20:
            return

        opcode_raw = struct.unpack(">I", data[16:20])[0]
        opcode_base = opcode_raw & 0x0FFFFFFF
        payload = data[20:-4]

        if opcode_base == OP_STATUS:
            _LOGGER.debug("FABER ITC: Received 1030 Payload (len=%d): %s", len(payload), payload.hex())
            if len(payload) >= 22:
                state = payload[11]
                flame = payload[15]
                width = payload[16]
                temp_raw = payload[21]
                
                self.last_status.update({
                    "state": state,
                    "flame_height": flame,
                    "flame_width": width,
                    "temp": temp_raw / 10.0,
                })
                
                _LOGGER.debug("FABER ITC: Parsed Status: %s", self.last_status)
                if self._callback:
                    self._callback(dict(self.last_status))
        
        elif opcode_base in [OP_IDENTIFY, OP_INFO_410, OP_INFO_1010]:
            self._parse_ascii_info(payload)

    def _parse_ascii_info(self, payload):
        """Extract device metadata from payload."""
        strings = re.findall(b"[ -~]{3,}", payload)
        for s in strings:
            try:
                text = s.decode("ascii").strip("\x00").strip()
                if not text: continue
                if text == "Faber": self.device_info["manufacturer"] = text
                elif text.startswith("M") and len(text) >= 8: self.device_info["serial"] = text
                elif any(x in text for x in ["Aspect", "Premium", "MatriX"]): 
                    self.device_info["model"] = text
            except: continue

    async def _send_control(self, param_id: int, value: int):
        """Helper to send 1040 control commands."""
        # Structure: FF FF | param_id(BE) | 00 00 00 | value(LE)
        payload = (
            b"\xFF\xFF"
            + struct.pack(">H", param_id)
            + b"\x00\x00\x00"
            + struct.pack("<H", value)
        )
        await self._send_frame(OP_CONTROL, payload)

    async def update(self):
        """Poll for status and send heartbeat."""
        _LOGGER.debug("FABER ITC: Polling status (1030) and heartbeat (1080)")
        await self._send_frame(OP_STATUS, b"\x00" * 8)
        await asyncio.sleep(0.1)
        await self._send_frame(OP_HEARTBEAT, b"\x00" * 8)

    async def turn_on(self):
        """Send ignition sequence."""
        _LOGGER.info("Sending Turn On sequence")
        await self._send_control(0x0002, 0)
        await asyncio.sleep(0.1)
        await self._send_control(0x0020, 0)
        await asyncio.sleep(0.5)
        await self.update()

    async def turn_off(self):
        """Send power off command."""
        _LOGGER.info("Sending Turn Off command")
        await self._send_control(0x0001, 0)
        await asyncio.sleep(0.5)
        await self.update()

    async def set_flame_height(self, level: int):
        """Set flame level (0x00, 0x19, 0x32, 0x4B, 0x64)."""
        _LOGGER.info("Setting flame level to %s", hex(level))
        await self._send_control(0x0009, level)
        await asyncio.sleep(0.5)
        await self.update()

    async def set_flame_width(self, wide: bool):
        """Toggle flame width."""
        _LOGGER.info("Setting flame width to %s", "wide" if wide else "narrow")
        await self._send_control(0x0005, 0)
        await asyncio.sleep(0.5)
        await self.update()

    async def fetch_data(self):
        """Watchdog check and return latest cached status."""
        now = asyncio.get_running_loop().time()
        if self._writer and (now - self._last_data_time > WATCHDOG_TIMEOUT):
            _LOGGER.warning("Watchdog: No data for %ss, reconnecting", WATCHDOG_TIMEOUT)
            await self.disconnect()

        if not self._writer:
            try:
                await self.connect()
                self._reconnect_delay = 1
            except Exception as e:
                _LOGGER.error("Reconnect failed: %s, retrying later", e)
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 60)

        return self.last_status
