import logging
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Faber ITC sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        FaberTemperatureSensor(coordinator, entry),
        FaberInstallerSensor(coordinator, entry),
    ])

class FaberTemperatureSensor(CoordinatorEntity, SensorEntity):
    """Representation of the Faber Fireplace room temperature."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_temperature"
        self._attr_translation_key = "temperature"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        info = self.coordinator.client.device_info
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=info.get("model", "Faber Fireplace"),
            manufacturer=info.get("manufacturer", "Faber"),
            model=info.get("model", "Faber ITC Fireplace"),
            serial_number=info.get("serial"),
        )

    @property
    def native_value(self):
        """Return the current temperature."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("temp")

class FaberInstallerSensor(CoordinatorEntity, SensorEntity):
    """Representation of the Faber Installer info."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:account-wrench"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_installer"
        self._attr_translation_key = "installer"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        info = self.coordinator.client.device_info
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=info.get("model", "Faber Fireplace"),
            manufacturer=info.get("manufacturer", "Faber"),
            model=info.get("model", "Faber ITC Fireplace"),
            serial_number=info.get("serial"),
        )

    @property
    def native_value(self):
        """Return the installer name."""
        return self.coordinator.client.device_info.get("installer_name")

    @property
    def extra_state_attributes(self):
        """Return installer contact details."""
        info = self.coordinator.client.device_info
        return {
            "phone": info.get("installer_phone"),
            "website": info.get("installer_web"),
            "email": info.get("installer_mail"),
            "article_no": info.get("article"),
            "variant": info.get("variant"),
        }
