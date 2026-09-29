"""Profielen laden en auto-detectie voor de Epson SNMP-integratie.

Deze module:
- Somt beschikbare profiel-id's op (ingebouwd en gebruikersoverrides).
- Laadt en parseert YAML-profielen naar een genormaliseerde Python-structuur.
- Implementeert de "auto"-profielselectie via een probe + scoring-mechanisme.

Alle probe-OID's van alle kandidaat-profielen worden in één SNMP GET
opgehaald via de gedeelde engine (zie snmp.py).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util.yaml import load_yaml

from .const import DOMAIN, PROFILE_AUTO, PROFILE_GENERIC
from .profile_parser import ParsedProfile, parse_profile
from .snmp import async_snmp_get

_LOGGER = logging.getLogger(__name__)


def _match(op: str | None, actual: Any, expected: Any) -> bool:
    """Evalueer een voorwaarde van een detectieregel."""
    if actual is None:
        return False
    a = str(actual)
    e = str(expected)
    if op == "equals":
        return a == e
    if op == "contains_ci":
        return e.lower() in a.lower()
    if op == "exists":
        return True
    return False


def _embedded_dir() -> Path:
    """Map met de ingebouwde profielen van de integratie."""
    return Path(__file__).parent / "profiles"


def _override_dir(hass: HomeAssistant) -> Path:
    """Map waarin gebruikers profielen in /config kunnen overschrijven."""
    return Path(hass.config.path(DOMAIN, "profiles"))


def _read_profiles(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    """Lees alle profielen van schijf (blokkerend; draait in executor).

    Overrides in /config/epson_snmp/profiles/ winnen van ingebouwde profielen
    met dezelfde bestandsnaam.
    """
    raw: dict[str, dict[str, Any]] = {}
    for directory in (_embedded_dir(), _override_dir(hass)):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.yaml")):
            try:
                raw[path.stem] = load_yaml(str(path)) or {}
            except Exception as err:  # noqa: BLE001 - kapot profiel mag de rest niet breken
                _LOGGER.warning("Profiel %s kon niet worden gelezen: %s", path, err)
    raw.pop(PROFILE_AUTO, None)
    return raw


async def async_load_profiles(hass: HomeAssistant) -> dict[str, ParsedProfile]:
    """Laad en parseer alle beschikbare profielen, geïndexeerd op bestandsnaam."""
    raw = await hass.async_add_executor_job(_read_profiles, hass)
    profiles: dict[str, ParsedProfile] = {}
    for pid, data in raw.items():
        try:
            profiles[pid] = parse_profile(data)
        except (ValueError, KeyError, TypeError) as err:
            _LOGGER.warning("Profiel '%s' is ongeldig en wordt overgeslagen: %s", pid, err)
    return profiles


async def load_profile(hass: HomeAssistant, profile_id: str) -> ParsedProfile:
    """Laad één profiel op id (override in /config gaat voor)."""
    profiles = await async_load_profiles(hass)
    if profile_id not in profiles:
        raise ValueError(f"Profiel niet gevonden: {profile_id}")
    return profiles[profile_id]


def _score(profile: ParsedProfile, values: dict[str, str | None]) -> int | None:
    """Bereken de score van een profiel; None als een verplichte regel faalt."""
    scoring = (profile.detection or {}).get("scoring") or {}
    score = 0
    for rule in scoring.get("rules") or []:
        when = rule.get("when") or {}
        if _match(when.get("op"), values.get(when.get("key")), when.get("value")):
            score += int(rule.get("score") or 0)
        elif rule.get("required"):
            return None
    return score


async def resolve_profile_id_auto(
    hass: HomeAssistant,
    *,
    host: str,
    community: str,
    mp_model: int,
) -> str:
    """Kies het best passende profiel voor een apparaat via probe- en scoringregels.

    Raises SnmpError als het apparaat niet antwoordt, zodat Home Assistant de
    setup later opnieuw probeert in plaats van stilletjes op het generieke
    profiel terug te vallen.
    """
    candidates = {
        pid: p for pid, p in (await async_load_profiles(hass)).items() if p.detection
    }

    # Alle probe-OID's van alle kandidaten in één GET.
    probe_oids: list[str] = []
    for prof in candidates.values():
        for probe in prof.detection.get("probe") or []:
            if probe.get("oid") and str(probe["oid"]) not in probe_oids:
                probe_oids.append(str(probe["oid"]))

    by_oid = await async_snmp_get(
        hass, host=host, community=community, mp_model=mp_model, oids=probe_oids
    )

    best_id, best_score = PROFILE_GENERIC, 0
    for pid, prof in candidates.items():
        values = {
            p["key"]: by_oid.get(str(p["oid"]))
            for p in prof.detection.get("probe") or []
            if p.get("key") and p.get("oid")
        }
        score = _score(prof, values)
        threshold = int(((prof.detection.get("scoring") or {}).get("threshold")) or 0)
        _LOGGER.debug("Profiel '%s' scoort %s (drempel %s)", pid, score, threshold)
        if score is not None and score >= threshold and score > best_score:
            best_id, best_score = pid, score

    return best_id
