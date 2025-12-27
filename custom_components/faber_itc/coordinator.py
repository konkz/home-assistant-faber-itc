from datetime import timedelta
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

class FaberITCUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Faber ITC data."""

    def __init__(self, hass, client):
        """Initialize."""
        self.client = client
        super().__init__(
            hass,
            _LOGGER,
            name="Faber ITC Status",
            update_interval=timedelta(seconds=30),
        )
        
        # Register callback for event-driven updates from the client's read loop
        self.client.set_callback(self._handle_client_update)

    def _handle_client_update(self, data):
        """Handle status update from client read loop."""
        _LOGGER.debug("Coordinator received event-driven update")
        self.async_set_updated_data(data)

    async def _async_update_data(self):
        """Fetch data from client (Watchdog check)."""
        try:
            # fetch_data now checks the watchdog/connection and returns cached status
            data = await self.client.fetch_data()
            if data is None:
                return {}
            return data
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")
