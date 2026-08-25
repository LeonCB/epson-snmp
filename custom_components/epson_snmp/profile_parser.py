from __future__ import annotations

"""
YAML-profielen parsen voor de Epson SNMP-integratie
(totaal aantal afgedrukte pagina's).

Deze module definieert de in-memory representatie van een profiel en zet
ruwe YAML-dictionaries om naar sterk getypeerde dataclasses.

Ondersteunde YAML-schema's (achterwaarts compatibel):
- Legacy:  oids: {key: "1.3.6...."}
- Huidig:  sources: {key: {oid: "1.3.6....", kind: "..."}}

Alleen de OID-string is nodig tijdens het pollen; extra metadata wordt
bewaard voor toekomstige uitbreidingen, terwijl de parser strikt en
voorspelbaar blijft.
"""

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass


_DEVICE_CLASS = {
    "duration": SensorDeviceClass.DURATION,
}

_STATE_CLASS = {
    "measurement": SensorStateClass.MEASUREMENT,
    "total_increasing": SensorStateClass.TOTAL_INCREASING,
}

_ALLOWED_KINDS = {
    "int",
    "str",
    "timeticks_seconds",
    "mapped_int",
    "ratio_percent",
}


@dataclass(frozen=True)
class ProfileMeta:
    """Profielmetadata, gebruikt voor identificatie en UI-labels."""
    id: str
    name: str
    priority: int
    match_model: list[str]


@dataclass(frozen=True)
class SensorDef:
    """Definitie van een sensor-entity die vanuit een YAML-profiel wordt aangemaakt."""
    key: str
    name_suffix: str
    kind: str
    source: str | None = None           # sleutel in oids/sources
    # letterlijke OID-override (snelle uitzondering)
    oid: str | None = None
    icon: str | None = None
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    map: dict[str, str] | None = None
    default: str | None = None
    numerator: str | None = None        # sleutel in oids (verhouding)
    denominator: str | None = None      # sleutel in oids (verhouding)


@dataclass(frozen=True)
class ParsedProfile:
    """Volledig geparseerd profiel, gebruikt door de coordinator en platforms."""
    meta: ProfileMeta
    oids: dict[str, str]
    sensors: list[SensorDef]
    detection: dict[str, Any] | None
    supplies: dict[str, Any] | None


def _resolve_oid_value(v: Any) -> str:
    """Normaliseer een ruwe YAML-waarde naar een schone OID-string."""
    return str(v).strip()


def parse_profile(raw: dict[str, Any]) -> ParsedProfile:
    """
    Parseer een ruwe YAML-dict naar een ParsedProfile.

    Verwachte top-level sleutels:
    - profile: {id, name?, priority?, match_model?}
    - oids of sources: mapping met OID-strings
    - sensors: lijst met entity-mappings
    - detection: optionele auto-detectiesectie
    - supplies: optionele supplies-sectie (inkt/toner-probes)

    Raises:
        ValueError: als verplichte velden ontbreken of ongeldig zijn.
    """
    p = raw.get("profile") or {}
    pid = str(p.get("id") or "").strip()
    if not pid:
        raise ValueError("profile.id is verplicht")

    name = str(p.get("name") or pid).strip()
    priority = int(p.get("priority") or 0)

    match_model = p.get("match_model") or []
    match_model = [str(x) for x in match_model]

    # Achterwaartse compatibiliteit: accepteer zowel legacy "oids" als huidige "sources"
    oids_raw = raw.get("oids") or raw.get("sources") or {}
    oids: dict[str, str] = {}

    for k, v in oids_raw.items():
        if isinstance(v, dict):
            # huidig schema: sources: {key: {oid: "...", kind: "..."}}
            oid_val = str(v.get("oid") or "").strip()
            if oid_val:
                oids[str(k)] = oid_val
        else:
            # legacy schema: oids: {key: "1.3...."}
            oid_val = _resolve_oid_value(v)
            if oid_val:
                oids[str(k)] = oid_val

    sensors_raw = raw.get("sensors") or []
    sensors: list[SensorDef] = []

    for s in sensors_raw:
        kind = str(s.get("kind") or "").strip()
        if kind not in _ALLOWED_KINDS:
            raise ValueError(f"Ongeldige kind: {kind}")

        dc = s.get("device_class")
        sc = s.get("state_class")

        sensors.append(
            SensorDef(
                key=str(s["key"]),
                name_suffix=str(s["name_suffix"]),
                kind=kind,
                source=s.get("source") or s.get("source_key"),
                oid=s.get("oid"),
                icon=s.get("icon"),
                unit=s.get("unit"),
                device_class=_DEVICE_CLASS.get(dc) if dc else None,
                state_class=_STATE_CLASS.get(sc) if sc else None,
                map=s.get("map"),
                default=s.get("default"),
                numerator=s.get("numerator"),
                denominator=s.get("denominator"),
            )
        )

    detection = raw.get("detection")
    supplies = raw.get("supplies")

    return ParsedProfile(
        meta=ProfileMeta(
            id=pid,
            name=name,
            priority=priority,
            match_model=match_model,
        ),
        oids=oids,
        sensors=sensors,
        detection=detection,
        supplies=supplies,
    )
