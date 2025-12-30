import asyncio
import logging
import socket
from .const import UDP_PORT, UDP_MAGIC_START, UDP_MAGIC_END

_LOGGER = logging.getLogger(__name__)

class FaberITCDiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_discovery, discovery_event):
        self.on_discovery = on_discovery
        self.discovery_event = discovery_event

    def datagram_received(self, data, addr):
        _LOGGER.debug("Received UDP packet from %s: %s", addr, data.hex())
        
        if len(data) < 48:
            _LOGGER.debug("Packet too short: %d bytes", len(data))
            return

        if not data.startswith(UDP_MAGIC_START) or not data.endswith(UDP_MAGIC_END):
            _LOGGER.debug("Magic bytes mismatch")
            return

        sender_id_hex = data[8:12].hex()
        ip_bytes = data[12:16] # This is the controller IP inside the payload
        # seq = data[16:20]
        name_bytes = data[20:44]
        
        try:
            # Parse IP from payload
            controller_ip = ".".join(map(str, ip_bytes))
            # Try UTF-8 first, fallback to ASCII, ignore errors to get at least something
            try:
                device_name = name_bytes.split(b"\x00")[0].decode("utf-8").strip()
            except UnicodeDecodeError:
                device_name = name_bytes.split(b"\x00")[0].decode("ascii", errors="ignore").strip()
            
            if not device_name:
                device_name = f"Faber ITC {controller_ip}"

            # Prefer IP from payload, fallback to source IP if parsing fails (unlikely)
            host = controller_ip if controller_ip else addr[0]
            
            _LOGGER.debug("Discovered device '%s' with IP %s (ID: %s)", device_name, host, sender_id_hex)
            if self.on_discovery(host, device_name, sender_id_hex):
                self.discovery_event.set()
        except Exception as e:
            _LOGGER.error("Error decoding discovery packet: %s", e)

async def async_discover_devices(timeout=5.0, is_new_device=None):
    """Scan for Faber ITC devices via UDP broadcast."""
    discovered = {} # ip -> {name, sender_id}
    discovery_event = asyncio.Event()

    def on_discovery(ip, name, sender_id):
        if ip not in discovered:
            _LOGGER.debug("Discovered Faber ITC: %s at %s (ID: %s)", name, ip, sender_id)
            # If it's a new device (or no filter provided), signal to stop discovery
            if is_new_device is None or is_new_device(ip, sender_id):
                discovered[ip] = {"name": name, "sender_id": sender_id}
                return True
        return False

    loop = asyncio.get_running_loop()
    
    # Use a custom socket to allow broadcast listening if needed, 
    # though standard binding to 0.0.0.0:UDP_PORT usually suffices for received broadcasts
    transport, _ = await loop.create_datagram_endpoint(
        lambda: FaberITCDiscoveryProtocol(on_discovery, discovery_event),
        local_addr=("0.0.0.0", UDP_PORT)
    )

    try:
        # Wait for the first new device to be found or timeout
        try:
            await asyncio.wait_for(discovery_event.wait(), timeout=timeout)
            _LOGGER.debug("Discovery stopped early after finding a new device")
        except asyncio.TimeoutError:
            _LOGGER.debug("Discovery timed out after %s seconds", timeout)
    finally:
        transport.close()

    return discovered
