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
            "article": None,
            "variant": None,
            "installer_name": None,
            "installer_phone": None,
            "installer_web": None,
            "installer_mail": None,
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
        """Establish connection."""
        async with self._lock:
            if self._writer:
                return True
            
            try:
                _LOGGER.debug("Connecting to %s:%s", self.host, self.port)
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), timeout=TCP_TIMEOUT
                )
                
                await self._send_frame(OP_IDENTIFY, b"\x00" * 9)

                if self._read_task:
                    self._read_task.cancel()
                self._read_task = asyncio.create_task(self._read_loop())
                self._last_data_time = asyncio.get_running_loop().time()
                
                _LOGGER.debug("Connected to %s:%s", self.host, self.port)
                return True
            except Exception as e:
                _LOGGER.debug("Connection failed: %s", e)
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
                    _LOGGER.debug("Connection closed by device")
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
        if len(data) < 20:
            return

        opcode_raw = struct.unpack(">I", data[12:16])[0]
        opcode_base = opcode_raw & 0x0FFFFFFF
        payload = data[16:-4]

        if len(payload) < 9:
            return
            
        expected_len = payload[8]
        actual_len = len(payload) - 9
        
        if expected_len != actual_len:
            _LOGGER.debug(
                "Payload length mismatch for Opcode 0x%08X: Expected %d, got %d", 
                opcode_raw, expected_len, actual_len
            )

        if opcode_base == OP_STATUS:
            if len(payload) >= 22:
                data_part = payload[9:]
                state = data_part[2]
                flame = data_part[6]
                width = data_part[7]
                temp_raw = data_part[12]
                
                self.last_status.update({
                    "state": state,
                    "flame_height": flame,
                    "flame_width": width,
                    "temp": temp_raw / 10.0,
                })
                
                _LOGGER.debug("Parsed Status: %s", self.last_status)
                if self._callback:
                    self._callback(dict(self.last_status))
        
        elif opcode_base in [OP_IDENTIFY, OP_INFO_410, OP_INFO_1010]:
            self._parse_ascii_info(opcode_base, payload)

    def _parse_ascii_info(self, opcode_base, payload):
        """Extract device metadata from payload (null-terminated strings)."""
        _LOGGER.debug("Parsing Info for Opcode 0x%04X, Payload: %s", opcode_base, payload.hex())
        
        if len(payload) < 9:
            return

        # According to dissector and protocol: 
        # Payload = Reserved (8 bytes) + Length Byte (1 byte) + Data
        data_part = payload[9:]
        _LOGGER.debug("Data part for Opcode 0x%04X: %s", opcode_base, data_part.hex())
        
        # Split by null bytes and decode
        strings = []
        # The device often pads with 0x00 or has multiple 0x00 between strings
        for p in data_part.split(b"\x00"):
            if len(p) >= 2: # Ignore single bytes or empty strings
                try:
                    # Use latin-1 to preserve more characters
                    text = p.decode("latin-1").strip()
                    # Filter out non-printable characters except space
                    text = "".join(c for c in text if c.isprintable())
                    if text:
                        strings.append(text)
                except Exception as e:
                    _LOGGER.debug("String decode error: %s", e)
                    continue

        _LOGGER.debug("Extracted strings for Opcode 0x%04X: %s", opcode_base, strings)

        if not strings:
            return

        # Based on faber_itc_protocol.md Section 7:
        if opcode_base == OP_INFO_1010:
            if len(strings) >= 1: self.device_info["model"] = strings[0]
            if len(strings) >= 2: 
                self.device_info["article"] = strings[1]
                # The 'Article No' is often the model identifier (serial)
                self.device_info["serial"] = strings[1]
            if len(strings) >= 3: self.device_info["variant"] = strings[2]
            _LOGGER.info("Device Info Updated: Model=%s, Serial=%s", 
                         self.device_info["model"], self.device_info["serial"])
            
        elif opcode_base == OP_INFO_410:
            if len(strings) >= 1: self.device_info["installer_name"] = strings[0]
            if len(strings) >= 2: self.device_info["installer_phone"] = strings[1]
            if len(strings) >= 3: self.device_info["installer_web"] = strings[2]
            if len(strings) >= 4: self.device_info["installer_mail"] = strings[3]
            _LOGGER.info("Installer Info Updated: Name=%s", self.device_info["installer_name"])

    async def _send_control(self, param_id: int, value: int):
        """Helper to send control commands."""
        payload = (
            b"\xFF\xFF"
            + struct.pack(">H", param_id)
            + b"\x00\x00\x00"
            + struct.pack("<H", value)
        )
        await self._send_frame(OP_CONTROL, payload)

    async def request_info(self):
        """Request device and installer info."""
        _LOGGER.debug("Requesting Device and Installer Info")
        await self._send_frame(OP_INFO_1010, b"\x00" * 9)
        await asyncio.sleep(0.2)
        await self._send_frame(OP_INFO_410, b"\x00" * 9)

    async def update(self):
        """Poll for status and send heartbeat."""
        await self._send_frame(OP_STATUS, b"\x00" * 9)
        await asyncio.sleep(0.1)
        await self._send_frame(OP_HEARTBEAT, b"\x00" * 9)

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
        """Toggle flame width. 0x0006 for wide, 0x0005 for narrow."""
        _LOGGER.info("Setting flame width to %s", "wide" if wide else "narrow")
        param_id = 0x0006 if wide else 0x0005
        await self._send_control(param_id, 0)
        await asyncio.sleep(0.5)
        await self.update()

    async def fetch_data(self):
        """Watchdog check and return latest cached status."""
        now = asyncio.get_running_loop().time()
        if self._writer and (now - self._last_data_time > WATCHDOG_TIMEOUT):
            _LOGGER.debug("Watchdog: No data for %ss, reconnecting", WATCHDOG_TIMEOUT)
            await self.disconnect()

        if not self._writer:
            try:
                await self.connect()
                self._reconnect_delay = 1
            except Exception as e:
                _LOGGER.debug("Reconnect failed: %s, retrying later", e)
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 60)

        return self.last_status
