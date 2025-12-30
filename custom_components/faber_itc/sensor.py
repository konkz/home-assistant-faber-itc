import logging
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, CONF_SENDER_ID

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
        # Use a stable unique_id based on entry_id to prevent recorder issues
        self._attr_unique_id = f"{entry.entry_id}_temperature"
        self._attr_translation_key = "temperature"
        self.entity_id = f"sensor.{entry.entry_id}_temperature"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        info = self.coordinator.client.device_info
        model_name = info.get("model") or self._entry.data.get("name") or "Faber ITC Fireplace"
        sender_id = self._entry.data.get(CONF_SENDER_ID)
        
        identifiers = {(DOMAIN, self._entry.entry_id)}
        connections = set()
        if sender_id:
            identifiers.add((DOMAIN, sender_id))
            # Format sender_id as a pseudo-MAC (e.g. fac42cd8 -> fa:c4:2c:d8)
            formatted_mac = ":".join(sender_id[i:i+2] for i in range(0, len(sender_id), 2))
            connections.add((dr.CONNECTION_NETWORK_MAC, formatted_mac))

        return DeviceInfo(
            identifiers=identifiers,
            connections=connections,
            name=model_name,
            manufacturer=info.get("manufacturer", "Faber"),
            model=model_name,
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
        self.entity_id = f"sensor.{entry.entry_id}_installer"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        # This property is already correctly implemented in FaberTemperatureSensor
        # and inherited by CoordinatorEntity. But since we have it here too,
        # let's keep it consistent.
        info = self.coordinator.client.device_info
        model_name = info.get("model") or self._entry.data.get("name") or "Faber ITC Fireplace"
        sender_id = self._entry.data.get(CONF_SENDER_ID)
        
        identifiers = {(DOMAIN, self._entry.entry_id)}
        connections = set()
        if sender_id:
            identifiers.add((DOMAIN, sender_id))
            formatted_mac = ":".join(sender_id[i:i+2] for i in range(0, len(sender_id), 2))
            connections.add((dr.CONNECTION_NETWORK_MAC, formatted_mac))

        return DeviceInfo(
            identifiers=identifiers,
            connections=connections,
            name=model_name,
            manufacturer=info.get("manufacturer", "Faber"),
            model=model_name,
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
