import asyncio
import logging
import struct
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

TCP_TIMEOUT = 5.0
DEVICE_ID = 0x00007DED

# Byte sequences for robust searching
MAGIC_START_BYTES = struct.pack(">I", MAGIC_START)
MAGIC_END_BYTES = b"\xFA\xFB\xFC\xFD"

class FaberITCClient:
    def __init__(self, host, port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self._lock = asyncio.Lock()

    def _get_base_words(self):
        """Return the base 15 words with constants according to protocol."""
        words = [0] * 15
        words[0] = MAGIC_START
        words[1] = 0x00FA0002 # Protocol Version
        words[2] = DEVICE_ID
        # Words 3, 4, 5 set by caller
        words[6] = 0x00FAFBFC
        words[7] = 0xFDA1A2A3
        words[8] = 0xA400FA00
        words[9] = 0x02FAC42C
        words[10] = 0xD8100010
        # Word 11 set by caller
        # Word 12 observed 0
        words[13] = 0x0000FAFB
        words[14] = 0xFCFD0000 # Corrected Trailer part
        return words

    async def send_frame(self, status_main, intensity, burner_mask):
        """Send a binary frame to the device."""
        if intensity not in INTENSITY_LEVELS:
            raise ValueError(f"Invalid intensity level: {intensity}. Must be 0-4.")
        
        intensity_val = INTENSITY_LEVELS[intensity]
        words = self._get_base_words()
        words[3] = status_main
        words[4] = 0xFFFF0005 # Command Flag
        words[5] = intensity_val
        words[11] = burner_mask
        
        payload = struct.pack(">15I", *words)
        
        async with self._lock:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=TCP_TIMEOUT
                )
                writer.write(payload)
                await asyncio.wait_for(writer.drain(), timeout=TCP_TIMEOUT)
                writer.close()
                await writer.wait_closed()
            except asyncio.TimeoutError:
                _LOGGER.error("Timeout sending frame to %s", self.host)
                raise
            except Exception as e:
                _LOGGER.error("Error sending frame: %s", e)
                raise

    async def fetch_data(self):
        """Fetch current status from the device with robust byte-sequence reading."""
        async with self._lock:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=TCP_TIMEOUT
                )
                
                # Passive phase: try to read existing data first (e.g. welcome message)
                buffer = b""
                start_time = asyncio.get_event_loop().time()
                
                # First try to read without requesting (wait max 1s for passive data)
                try:
                    chunk = await asyncio.wait_for(reader.read(1024), timeout=1.0)
                    if chunk:
                        buffer += chunk
                        _LOGGER.debug("Received passive data: %s", buffer.hex())
                except asyncio.TimeoutError:
                    pass

                # If no frame found yet, send active request
                if not self._find_frame(buffer):
                    words = self._get_base_words()
                    words[4] = 0xFFFF0009 # Status Request Flag
                    payload = struct.pack(">15I", *words)
                    writer.write(payload)
                    await asyncio.wait_for(writer.drain(), timeout=TCP_TIMEOUT)

                # Active reading phase
                while True:
                    if asyncio.get_event_loop().time() - start_time > TCP_TIMEOUT:
                        _LOGGER.debug("Buffer state on timeout: %s", buffer.hex())
                        raise asyncio.TimeoutError("Timeout searching for frame markers")
                        
                    chunk = await asyncio.wait_for(reader.read(1024), timeout=TCP_TIMEOUT)
                    if not chunk:
                        break
                    buffer += chunk
                    
                    frame = self._find_frame(buffer)
                    if frame:
                        writer.close()
                        await writer.wait_closed()
                        return frame
                
                writer.close()
                await writer.wait_closed()
                return None
                
            except asyncio.TimeoutError:
                _LOGGER.error("Timeout fetching data from %s", self.host)
                raise
            except Exception as e:
                _LOGGER.error("Error fetching data: %s", e)
                raise

    def _find_frame(self, buffer):
        """Search for a complete frame in the byte buffer."""
        start_idx = buffer.find(MAGIC_START_BYTES)
        if start_idx != -1:
            end_idx = buffer.find(MAGIC_END_BYTES, start_idx)
            if end_idx != -1:
                # Frame found from MAGIC_START to MAGIC_END
                frame_data = buffer[start_idx : end_idx + 4]
                
                # Ensure we have enough data to unpack status words (min 12 words)
                if len(frame_data) < 48:
                    return None
                    
                # We unpack words starting from word 0 (Magic)
                # Word 3: STATUS_MAIN, Word 4: FLAGS, Word 5: INTENSITY, Word 11: BURNER_MASK
                try:
                    words = [struct.unpack(">I", frame_data[i:i+4])[0] for i in range(0, 48, 4)]
                    return {
                        "status_main": words[3],
                        "flags": words[4],
                        "intensity": words[5],
                        "burner_mask": words[11],
                    }
                except Exception as e:
                    _LOGGER.debug("Error parsing frame data: %s", e)
                    return None
        return None
