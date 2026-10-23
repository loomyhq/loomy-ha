"""Sensor platform for the Loomy integration."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LoomyConfigEntry, LoomyCoordinator
from .p1 import MBUS_DEVICE_TYPE_GAS, MBUS_DEVICE_TYPE_WATER, P1Telegram, P1Value

type ValueFn = Callable[[P1Telegram], P1Value]


@dataclass(frozen=True, kw_only=True)
class LoomySensorEntityDescription(SensorEntityDescription):
    """Describes a Loomy sensor."""

    value_fn: ValueFn
    attributes_fn: Callable[[P1Telegram], dict[str, Any]] | None = None


def _register(obis: str) -> ValueFn:
    """Read a register from the telegram."""
    return lambda telegram: telegram.get(obis)


def _total(*obis: str) -> ValueFn:
    """Sum registers, for example the day and night tariff."""

    def value_fn(telegram: P1Telegram) -> float | None:
        values = [telegram.get(code) for code in obis]
        if not all(isinstance(value, float) for value in values):
            return None
        return round(sum(values), 3)  # type: ignore[arg-type]

    return value_fn


def _mbus(device_type: str, obis: str) -> ValueFn:
    """Read a register from the submeter of the given type, on any channel."""

    def value_fn(telegram: P1Telegram) -> P1Value:
        if (channel := telegram.mbus_channel(device_type)) is None:
            return None
        return telegram.get(f"0-{channel}:{obis}")

    return value_fn


def _enum(value_fn: ValueFn, states: dict[str, str]) -> ValueFn:
    """Translate a raw enum value, like 0001, into a state."""
    return lambda telegram: states.get(value_fn(telegram))  # type: ignore[arg-type]


def _text(value_fn: ValueFn) -> ValueFn:
    """Decode a hex string, like an equipment ID, into text."""

    def decode(telegram: P1Telegram) -> str | None:
        try:
            text = bytes.fromhex(value_fn(telegram)).decode()  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        # A state is at most 255 characters, the text message up to 1024.
        return text[:255]

    return decode


def _ean(value_fn: ValueFn) -> ValueFn:
    """Decode an EAN, the meter publishes dashes when it has not been set."""
    decode = _text(value_fn)

    def value(telegram: P1Telegram) -> str | None:
        if (ean := decode(telegram)) is not None and set(ean) == {"-"}:
            return "not set"
        return ean

    return value


def _timestamp(value_fn: ValueFn) -> ValueFn:
    """Only pass on valid timestamps, meters publish garbage ones."""

    def value(telegram: P1Telegram) -> datetime | None:
        timestamp = value_fn(telegram)
        return timestamp if isinstance(timestamp, datetime) else None

    return value


def _peak_history(telegram: P1Telegram) -> list[dict[str, Any]] | None:
    """Return the monthly peaks of the last 13 months, oldest first."""
    if not (values := telegram.objects.get("0-0:98.1.0")):
        return None
    # (entries)(1-0:1.6.0)(1-0:1.6.0), then (month)(peak time)(peak) per month.
    entries = values[3:]
    months = [
        {"time": time, "value": value}
        for time, value in zip(entries[1::3], entries[2::3], strict=False)
        # Skip months with a garbage timestamp or value.
        if isinstance(time, datetime) and isinstance(value, float)
    ]
    return sorted(months, key=lambda month: month["time"])


def _last_peak(telegram: P1Telegram) -> P1Value:
    """Return the peak of the most recent month in the history."""
    return history[-1]["value"] if (history := _peak_history(telegram)) else None


TARIFFS = {"0001": "day", "0002": "night"}
SWITCH_STATES = {"0": "disconnected", "1": "connected", "2": "ready_for_reconnection"}
GRID_CONFIGURATIONS = {"230": "3x230v", "400": "3n400v"}

ENERGY = {
    "device_class": SensorDeviceClass.ENERGY,
    "state_class": SensorStateClass.TOTAL_INCREASING,
    "native_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
}
POWER = {
    "device_class": SensorDeviceClass.POWER,
    "state_class": SensorStateClass.MEASUREMENT,
    "native_unit_of_measurement": UnitOfPower.KILO_WATT,
}

# Phase L1, L2 and L3 registers are 20 apart: 1-0:21.7.0, 1-0:41.7.0, 1-0:61.7.0.
PHASES = {"L1": 20, "L2": 40, "L3": 60}

SENSORS: tuple[LoomySensorEntityDescription, ...] = (
    LoomySensorEntityDescription(
        key="consumption",
        translation_key="consumption",
        value_fn=_total("1-0:1.8.1", "1-0:1.8.2"),
        **ENERGY,
    ),
    LoomySensorEntityDescription(
        key="consumption_day",
        translation_key="consumption_day",
        value_fn=_register("1-0:1.8.1"),
        **ENERGY,
    ),
    LoomySensorEntityDescription(
        key="consumption_night",
        translation_key="consumption_night",
        value_fn=_register("1-0:1.8.2"),
        **ENERGY,
    ),
    LoomySensorEntityDescription(
        key="injection",
        translation_key="injection",
        value_fn=_total("1-0:2.8.1", "1-0:2.8.2"),
        **ENERGY,
    ),
    LoomySensorEntityDescription(
        key="injection_day",
        translation_key="injection_day",
        value_fn=_register("1-0:2.8.1"),
        **ENERGY,
    ),
    LoomySensorEntityDescription(
        key="injection_night",
        translation_key="injection_night",
        value_fn=_register("1-0:2.8.2"),
        **ENERGY,
    ),
    LoomySensorEntityDescription(
        key="current_consumption",
        translation_key="current_consumption",
        value_fn=_register("1-0:1.7.0"),
        **POWER,
    ),
    LoomySensorEntityDescription(
        key="current_injection",
        translation_key="current_injection",
        value_fn=_register("1-0:2.7.0"),
        **POWER,
    ),
    LoomySensorEntityDescription(
        key="average_demand",
        translation_key="average_demand",
        value_fn=_register("1-0:1.4.0"),
        **POWER,
    ),
    LoomySensorEntityDescription(
        key="peak_demand",
        translation_key="peak_demand",
        value_fn=_register("1-0:1.6.0"),
        **POWER,
    ),
    LoomySensorEntityDescription(
        key="peak_demand_last_month",
        translation_key="peak_demand_last_month",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=_last_peak,
        attributes_fn=lambda telegram: {"history": _peak_history(telegram)},
    ),
    *(
        LoomySensorEntityDescription(
            key=f"current_consumption_{phase.lower()}",
            translation_key="current_consumption_phase",
            translation_placeholders={"phase": phase},
            value_fn=_register(f"1-0:{offset + 1}.7.0"),
            **POWER,
        )
        for phase, offset in PHASES.items()
    ),
    *(
        LoomySensorEntityDescription(
            key=f"current_injection_{phase.lower()}",
            translation_key="current_injection_phase",
            translation_placeholders={"phase": phase},
            value_fn=_register(f"1-0:{offset + 2}.7.0"),
            **POWER,
        )
        for phase, offset in PHASES.items()
    ),
    *(
        LoomySensorEntityDescription(
            key=f"voltage_{phase.lower()}",
            translation_key="voltage",
            translation_placeholders={"phase": phase},
            device_class=SensorDeviceClass.VOLTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            value_fn=_register(f"1-0:{offset + 12}.7.0"),
        )
        for phase, offset in PHASES.items()
    ),
    *(
        LoomySensorEntityDescription(
            key=f"current_{phase.lower()}",
            translation_key="current",
            translation_placeholders={"phase": phase},
            device_class=SensorDeviceClass.CURRENT,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            value_fn=_register(f"1-0:{offset + 11}.7.0"),
        )
        for phase, offset in PHASES.items()
    ),
    LoomySensorEntityDescription(
        key="grid_configuration",
        translation_key="grid_configuration",
        device_class=SensorDeviceClass.ENUM,
        options=list(GRID_CONFIGURATIONS.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_enum(_register("1-0:94.32.1"), GRID_CONFIGURATIONS),
    ),
    LoomySensorEntityDescription(
        key="meter_time",
        translation_key="meter_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_timestamp(_register("0-0:1.0.0")),
    ),
    LoomySensorEntityDescription(
        key="text_message",
        translation_key="text_message",
        value_fn=_text(_register("0-0:96.13.0")),
    ),
    LoomySensorEntityDescription(
        key="equipment_id",
        translation_key="equipment_id",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_text(_register("0-0:96.1.1")),
    ),
    LoomySensorEntityDescription(
        key="ean",
        translation_key="ean",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_ean(_register("0-0:96.1.2")),
    ),
    LoomySensorEntityDescription(
        key="tariff",
        translation_key="tariff",
        device_class=SensorDeviceClass.ENUM,
        options=list(TARIFFS.values()),
        value_fn=_enum(_register("0-0:96.14.0"), TARIFFS),
    ),
    LoomySensorEntityDescription(
        key="breaker_state",
        translation_key="breaker_state",
        device_class=SensorDeviceClass.ENUM,
        options=list(SWITCH_STATES.values()),
        value_fn=_enum(_register("0-0:96.3.10"), SWITCH_STATES),
    ),
    *(
        LoomySensorEntityDescription(
            key=f"virtual_relay_{relay}",
            translation_key="virtual_relay",
            translation_placeholders={"relay": str(relay)},
            device_class=SensorDeviceClass.ENUM,
            options=list(SWITCH_STATES.values()),
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=_enum(_register(f"0-{relay}:96.3.10"), SWITCH_STATES),
        )
        for relay in range(1, 5)
    ),
    # 99.999 kW and 999.99 A mean the limiter or fuse supervision is deactivated.
    LoomySensorEntityDescription(
        key="limiter_threshold",
        translation_key="limiter_threshold",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=_register("0-0:17.0.0"),
    ),
    LoomySensorEntityDescription(
        key="fuse_threshold",
        translation_key="fuse_threshold",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value_fn=_register("1-0:31.4.0"),
    ),
    LoomySensorEntityDescription(
        key="gas",
        translation_key="gas",
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        value_fn=_mbus(MBUS_DEVICE_TYPE_GAS, "24.2.3"),
    ),
    LoomySensorEntityDescription(
        key="gas_valve",
        translation_key="gas_valve",
        device_class=SensorDeviceClass.ENUM,
        options=list(SWITCH_STATES.values()),
        value_fn=_enum(_mbus(MBUS_DEVICE_TYPE_GAS, "24.4.0"), SWITCH_STATES),
    ),
    *(
        LoomySensorEntityDescription(
            key=f"{meter}_{key}",
            translation_key=f"{meter}_{key}",
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=decode(_mbus(device_type, obis)),
        )
        for meter, device_type in (
            ("gas", MBUS_DEVICE_TYPE_GAS),
            ("water", MBUS_DEVICE_TYPE_WATER),
        )
        for key, obis, decode in (
            ("equipment_id", "96.1.1", _text),
            ("ean", "96.1.2", _ean),
        )
    ),
    LoomySensorEntityDescription(
        key="water",
        translation_key="water",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        value_fn=_mbus(MBUS_DEVICE_TYPE_WATER, "24.2.1"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LoomyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Loomy sensors that are present in the telegram."""
    coordinator = entry.runtime_data
    async_add_entities(
        LoomySensor(coordinator, description)
        for description in SENSORS
        if description.value_fn(coordinator.data) is not None
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
        # The meter publishes 3 decimals, show them all instead of HA's default.
        if description.native_unit_of_measurement is not None:
            self._attr_suggested_display_precision = 3
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Loomy",
            manufacturer="Loomy",
            model="Dongle",
        )

    @property
    def available(self) -> bool:
        """Return False when the register is missing from the telegram."""
        return super().available and self.native_value is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the extra attributes, like the peak history."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)

    @property
    def native_value(self) -> P1Value:
        """Return the sensor value, or None when it is garbage."""
        value = self.entity_description.value_fn(self.coordinator.data)
        # Sensors with a unit are numeric, anything but a number is garbage.
        if self.entity_description.native_unit_of_measurement is not None and (
            not isinstance(value, float)
        ):
            return None
        return value
