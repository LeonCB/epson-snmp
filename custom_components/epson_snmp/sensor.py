"""Sensor-platform voor de Epson SNMP-integratie.

Elke sensor komt uit het actieve YAML-profiel (zie profiles/*.yaml).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EpsonSnmpConfigEntry
from .const import CONF_NAME, DOMAIN
from .coordinator import EpsonSnmpCoordinator
from .profile_parser import SensorDef


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EpsonSnmpConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    assert coordinator.profile is not None
    name: str = entry.data[CONF_NAME]
    data = coordinator.data or {}
    async_add_entities(
        EpsonYamlSensor(coordinator, name=name, sensor_def=s)
        for s in coordinator.profile.sensors
        # Een optionele sensor die deze printer niet levert, blijft weg
        # i.p.v. permanent "onbekend" te zijn.
        if not s.optional or data.get(s.source) is not None
    )


class EpsonYamlSensor(CoordinatorEntity[EpsonSnmpCoordinator], SensorEntity):
    """Sensor die zijn waarde en eigenschappen uit een profiel-definitie haalt."""

    def __init__(
        self,
        coordinator: EpsonSnmpCoordinator,
        *,
        name: str,
        sensor_def: SensorDef,
    ) -> None:
        super().__init__(coordinator)
        host = coordinator.host
        data = coordinator.data or {}
        self._def = sensor_def
        self._attr_name = f"{name} {sensor_def.name_suffix}"
        self._attr_unique_id = f"{DOMAIN}_{host}_{sensor_def.key}"
        self._attr_icon = sensor_def.icon
        self._attr_native_unit_of_measurement = sensor_def.unit
        self._attr_device_class = sensor_def.device_class
        self._attr_state_class = sensor_def.state_class
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name=name,
            manufacturer="Epson",
            model=data.get("model"),
            serial_number=data.get("serial"),
            sw_version=data.get("firmware") or data.get("firmware_code_raw"),
        )

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data or {}
        kind = self._def.kind

        # ratio_percent leest twee eigen bronwaarden (numerator/denominator)
        # in plaats van het gebruikelijke "source"-veld.
        if kind == "ratio_percent":
            return self._ratio_percent_value(data)

        raw = data.get(self._def.source)
        if raw is None:
            return self._def.default

        try:
            if kind == "int":
                return int(raw)
            if kind == "timeticks_seconds":
                return int(raw) // 100
        except (TypeError, ValueError):
            return None

        if kind == "mapped_int":
            return (self._def.map or {}).get(str(raw), self._def.default)

        return raw

    def _ratio_percent_value(self, data: dict[str, Any]) -> Any:
        """Bereken een percentage uit de numerator/denominator-bronwaarden van het profiel."""
        try:
            numerator = float(data[self._def.numerator])
            denominator = float(data[self._def.denominator])
        except (KeyError, TypeError, ValueError):
            return self._def.default

        if denominator == 0:
            return self._def.default

        return round(numerator / denominator * 100)
