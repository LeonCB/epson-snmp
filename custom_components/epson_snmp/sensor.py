from __future__ import annotations

"""
Sensor-platform voor de Epson SNMP-integratie
(totaal aantal afgedrukte pagina's).

- EpsonYamlSensor: sensors gedefinieerd door het actieve YAML-profiel.
- EpsonYamlSupplySensor: supply-sensors gevonden via SNMP (inkt/toner).

Supply-entities worden aangemaakt:
1) Meteen vanuit coordinator.data (beschikbaar na first_refresh),
2) En later via een coordinator-listener als er nieuwe supply-indexen bijkomen.
"""

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_HOST, CONF_NAME
from .coordinator import EpsonSnmpCoordinator


_RUNTIME_KEY = f"{DOMAIN}_runtime"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    host: str = entry.data[CONF_HOST]
    name: str = entry.data[CONF_NAME]

    coordinator: EpsonSnmpCoordinator = hass.data[DOMAIN][entry.entry_id]
    profile = await coordinator.async_get_profile()

    # 1) Sensors zoals gedefinieerd in het profiel
    entities: list[SensorEntity] = [
        EpsonYamlSensor(coordinator, host=host, name=name, sensor_def=s) for s in profile.sensors
    ]
    async_add_entities(entities, update_before_add=False)

    # Runtime-state (niet mengen met de coordinators in hass.data[DOMAIN])
    runtime = hass.data.setdefault(_RUNTIME_KEY, {})
    state = runtime.setdefault(
        entry.entry_id, {"supplies_added": set(), "unsub": None})
    supplies_added: set[int] = state["supplies_added"]

    def _add_supplies_from_data() -> None:
        """Voeg nieuw gevonden supply-entities toe (idempotent)."""
        supplies = (coordinator.data or {}).get("supplies") or []
        if not supplies:
            return

        new_entities: list[SensorEntity] = []
        for sup in supplies:
            idx = sup.get("index")
            if not isinstance(idx, int):
                continue
            if idx in supplies_added:
                continue

            supplies_added.add(idx)
            new_entities.append(
                EpsonYamlSupplySensor(
                    coordinator, host=host, name=name, supply=sup)
            )

        if new_entities:
            async_add_entities(new_entities, update_before_add=False)

    # 2) Supplies meteen aanmaken (werkt omdat first_refresh al is geweest)
    _add_supplies_from_data()

    # 3) Listener aanhouden voor latere updates (robuust als supplies later verschijnen)
    unsub = coordinator.async_add_listener(_add_supplies_from_data)
    state["unsub"] = unsub


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


class EpsonYamlSupplySensor(EpsonBaseEntity, SensorEntity):
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = None

    def __init__(
        self,
        coordinator: EpsonSnmpCoordinator,
        *,
        host: str,
        name: str,
        supply: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, host=host, name=name)
        self._idx = supply["index"]
        title = supply.get("color") or supply.get(
            "desc") or f"Supply {self._idx}"
        self._attr_name = f"{name} Ink {title}"
        self._attr_unique_id = f"{DOMAIN}_{host}_supply_{self._idx}"

    @property
    def native_value(self) -> Any:
        supplies = (self.coordinator.data or {}).get("supplies") or []
        cur = next((s for s in supplies if s.get("index") == self._idx), None)
        if not cur:
            return None

        level = cur.get("level")
        maxv = cur.get("max")
        if level is None or maxv is None:
            return None

        try:
            level_i = int(level)
            max_i = int(maxv)
        except Exception:
            return None

        # Printer-MIB: negatieve waarden (bijv. -2) betekenen "onbekend / niet beschikbaar"
        if level_i < 0 or max_i <= 0:
            return None

        return int(round((level_i / max_i) * 100))
