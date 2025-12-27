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
        self._last_full_frame_words = [0] * 32  # Extended cache for sensor mining

    def set_callback(self, callback):
        """Set callback for status updates."""
        self._callback = callback

    async def connect(self):
        """Establish a long-lived connection with handshake."""
        async with self._lock:
            if self._writer:
                return True
            
            try:
                _LOGGER.warning("Connecting to %s:%s", self.host, self.port)
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), timeout=TCP_TIMEOUT
                )
                
                # Discovery Frame (Exakt 29 Bytes)
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
        """Background loop to continuously empty the socket buffer."""
        buffer = b""
        try:
            while True:
                chunk = await self._reader.read(4096)
                if not chunk:
                    _LOGGER.warning("Connection closed by device")
                    break
                
                self._last_data_time = asyncio.get_event_loop().time()
                buffer += chunk
                
                while True:
                    start_idx = buffer.find(MAGIC_START_BYTES)
                    if start_idx == -1:
                        buffer = buffer[-3:]
                        break
                    
                    end_idx = buffer.find(MAGIC_END_BYTES, start_idx)
                    if end_idx == -1:
                        break
                    
                    frame_data = buffer[start_idx : end_idx + 4]
                    buffer = buffer[end_idx + 4:]
                    _LOGGER.warning("Received frame (%d bytes)", len(frame_data))
                    self._handle_frame(frame_data)
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            _LOGGER.error("Read loop error: %s", e)
        finally:
            asyncio.create_task(self.disconnect())

    def _handle_frame(self, data):
        """Parse received frames, store state words and trigger callbacks."""
        if len(data) > 60:
            self._parse_ascii_info(data)

        num_words = len(data) // 4
        if num_words < 7:
            return

        current_words = [
            struct.unpack(">I", data[i : i + 4])[0] for i in range(0, (num_words * 4), 4)
        ]

        # Update cache (first 32 words if available)
        for i in range(min(len(current_words), 32)):
            self._last_full_frame_words[i] = current_words[i]

        status_main = current_words[3]
        # Valid states: OFF (0x1030), ON (0x1040), DUAL (0x1080)
        if status_main in [0x1030, 0x1040, 0x1080]:
            intensity = current_words[5] if len(current_words) >= 6 else 0
            
            # Extract burner mask if available (usually word index 11)
            burner_mask = BURNER_OFF_MASK
            if len(current_words) >= 12:
                burner_mask = current_words[11]
            elif status_main == STATUS_ON:
                burner_mask = BURNER_ON_MASK

            # Sensor Mining: All words from index 6 onwards are potential sensors
            raw_sensors = {}
            for i in range(6, len(current_words)):
                raw_sensors[f"word_{i}"] = hex(current_words[i])

            self.last_status = {
                "status_main": status_main,
                "intensity": intensity,
                "burner_mask": burner_mask,
                "model": self.device_info["model"],
                "manufacturer": self.device_info["manufacturer"],
                "serial": self.device_info["serial"],
                "raw_sensors": raw_sensors,
                "raw_words": [hex(w) for w in current_words],
            }

            if self._callback:
                self._callback(self.last_status)

    def _parse_ascii_info(self, data):
        """Extract metadata from frames."""
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

    async def fetch_data(self):
        """Watchdog check and return latest cached status."""
        now = asyncio.get_event_loop().time()
        if self._writer and (now - self._last_data_time > WATCHDOG_TIMEOUT):
            _LOGGER.warning("Watchdog: No data for %ss, reconnecting", WATCHDOG_TIMEOUT)
            await self.disconnect()

        await self.connect()
        return self.last_status

    async def send_frame(self, status_main, intensity, burner_mask):
        """Send command using stateful 29-byte structure and dynamic flags."""
        if not await self.connect():
            raise ConnectionError("Not connected")

        intensity_val = INTENSITY_LEVELS.get(intensity, 0)

        # Build 29-byte Command Frame (7 Words: 28 Bytes + 1 Byte Padding/Trailer Part)
        # We take the first 6 words (24 bytes) from the last known status to stay "stateful"
        # Word 0: MAGIC, Word 1: Version, Word 2: Device ID, Word 3: Status, Word 4: Flags, Word 5: Intensity
        words = list(self._last_full_frame_words[:6])

        # Fallback if no status was received yet or cache is empty
        if len(words) < 6 or words[0] != MAGIC_START:
            words = [MAGIC_START, 0x00FA0002, DEVICE_ID, status_main, 0, 0]
        
        # Stateful transformation:
        # We keep Word 0, 1, 2 as they are from the last status (unless fallback)
        # We only modify Word 3 (Status), Word 4 (Flags) and Word 5 (Intensity)
        
        words[3] = status_main
        
        # Word 4 (Flags): If the last status had flags, we keep them, 
        # unless we are switching to OFF (0x1030), where flags usually go to 0.
        if status_main == STATUS_OFF:
            words[4] = 0x00000000
        elif words[4] == 0 or words[4] == 0xFFFFFFFF:
            # Only set default if previous word 4 was empty/invalid
            words[4] = 0xFFFF0009
            
        words[5] = intensity_val
        
        # Construct the 29-byte payload:
        # 6 Words (24 Bytes) + 1 Byte Padding (0x00) + MAGIC_END (4 Bytes) = 29 Bytes
        payload = struct.pack(">6I", *words) + b"\x00" + MAGIC_END_BYTES

        _LOGGER.warning("Sending Smart-Command: %s (Intensity: %d)", hex(status_main), intensity_val)
        
        async with self._lock:
            try:
                self._writer.write(payload)
                await self._writer.drain()
                return True
            except Exception as e:
                _LOGGER.error("Failed to send command: %s", e)
                await self.disconnect()
                return False
