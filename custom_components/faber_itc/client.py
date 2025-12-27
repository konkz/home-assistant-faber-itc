import asyncio
import logging
import struct
import traceback
import re
from .const import (
    DEFAULT_PORT,
    MAGIC_START,
    MAGIC_END,
    INTENSITY_LEVELS,
    STATUS_OFF,
    STATUS_ON,
    STATUS_DUAL_BURNER,
    BURNER_OFF_MASK,
    BURNER_ON_MASK,
    BURNER_DUAL_MASK,
)

_LOGGER = logging.getLogger(__name__)

TCP_TIMEOUT = 10.0
WATCHDOG_TIMEOUT = 120.0 # Reconnect if no data for 2 mins
DEVICE_ID = 0x00007DED

MAGIC_START_BYTES = struct.pack(">I", MAGIC_START)
MAGIC_END_BYTES = b"\xFA\xFB\xFC\xFD"

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
        self.device_info = {
            "model": "Faber ITC Fireplace",
            "manufacturer": "Faber",
            "serial": None,
            "fam": None
        }
        self.last_status = None

    def set_callback(self, callback):
        """Set callback for status updates."""
        self._callback = callback

    async def connect(self):
        """Establish a long-lived connection with handshake (29 bytes)."""
        async with self._lock:
            if self._writer:
                return True

            try:
                _LOGGER.warning("Connecting to %s:%s", self.host, self.port)
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), timeout=TCP_TIMEOUT
                )

                # Discovery Frame (Exakt 29 Bytes)
                # Structure: Magic(4) + Ver(4) + ID(4) + Cmd(4) + Padding(9) + Trailer(4) = 29 bytes
                discovery_payload = (
                    struct.pack(">4I", MAGIC_START, 0x00FA0002, 0, 0x20)
                    + b"\x00" * 9
                    + MAGIC_END_BYTES
                )

                _LOGGER.warning("Sending Discovery (29 bytes) to %s", self.host)
                self._writer.write(discovery_payload)
                await self._writer.drain()

                # Start background read loop
                if self._read_task:
                    self._read_task.cancel()
                self._read_task = asyncio.create_task(self._read_loop())
                self._last_data_time = asyncio.get_event_loop().time()

                _LOGGER.warning("Long-lived connection established to %s", self.host)
                return True
            except Exception as e:
                _LOGGER.error("Connection failed: %s", e)
                await self.disconnect()
                return False

    async def disconnect(self):
        """Close connection and cleanup."""
        if self._read_task:
            self._read_task.cancel()
            self._read_task = None
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except:
                pass
            self._writer = None
        self._reader = None

    async def _read_loop(self):
        """Background loop to continuously empty the socket buffer using read_until logic."""
        buffer = b""
        try:
            while True:
                # We use a simple read but process until the trailer is found
                chunk = await self._reader.read(4096)
                if not chunk:
                    _LOGGER.warning("Connection closed by device")
                    break

                self._last_data_time = asyncio.get_event_loop().time()
                buffer += chunk

                # Process all frames in buffer (find MAGIC_START ... MAGIC_END)
                while True:
                    start_idx = buffer.find(MAGIC_START_BYTES)
                    if start_idx == -1:
                        buffer = buffer[-3:] # Keep partial magic start
                        break

                    end_idx = buffer.find(MAGIC_END_BYTES, start_idx)
                    if end_idx == -1:
                        break # Wait for more data to complete frame

                    frame_data = buffer[start_idx : end_idx + 4]
                    buffer = buffer[end_idx + 4:]
                    _LOGGER.warning("Received frame (%d bytes): %s", len(frame_data), frame_data.hex()[:60] + "...")
                    self._handle_frame(frame_data)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            _LOGGER.error("Read loop error: %s", e)
        finally:
            asyncio.create_task(self.disconnect())

    def _handle_frame(self, data):
        """Parse received frames and trigger callbacks."""
        # 1. Parse ASCII metadata if frame is large enough
        if len(data) > 60:
            self._parse_ascii_info(data)

        # 2. Parse Status
        if len(data) >= 16:
            status_main = struct.unpack(">I", data[12:16])[0]
            if status_main in [0x1030, 0x1040, 0x1080]:
                intensity = 0
                if len(data) >= 24:
                    intensity = struct.unpack(">I", data[20:24])[0]

                burner_mask = BURNER_OFF_MASK
                if len(data) >= 48:
                    burner_mask = struct.unpack(">I", data[44:48])[0]
                elif status_main == STATUS_ON:
                    burner_mask = BURNER_ON_MASK

                self.last_status = {
                    "status_main": status_main,
                    "intensity": intensity,
                    "burner_mask": burner_mask,
                    "model": self.device_info["model"],
                    "manufacturer": self.device_info["manufacturer"],
                    "serial": self.device_info["serial"],
                }

                if self._callback:
                    self._callback(self.last_status)

    def _parse_ascii_info(self, data):
        """Extract metadata from frames using regex."""
        strings = re.findall(b"[ -~]{3,}", data)
        for s in strings:
            try:
                text = s.decode("ascii").strip("\x00").strip()
                if not text: continue
                if text == "Faber": self.device_info["manufacturer"] = text
                elif text.startswith("M") and len(text) >= 8: self.device_info["serial"] = text
                elif "Aspect" in text or "Premium" in text: self.device_info["model"] = text
                elif text in ["ASG", "FAM"]: self.device_info["fam"] = text
            except: continue

    async def send_frame(self, status_main, intensity, burner_mask):
        """Send command using precise 29-byte structure."""
        if not await self.connect():
            raise ConnectionError("Not connected")

        intensity_val = INTENSITY_LEVELS.get(intensity, 0)
        flags = 0xFFFF0009 if status_main in [STATUS_ON, STATUS_DUAL_BURNER] else 0x00000000

        # Build 29-byte command
        # Structure: Magic(4) + Ver(4) + ID(4) + Status(4) + Flags(4) + Intensity(4) + Pad(1) + Trailer(4) = 29 bytes
        payload = (
            struct.pack(">6I", MAGIC_START, 0x00FA0002, DEVICE_ID, status_main, flags, intensity_val)
            + b"\x00"
            + MAGIC_END_BYTES
        )

        async with self._lock:
            try:
                self._writer.write(payload)
                await asyncio.wait_for(self._writer.drain(), timeout=TCP_TIMEOUT)
                _LOGGER.warning("Command sent (29 bytes): %s", payload.hex())
            except Exception as e:
                _LOGGER.error("Failed to send command: %s", e)
                await self.disconnect()
                raise
