from datetime import timedelta
import logging

from homeassistant.core import callback
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
            update_interval=timedelta(seconds=10),
        )
        self._initial_info_fetched = False
        
        # Register callback for event-driven updates from the client's read loop
        self.client.set_callback(self._handle_client_update)

    @callback
    def _handle_client_update(self, data):
        """Handle status update from client read loop."""
        self.async_set_updated_data(data)

    async def _async_update_data(self):
        """Fetch data from client."""
        try:
            # Fetch device info once at the start or after reconnection
            if not self._initial_info_fetched:
                await self.client.request_info()
                self._initial_info_fetched = True

            await self.client.update()
            data = await self.client.fetch_data()
            if data is None:
                return {}
            return data
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")
