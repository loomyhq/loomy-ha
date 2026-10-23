"""Sensor platform for the Loomy integration."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import partial
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
from .p1 import GAS_METER, WATER_METER, P1Telegram, P1Value

type ValueFn = Callable[[P1Telegram], P1Value]


@dataclass(frozen=True, kw_only=True)
class LoomySensorEntityDescription(SensorEntityDescription):
    """Describes a Loomy sensor."""

    value_fn: ValueFn
    attributes_fn: Callable[[P1Telegram], dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        """Default the translation key to the key."""
        if self.translation_key is None:
            object.__setattr__(self, "translation_key", self.key)


def _register(obis: str) -> ValueFn:
    """Read a register from the telegram."""
    return lambda telegram: telegram.get(obis)


def _total(*obis: str) -> ValueFn:
    """Sum registers, for example the day and night tariff."""

    def value(telegram: P1Telegram) -> float | None:
        total = 0.0
        for code in obis:
            if not isinstance(term := telegram.get(code), float):
                return None
            total += term
        return round(total, 3)

    return value


def _mbus(device_type: str, obis: str) -> ValueFn:
    """Read a register from the submeter of the given type, on any channel."""

    def value(telegram: P1Telegram) -> P1Value:
        if (channel := telegram.mbus_channel(device_type)) is None:
            return None
        return telegram.get(f"0-{channel}:{obis}")

    return value


def _text(value_fn: ValueFn) -> ValueFn:
    """Decode a hex string, like an equipment ID, into text."""

    def value(telegram: P1Telegram) -> str | None:
        if not isinstance(raw := value_fn(telegram), str):
            return None
        try:
            text = bytes.fromhex(raw).decode()
        except ValueError:
            return None
        # A state is at most 255 characters, the text message up to 1024.
        return text[:255]

    return value


def _ean(value_fn: ValueFn) -> ValueFn:
    """Decode an EAN, the meter publishes dashes when it has not been set."""
    decode = _text(value_fn)

    def value(telegram: P1Telegram) -> str | None:
        if (ean := decode(telegram)) is not None and set(ean) == {"-"}:
            return "not set"
        return ean

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


def _quantity(
    device_class: SensorDeviceClass, unit: str, *, total: bool = False
) -> partial[LoomySensorEntityDescription]:
    """Describe a kind of measurement, momentary or a total that only increases.

    The meter publishes 3 decimals, show them all instead of HA's default.
    """
    return partial(
        LoomySensorEntityDescription,
        device_class=device_class,
        native_unit_of_measurement=unit,
        state_class=(
            SensorStateClass.TOTAL_INCREASING if total else SensorStateClass.MEASUREMENT
        ),
        suggested_display_precision=3,
    )


_energy = _quantity(SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR, total=True)
_power = _quantity(SensorDeviceClass.POWER, UnitOfPower.KILO_WATT)
_voltage = _quantity(SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT)
_current = _quantity(SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE)
_gas = _quantity(SensorDeviceClass.GAS, UnitOfVolume.CUBIC_METERS, total=True)
_water = _quantity(SensorDeviceClass.WATER, UnitOfVolume.CUBIC_METERS, total=True)
_diagnostic = partial(
    LoomySensorEntityDescription, entity_category=EntityCategory.DIAGNOSTIC
)


def _enum(
    *, key: str, value_fn: ValueFn, states: dict[str, str], **fields: Any
) -> LoomySensorEntityDescription:
    """An enum sensor, translating a raw value like 0001 into one of the states."""

    def value(telegram: P1Telegram) -> str | None:
        raw = value_fn(telegram)
        return states.get(raw) if isinstance(raw, str) else None

    return LoomySensorEntityDescription(
        key=key,
        device_class=SensorDeviceClass.ENUM,
        options=list(states.values()),
        value_fn=value,
        **fields,
    )


# Each phase has its own registers, 20 apart: L1 is 1-0:21.7.0, L2 1-0:41.7.0.
PHASES = {"L1": 0, "L2": 20, "L3": 40}
# The sensors per phase, with their L1 register and kind.
PHASE_SENSORS = (
    ("current_consumption", 21, _power),
    ("current_injection", 22, _power),
    ("voltage", 32, _voltage),
    ("current", 31, _current),
)

SENSORS: tuple[LoomySensorEntityDescription, ...] = (
    _energy(key="consumption", value_fn=_total("1-0:1.8.1", "1-0:1.8.2")),
    _energy(key="consumption_day", value_fn=_register("1-0:1.8.1")),
    _energy(key="consumption_night", value_fn=_register("1-0:1.8.2")),
    _energy(key="injection", value_fn=_total("1-0:2.8.1", "1-0:2.8.2")),
    _energy(key="injection_day", value_fn=_register("1-0:2.8.1")),
    _energy(key="injection_night", value_fn=_register("1-0:2.8.2")),
    _power(key="current_consumption", value_fn=_register("1-0:1.7.0")),
    _power(key="current_injection", value_fn=_register("1-0:2.7.0")),
    _power(key="average_demand", value_fn=_register("1-0:1.4.0")),
    _power(key="peak_demand", value_fn=_register("1-0:1.6.0")),
    _power(
        key="peak_demand_last_month",
        state_class=None,
        value_fn=_last_peak,
        attributes_fn=lambda telegram: {"history": _peak_history(telegram)},
    ),
    *(
        kind(
            key=f"{key}_{phase.lower()}",
            translation_key=f"{key}_phase",
            translation_placeholders={"phase": phase},
            value_fn=_register(f"1-0:{register + offset}.7.0"),
        )
        for key, register, kind in PHASE_SENSORS
        for phase, offset in PHASES.items()
    ),
    _enum(
        key="grid_configuration",
        states=GRID_CONFIGURATIONS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_register("1-0:94.32.1"),
    ),
    _diagnostic(
        key="meter_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_register("0-0:1.0.0"),
    ),
    LoomySensorEntityDescription(
        key="text_message", value_fn=_text(_register("0-0:96.13.0"))
    ),
    _diagnostic(key="equipment_id", value_fn=_text(_register("0-0:96.1.1"))),
    _diagnostic(key="ean", value_fn=_ean(_register("0-0:96.1.2"))),
    _enum(key="tariff", states=TARIFFS, value_fn=_register("0-0:96.14.0")),
    _enum(key="breaker_state", states=SWITCH_STATES, value_fn=_register("0-0:96.3.10")),
    *(
        _enum(
            key=f"virtual_relay_{relay}",
            translation_key="virtual_relay",
            translation_placeholders={"relay": str(relay)},
            states=SWITCH_STATES,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=_register(f"0-{relay}:96.3.10"),
        )
        for relay in range(1, 5)
    ),
    # 99.999 kW and 999.99 A mean the limiter or fuse supervision is deactivated.
    _power(
        key="limiter_threshold",
        state_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_register("0-0:17.0.0"),
    ),
    _current(
        key="fuse_threshold",
        state_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_register("1-0:31.4.0"),
    ),
    _gas(key="gas", value_fn=_mbus(GAS_METER, "24.2.3")),
    _enum(key="gas_valve", states=SWITCH_STATES, value_fn=_mbus(GAS_METER, "24.4.0")),
    _diagnostic(key="gas_equipment_id", value_fn=_text(_mbus(GAS_METER, "96.1.1"))),
    _diagnostic(key="gas_ean", value_fn=_ean(_mbus(GAS_METER, "96.1.2"))),
    _water(key="water", value_fn=_mbus(WATER_METER, "24.2.1")),
    _diagnostic(key="water_equipment_id", value_fn=_text(_mbus(WATER_METER, "96.1.1"))),
    _diagnostic(key="water_ean", value_fn=_ean(_mbus(WATER_METER, "96.1.2"))),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LoomyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Loomy sensors that are present in the telegram."""
    coordinator = entry.runtime_data
    sensors = (LoomySensor(coordinator, description) for description in SENSORS)
    async_add_entities(sensor for sensor in sensors if sensor.native_value is not None)


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
        description = self.entity_description
        value = description.value_fn(self.coordinator.data)
        # Sensors with a unit need a number and timestamps a datetime, the
        # meter is known to publish garbage for both.
        if description.native_unit_of_measurement is not None:
            return value if isinstance(value, float) else None
        if description.device_class == SensorDeviceClass.TIMESTAMP:
            return value if isinstance(value, datetime) else None
        return value
