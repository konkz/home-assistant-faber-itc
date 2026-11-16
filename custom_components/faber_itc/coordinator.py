import asyncio
from datetime import timedelta
import logging

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

# Upper bound for one refresh (TCP connect alone may take 10 s). Keeps a slow or
# unreachable controller from blocking the HA start: the first refresh fails in
# time and setup is retried via ConfigEntryNotReady.
UPDATE_TIMEOUT = 20

class FaberITCUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Faber ITC data."""

    def __init__(self, hass, client, config_entry=None):
        """Initialize."""
        self.client = client
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
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

    @callback
    def async_set_expected_state(self, updates: dict):
        """Optimistically update the coordinator data."""
        if self.data:
            new_data = dict(self.data)
            new_data.update(updates)
            self.async_set_updated_data(new_data)

    async def _async_update_data(self):
        """Fetch data from client."""
        try:
            async with asyncio.timeout(UPDATE_TIMEOUT):
                # Connect first, otherwise the requests below go nowhere
                await self.client.fetch_data()

                # Fetch device info if missing
                info = self.client.device_info
                if not info.get("serial") or not info.get("installer_name"):
                    _LOGGER.debug("Missing device or installer info, requesting...")
                    await self.client.request_info()

                await self.client.update()
            # Latest status, the answer to update() may already be in
            return dict(self.client.last_status)
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")
