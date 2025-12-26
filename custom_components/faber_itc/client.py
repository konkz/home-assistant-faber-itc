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
        words[14] = MAGIC_END
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
        """Fetch current status from the device with robust frame reading."""
        async with self._lock:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=TCP_TIMEOUT
                )
                
                # Request status
                words = self._get_base_words()
                words[4] = 0xFFFF0009 # Status Request Flag
                payload = struct.pack(">15I", *words)
                
                writer.write(payload)
                await asyncio.wait_for(writer.drain(), timeout=TCP_TIMEOUT)
                
                # Robust reading: find magic start and end
                buffer = b""
                start_time = asyncio.get_event_loop().time()
                
                while True:
                    if asyncio.get_event_loop().time() - start_time > TCP_TIMEOUT:
                        raise asyncio.TimeoutError("Timeout searching for frame markers")
                        
                    chunk = await asyncio.wait_for(reader.read(1024), timeout=TCP_TIMEOUT)
                    if not chunk:
                        break
                    buffer += chunk
                    
                    start_idx = buffer.find(struct.pack(">I", MAGIC_START))
                    if start_idx != -1:
                        end_idx = buffer.find(struct.pack(">I", MAGIC_END), start_idx)
                        if end_idx != -1:
                            # Frame found
                            frame_data = buffer[start_idx : end_idx + 4]
                            writer.close()
                            await writer.wait_closed()
                            
                            # Parse frame (minimum 15 words)
                            if len(frame_data) < 60:
                                _LOGGER.error("Frame too short: %d bytes", len(frame_data))
                                return None
                                
                            unpacked = struct.unpack(">15I", frame_data[:60])
                            return {
                                "status_main": unpacked[3],
                                "flags": unpacked[4],
                                "intensity": unpacked[5],
                                "burner_mask": unpacked[11],
                            }
                
                writer.close()
                await writer.wait_closed()
                return None
                
            except asyncio.TimeoutError:
                _LOGGER.error("Timeout fetching data from %s", self.host)
                raise
            except Exception as e:
                _LOGGER.error("Error fetching data: %s", e)
                raise
