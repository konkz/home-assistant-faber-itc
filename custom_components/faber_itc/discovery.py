import asyncio
import logging
import socket
from .const import UDP_PORT, UDP_MAGIC_START, UDP_MAGIC_END

_LOGGER = logging.getLogger(__name__)

class FaberITCDiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_discovery):
        self.on_discovery = on_discovery

    def datagram_received(self, data, addr):
        if len(data) < 28:
            return

        if not data.startswith(UDP_MAGIC_START) or not data.endswith(UDP_MAGIC_END):
            return

        # sender_id = data[8:12]
        # ip_bytes = data[12:16]
        # seq = data[16:20]
        name_bytes = data[20:-4]
        
        try:
            device_name = name_bytes.split(b"\x00")[0].decode("ascii").strip()
            self.on_discovery(addr[0], device_name)
        except Exception as e:
            _LOGGER.debug("Error decoding discovery name: %s", e)

async def async_discover_devices(timeout=5.0):
    """Scan for Faber ITC devices via UDP broadcast."""
    discovered = {}

    def on_discovery(ip, name):
        if ip not in discovered:
            _LOGGER.debug("Discovered Faber ITC: %s at %s", name, ip)
            discovered[ip] = name

    loop = asyncio.get_running_loop()
    
    # Use a custom socket to allow broadcast listening if needed, 
    # though standard binding to 0.0.0.0:UDP_PORT usually suffices for received broadcasts
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: FaberITCDiscoveryProtocol(on_discovery),
        local_addr=("0.0.0.0", UDP_PORT)
    )

    try:
        await asyncio.sleep(timeout)
    finally:
        transport.close()

    return discovered
