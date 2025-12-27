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
DEVICE_ID = 0x00007DED

# Byte sequences for robust searching
MAGIC_START_BYTES = struct.pack(">I", MAGIC_START)
MAGIC_END_BYTES = b"\xFA\xFB\xFC\xFD"

class FaberITCClient:
    def __init__(self, host, port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self._lock = asyncio.Lock()
        self.device_info = {
            "model": "Faber ITC Fireplace",
            "manufacturer": "Faber",
            "serial": None,
            "fam": None
        }

    async def _perform_handshake(self, reader, writer):
        """Perform the mandatory discovery handshake and parse metadata."""
        discovery_payload = (
            struct.pack(">6I", MAGIC_START, 0x00FA0002, 0, 0x20, 0, 0)
            + b"\x00"
            + MAGIC_END_BYTES
        )
        
        _LOGGER.warning("Sending Discovery Frame (ID 0, 29 bytes) to %s", self.host)
        writer.write(discovery_payload)
        await asyncio.wait_for(writer.drain(), timeout=TCP_TIMEOUT)
        
        # Read discovery response (Info frame)
        _LOGGER.warning("Waiting for discovery response from %s (timeout 3s)", self.host)
        try:
            frame_data = await asyncio.wait_for(self._read_frame(reader), timeout=3.0)
            if frame_data:
                _LOGGER.warning("Handshake response received (%d bytes)", len(frame_data))
                self._parse_ascii_info(frame_data)
        except asyncio.TimeoutError:
            _LOGGER.warning("Handshake response timeout - continuing anyway")

    def _parse_ascii_info(self, data):
        """Extract ASCII strings from Info frames to populate device_info."""
        strings = re.findall(b"[ -~]{3,}", data)
        for s in strings:
            try:
                text = s.decode("ascii").strip("\x00").strip()
                if not text: continue
                
                if text == "Faber":
                    self.device_info["manufacturer"] = text
                elif text.startswith("M") and len(text) >= 8:
                    self.device_info["serial"] = text
                elif "Aspect" in text or "Premium" in text:
                    self.device_info["model"] = text
                elif text in ["ASG", "FAM"]:
                    self.device_info["fam"] = text
                    
                _LOGGER.debug("Found ASCII metadata: %s", text)
            except Exception:
                continue

    def _build_command_payload(self, status_main, flags, intensity_val):
        """Build the 29-byte command frame structure from hex logs."""
        header = struct.pack(">3I", MAGIC_START, 0x00FA0002, DEVICE_ID)
        body = struct.pack(">3I", status_main, flags, intensity_val)
        padding = b"\x00"
        trailer = MAGIC_END_BYTES
        return header + body + padding + trailer

    async def _read_frame(self, reader):
        """Robustly read a single frame from the stream."""
        buffer = b""
        start_time = asyncio.get_event_loop().time()
        while True:
            if asyncio.get_event_loop().time() - start_time > TCP_TIMEOUT:
                if buffer:
                    _LOGGER.warning("Read frame timeout. Buffer state: %s", buffer.hex())
                raise asyncio.TimeoutError("Timeout searching for frame markers")
                
            chunk = await asyncio.wait_for(reader.read(4096), timeout=TCP_TIMEOUT)
            if not chunk:
                break
            buffer += chunk
            
            start_idx = buffer.find(MAGIC_START_BYTES)
            if start_idx != -1:
                end_idx = buffer.find(MAGIC_END_BYTES, start_idx)
                if end_idx != -1:
                    frame_data = buffer[start_idx : end_idx + 4]
                    return frame_data
        return None

    async def send_frame(self, status_main, intensity, burner_mask):
        """Send a command frame with handshake."""
        if intensity not in INTENSITY_LEVELS:
            raise ValueError(f"Invalid intensity level: {intensity}")
        
        intensity_val = INTENSITY_LEVELS[intensity]
        flags = 0xFFFF0009 if status_main in [STATUS_ON, STATUS_DUAL_BURNER] else 0x00000000
        payload = self._build_command_payload(status_main, flags, intensity_val)
        
        async with self._lock:
            try:
                _LOGGER.warning("Connecting to %s to send command", self.host)
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), timeout=TCP_TIMEOUT
                )
                
                await self._perform_handshake(reader, writer)
                
                _LOGGER.warning("Sending Command Frame (29 bytes) to %s", self.host)
                writer.write(payload)
                await asyncio.wait_for(writer.drain(), timeout=TCP_TIMEOUT)
                
                try:
                    await asyncio.wait_for(self._read_frame(reader), timeout=2.0)
                except asyncio.TimeoutError:
                    pass
                
                writer.close()
                await writer.wait_closed()
                _LOGGER.warning("Command sequence complete")
            except Exception:
                _LOGGER.error("Error in send_frame:\n%s", traceback.format_exc())
                raise

    async def fetch_data(self):
        """Fetch status using the stateful sequence and multi-frame reading."""
        async with self._lock:
            try:
                _LOGGER.warning("Connecting to %s to fetch data", self.host)
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), timeout=TCP_TIMEOUT
                )
                
                await self._perform_handshake(reader, writer)
                
                payload = self._build_command_payload(0x00001030, 0, 0)
                _LOGGER.warning("Sending Status Request (29 bytes) to %s", self.host)
                writer.write(payload)
                await asyncio.wait_for(writer.drain(), timeout=TCP_TIMEOUT)

                while True:
                    frame_data = await self._read_frame(reader)
                    if not frame_data:
                        break
                        
                    if len(frame_data) >= 16:
                        status_main = struct.unpack(">I", frame_data[12:16])[0]
                        if status_main in [0x1030, 0x1040, 0x1080]:
                            intensity = 0
                            if len(frame_data) >= 24:
                                intensity = struct.unpack(">I", frame_data[20:24])[0]
                            
                            writer.close()
                            await writer.wait_closed()
                            return {
                                "status_main": status_main,
                                "flags": 0,
                                "intensity": intensity,
                                "burner_mask": BURNER_ON_MASK if status_main == STATUS_ON else BURNER_OFF_MASK,
                                "model": self.device_info["model"],
                                "manufacturer": self.device_info["manufacturer"],
                                "serial": self.device_info["serial"],
                            }
                
                writer.close()
                await writer.wait_closed()
                return None
            except Exception:
                _LOGGER.error("Error in fetch_data:\n%s", traceback.format_exc())
                raise
