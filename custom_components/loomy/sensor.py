"""Sensor platform for the Loomy integration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfPower, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LoomyConfigEntry, LoomyCoordinator


@dataclass(frozen=True, kw_only=True)
class LoomySensorEntityDescription(SensorEntityDescription):
    """Describes a Loomy sensor."""

    value_fn: Callable[[dict[str, Any]], float]


SENSORS = (
    LoomySensorEntityDescription(
        key="consumption",
        translation_key="consumption",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda data: round(
            data["consumption_day"] + data["consumption_night"], 3
        ),
    ),
    LoomySensorEntityDescription(
        key="injection",
        translation_key="injection",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda data: round(data["injection_day"] + data["injection_night"], 3),
    ),
    LoomySensorEntityDescription(
        key="current_consumption",
        translation_key="current_consumption",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=lambda data: data["current_consumption"],
    ),
    LoomySensorEntityDescription(
        key="current_injection",
        translation_key="current_injection",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=lambda data: data["current_injection"],
    ),
    LoomySensorEntityDescription(
        key="gas",
        translation_key="gas",
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        value_fn=lambda data: data["gas"],
    ),
    LoomySensorEntityDescription(
        key="water",
        translation_key="water",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        value_fn=lambda data: data["water"],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LoomyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Loomy sensors."""
    async_add_entities(
        LoomySensor(entry.runtime_data, description) for description in SENSORS
    )


class LoomySensor(CoordinatorEntity[LoomyCoordinator], SensorEntity):
    """A Loomy sensor."""

    _attr_has_entity_name = True
    entity_description: LoomySensorEntityDescription

    def __init__(
        self,
        coordinator: LoomyCoordinator,
        description: LoomySensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Loomy",
            manufacturer="Loomy",
            model="Dongle",
        )

    @property
    def native_value(self) -> float:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
