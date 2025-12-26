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

    async def _async_update_data(self):
        """Fetch data from client."""
        try:
            data = await self.client.fetch_data()
            if data is None:
                raise UpdateFailed("Invalid data received from device")
            return data
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")
