from __future__ import annotations

"""
Sensor-platform voor de Epson SNMP-integratie
(totaal aantal afgedrukte pagina's).

- EpsonYamlSensor: sensors gedefinieerd door het actieve YAML-profiel.
"""

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_HOST, CONF_NAME
from .coordinator import EpsonSnmpCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    host: str = entry.data[CONF_HOST]
    name: str = entry.data[CONF_NAME]

    coordinator: EpsonSnmpCoordinator = hass.data[DOMAIN][entry.entry_id]
    profile = await coordinator.async_get_profile()

    entities: list[SensorEntity] = [
        EpsonYamlSensor(coordinator, host=host, name=name, sensor_def=s) for s in profile.sensors
    ]
    async_add_entities(entities, update_before_add=False)


class EpsonBaseEntity(CoordinatorEntity[EpsonSnmpCoordinator]):
    def __init__(self, coordinator: EpsonSnmpCoordinator, *, host: str, name: str) -> None:
        super().__init__(coordinator)
        self._host = host
        self._name = name
        self._attr_device_info = self._device_info()

    def _device_info(self) -> DeviceInfo:
        data = self.coordinator.data or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self._host)},
            name=self._name,
            manufacturer="Epson",
            model=data.get("model"),
            serial_number=data.get("serial"),
            sw_version=data.get("firmware") or data.get("firmware_code_raw"),

        )


class EpsonYamlSensor(EpsonBaseEntity, SensorEntity):
    def __init__(
        self,
        coordinator: EpsonSnmpCoordinator,
        *,
        host: str,
        name: str,
        sensor_def: Any,
    ) -> None:
        super().__init__(coordinator, host=host, name=name)
        self._def = sensor_def
        self._attr_name = f"{name} {sensor_def.name_suffix}"
        self._attr_unique_id = f"{DOMAIN}_{host}_{sensor_def.key}"
        self._attr_icon = sensor_def.icon
        self._attr_native_unit_of_measurement = sensor_def.unit
        self._attr_device_class = sensor_def.device_class
        self._attr_state_class = sensor_def.state_class

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data or {}

        # ratio_percent leest twee eigen bronwaarden (numerator/denominator)
        # in plaats van het gebruikelijke "source"-veld, dus dit moet vóór
        # de generieke raw/source-check afgehandeld worden.
        if self._def.kind == "ratio_percent":
            return self._ratio_percent_value(data)

        raw = data.get(self._def.source)

        if raw is None:
            return self._def.default

        if self._def.kind == "int":
            try:
                return int(raw)
            except Exception:
                return None

        if self._def.kind == "timeticks_seconds":
            try:
                return int(raw) // 100
            except Exception:
                return None

        if self._def.kind == "mapped_int":
            return (self._def.map or {}).get(str(raw), self._def.default)

        return raw

    def _ratio_percent_value(self, data: dict[str, Any]) -> Any:
        """Bereken een percentage uit de numerator/denominator-bronwaarden van het profiel."""
        num_raw = data.get(self._def.numerator)
        den_raw = data.get(self._def.denominator)

        if num_raw is None or den_raw is None:
            return self._def.default

        try:
            numerator = float(num_raw)
            denominator = float(den_raw)
        except (TypeError, ValueError):
            return self._def.default

        if denominator == 0:
            return self._def.default

        return int(round((numerator / denominator) * 100))