import asyncio
import logging
import struct
from .const import MAGIC_START, MAGIC_END, INTENSITY_LEVELS, STATUS_ON, STATUS_OFF, BURNER_ON_MASK, BURNER_OFF_MASK
from .templates import BASE_COMMAND_FRAME

_LOGGER = logging.getLogger(__name__)

class FaberClient:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self._callbacks = []

    async def connect(self):
        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            asyncio.create_task(self._read_loop())
            return True
        except Exception as e:
            _LOGGER.error(f"Connection failed: {e}")
            return False

    def register_callback(self, callback):
        self._callbacks.append(callback)

    async def set_state(self, power_on: bool, level: int = 1, double_burner: bool = False):
        """Erzeugt aus dem Template einen passenden Frame und sendet ihn."""
        frame = list(BASE_COMMAND_FRAME)
        
        if not power_on:
            frame[3] = STATUS_OFF
            frame[11] = BURNER_OFF_MASK
            frame[5] = 0x00
        else:
            frame[3] = STATUS_ON
            frame[11] = BURNER_ON_MASK # Hier später Logik für 2 Brenner (0x8000...)
            frame[5] = INTENSITY_LEVELS.get(level, 0x19)
            
        await self.send_frame(frame)

    async def send_frame(self, frame_words):
        if not self.writer: return
        payload = b"".join([struct.pack(">I", w) for w in frame_words])
        self.writer.write(payload)
        await self.writer.drain()

    async def _read_loop(self):
        buffer = b""
        while True:
            try:
                data = await self.reader.read(1024)
                if not data: break
                buffer += data
                while len(buffer) >= 8:
                    start_idx = buffer.find(struct.pack(">I", MAGIC_START))
                    if start_idx == -1:
                        buffer = buffer[-3:]; break
                    end_idx = buffer.find(struct.pack(">I", MAGIC_END), start_idx)
                    if end_idx == -1: break
                    frame_data = buffer[start_idx : end_idx + 4]
                    buffer = buffer[end_idx + 4:]
                    words = [struct.unpack(">I", frame_data[i:i+4])[0] for i in range(0, len(frame_data), 4)]
                    for cb in self._callbacks: cb(words)
            except Exception as e:
                _LOGGER.error(f"Read loop error: {e}"); break
