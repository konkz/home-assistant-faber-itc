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

    async def _perform_handshake(self, reader, writer):
        """Perform the mandatory stateful discovery handshake."""
        # Step 1: Send Discovery Frame (ID 0, Word 3 = 0x20) - 32 Bytes
        discovery_words = [
            MAGIC_START,
            0x00FA0002,
            0x00000000, # ID 0
            0x00000020, # Word 3 = 0x20
            0x00000000,
            0x00000000,
            0x00000000,
            0xFAFBFCFD, # Trailer
        ]
        payload = struct.pack(">8I", *discovery_words)
        
        _LOGGER.warning("Sending Discovery Frame (ID 0) to %s", self.host)
        writer.write(payload)
        await asyncio.wait_for(writer.drain(), timeout=TCP_TIMEOUT)
        
        # Step 2: Read and discard incoming info frame
        _LOGGER.warning("Waiting for discovery response from %s", self.host)
        buffer = b""
        start_time = asyncio.get_event_loop().time()
        while True:
            if asyncio.get_event_loop().time() - start_time > 5.0:
                _LOGGER.warning("Handshake response timeout (discarding and continuing)")
                break
                
            chunk = await asyncio.wait_for(reader.read(1024), timeout=2.0)
            if not chunk:
                break
            buffer += chunk
            _LOGGER.warning("Handshake data received (%d bytes): %s", len(chunk), chunk.hex())
            if MAGIC_END_BYTES in buffer:
                _LOGGER.warning("Discovery response complete")
                break

    def _build_command_payload(self, status_main, intensity_val, flags=0xFFFF0009):
        """Build the 33-byte command frame structure."""
        # Hex structure: a1a2a3a4 00fa0002 00007ded 00001030 00000000 00000000 00000000 00 fafbfcfd
        header = struct.pack(">3I", MAGIC_START, 0x00FA0002, DEVICE_ID)
        body = struct.pack(">4I", status_main, flags, intensity_val, 0)
        padding = b"\x00"
        trailer = MAGIC_END_BYTES
        return header + body + padding + trailer

    async def send_frame(self, status_main, intensity, burner_mask):
        """Send a binary frame to the device with stateful handshake."""
        if intensity not in INTENSITY_LEVELS:
            raise ValueError(f"Invalid intensity level: {intensity}. Must be 0-4.")
        
        intensity_val = INTENSITY_LEVELS[intensity]
        # Ensure correct flags for commands
        command_flags = 0xFFFF0005 if status_main in [STATUS_ON, STATUS_DUAL_BURNER] else 0x00000000
        payload = self._build_command_payload(status_main, intensity_val, command_flags)
        
        async with self._lock:
            try:
                _LOGGER.warning("Connecting to %s to send command", self.host)
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=TCP_TIMEOUT
                )
                
                await self._perform_handshake(reader, writer)
                
                _LOGGER.warning("Sending Command Frame (ID 7DED) to %s", self.host)
                writer.write(payload)
                await asyncio.wait_for(writer.drain(), timeout=TCP_TIMEOUT)
                
                # Optional: Read response to clear buffer
                try:
                    await asyncio.wait_for(reader.read(1024), timeout=1.0)
                except:
                    pass
                    
                writer.close()
                await writer.wait_closed()
                _LOGGER.warning("Command sequence complete")
            except Exception as e:
                _LOGGER.error("Error in command sequence: %s", e)
                raise

    async def fetch_data(self):
        """Fetch status using the stateful handshake sequence."""
        async with self._lock:
            try:
                _LOGGER.warning("Connecting to %s to fetch data", self.host)
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=TCP_TIMEOUT
                )
                
                await self._perform_handshake(reader, writer)
                
                # Send Status Request (using 0x1030 frame or just a normal ping)
                payload = self._build_command_payload(0x00001030, 0, 0x00000000)
                _LOGGER.warning("Sending Status Request to %s", self.host)
                writer.write(payload)
                await asyncio.wait_for(writer.drain(), timeout=TCP_TIMEOUT)

                buffer = b""
                start_time = asyncio.get_event_loop().time()
                while True:
                    if asyncio.get_event_loop().time() - start_time > TCP_TIMEOUT:
                        _LOGGER.warning("Buffer state on timeout: %s", buffer.hex())
                        writer.close()
                        await writer.wait_closed()
                        raise asyncio.TimeoutError("Timeout searching for frame markers")
                        
                    chunk = await asyncio.wait_for(reader.read(1024), timeout=TCP_TIMEOUT)
                    if not chunk:
                        _LOGGER.warning("Connection closed by device")
                        break
                    
                    buffer += chunk
                    _LOGGER.warning("Received chunk (%d bytes): %s", len(chunk), chunk.hex())
                    
                    frame = self._find_frame(buffer)
                    if frame:
                        _LOGGER.warning("Complete frame identified and parsed")
                        writer.close()
                        await writer.wait_closed()
                        return frame
                
                writer.close()
                await writer.wait_closed()
                return None
                
            except Exception as e:
                _LOGGER.error("Error fetching data from %s: %s", self.host, e)
                raise

    def _find_frame(self, buffer):
        """Search for a complete frame in the byte buffer."""
        start_idx = buffer.find(MAGIC_START_BYTES)
        if start_idx != -1:
            end_idx = buffer.find(MAGIC_END_BYTES, start_idx)
            if end_idx != -1:
                # Frame found
                frame_data = buffer[start_idx : end_idx + 4]
                
                if len(frame_data) < 16:
                    return None
                    
                try:
                    # Parse status from Word 3 (Byte 12-15)
                    status_main = struct.unpack(">I", frame_data[12:16])[0]
                    # Default other values if frame is short
                    intensity = 0
                    burner_mask = BURNER_OFF_MASK
                    
                    if len(frame_data) >= 24:
                        intensity_raw = struct.unpack(">I", frame_data[20:24])[0]
                        intensity = intensity_raw
                    if len(frame_data) >= 48:
                        burner_mask = struct.unpack(">I", frame_data[44:48])[0]

                    return {
                        "status_main": status_main,
                        "flags": 0,
                        "intensity": intensity,
                        "burner_mask": burner_mask,
                    }
                except Exception as e:
                    _LOGGER.warning("Error parsing frame data: %s", e)
                    return None
        return None
