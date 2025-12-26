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

class FaberITCClient:
    def __init__(self, host, port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self._lock = asyncio.Lock()

    async def send_frame(self, status_main, intensity, burner_mask):
        """Send a binary frame to the device."""
        # intensity validation
        if intensity not in INTENSITY_LEVELS:
            raise ValueError(f"Invalid intensity level: {intensity}. Must be 0-4.")
        
        intensity_val = INTENSITY_LEVELS[intensity]
        
        # Construct 15 words (60 bytes)
        words = [0] * 15
        words[0] = MAGIC_START
        words[3] = status_main
        words[4] = 0xFFFF0005
        words[5] = intensity_val
        words[11] = burner_mask
        words[14] = MAGIC_END
        
        payload = struct.pack(">15I", *words)
        
        async with self._lock:
            try:
                reader, writer = await asyncio.open_connection(self.host, self.port)
                writer.write(payload)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                _LOGGER.error(f"Error sending frame: {e}")
                raise

    async def fetch_data(self):
        """Fetch current status from the device."""
        async with self._lock:
            try:
                reader, writer = await asyncio.open_connection(self.host, self.port)
                
                words = [0] * 15
                words[0] = MAGIC_START
                words[4] = 0xFFFF0009
                words[14] = MAGIC_END
                payload = struct.pack(">15I", *words)
                
                writer.write(payload)
                await writer.drain()
                
                data = await reader.readexactly(60)
                writer.close()
                await writer.wait_closed()
                
                if len(data) < 60:
                    _LOGGER.error("Received incomplete frame")
                    return None
                    
                unpacked = struct.unpack(">15I", data)
                
                if unpacked[0] != MAGIC_START or unpacked[14] != MAGIC_END:
                    _LOGGER.error("Invalid magic header or trailer")
                    return None
                    
                return {
                    "status_main": unpacked[3],
                    "flags": unpacked[4],
                    "intensity": unpacked[5],
                    "burner_mask": unpacked[11],
                }
                
            except Exception as e:
                _LOGGER.error(f"Error fetching data: {e}")
                raise
