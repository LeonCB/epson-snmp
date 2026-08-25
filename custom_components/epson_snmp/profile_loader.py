from __future__ import annotations

"""
Profielen laden en auto-detectie voor de Epson SNMP-integratie
(totaal aantal afgedrukte pagina's).

Deze module:
- Somt beschikbare profiel-id's op (ingebouwd en gebruikersoverrides).
- Laadt en parseert YAML-profielen naar een genormaliseerde Python-structuur.
- Implementeert de "auto"-profielselectie via een probe + scoring-mechanisme.

Alle SNMP-probes worden buiten Home Assistants event loop uitgevoerd door
het werk naar een executor-thread te delegeren, waar een eigen asyncio-loop
draait.
"""

import asyncio
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util.yaml import load_yaml
from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
)

from .const import DOMAIN, PROFILE_AUTO, PROFILE_GENERIC
from .profile_parser import ParsedProfile, parse_profile


def _match(op: str, actual: Any, expected: Any) -> bool:
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


def _run_coro_in_new_loop(coro: Any) -> Any:
    """Draai een coroutine in een nieuwe event loop (bedoeld voor executor-threads)."""
    return asyncio.run(coro)


async def _snmp_probe(
    hass: HomeAssistant,
    host: str,
    community: str,
    mp_model: int,
    probe: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Voer een eenmalige SNMP GET uit voor een set probe-OID's en geef een dict
    terug, geïndexeerd op de "key"-velden van de probe-items.

    Geeft een lege dict terug bij fouten/timeouts, zodat auto-detectie
    veerkrachtig blijft.
    """
    oids = [p["oid"] for p in probe]

    async def _async_do() -> list[Any]:
        target = await UdpTransportTarget.create((host, 161), timeout=2, retries=1)

        err_ind, err_stat, _, var_binds = await get_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=mp_model),
            target,
            ContextData(),
            *[ObjectType(ObjectIdentity(oid)) for oid in oids],
            lookupMib=False,
        )
        if err_ind or err_stat:
            return []
        return [v for _, v in var_binds]

    def _do_sync() -> list[Any]:
        return _run_coro_in_new_loop(_async_do())

    values = await hass.async_add_executor_job(_do_sync)
    if not values:
        return {}

    out: dict[str, Any] = {}
    for p, v in zip(probe, values):
        out[p["key"]] = str(v)
    return out


def _embedded_dir() -> Path:
    """Geef de map met de ingebouwde profielen van de integratie terug."""
    return Path(__file__).parent / "profiles"


def _override_dir(hass: HomeAssistant) -> Path:
    """Geef de map terug waarin gebruikers profielen in /config kunnen overschrijven."""
    return Path(hass.config.path(DOMAIN, "profiles"))


def list_profile_ids(hass: HomeAssistant) -> list[str]:
    """
    Somt de beschikbare profiel-id's op, zowel ingebouwd als overrides.

    Het speciale "auto"-profiel staat altijd vooraan.
    """
    ids = set()

    for p in _embedded_dir().glob("*.yaml"):
        ids.add(p.stem)

    od = _override_dir(hass)
    if od.exists():
        for p in od.glob("*.yaml"):
            ids.add(p.stem)

    out = sorted(ids, key=lambda s: s.lower())
    if PROFILE_AUTO in out:
        out.remove(PROFILE_AUTO)
    out.insert(0, PROFILE_AUTO)
    return out


async def _load_yaml_file(hass: HomeAssistant, path: Path) -> dict[str, Any]:
    """Laad YAML van schijf via een executor, om de event loop niet te blokkeren."""
    return await hass.async_add_executor_job(load_yaml, str(path)) or {}


async def load_profile(hass: HomeAssistant, profile_id: str) -> ParsedProfile:
    """
    Laad een profiel op basis van id en parseer het naar een genormaliseerde structuur.

    Volgorde bij overrides:
      1) /config/epson_snmp/profiles/<id>.yaml
      2) custom_components/epson_snmp/profiles/<id>.yaml
    """
    od = _override_dir(hass) / f"{profile_id}.yaml"
    if od.exists():
        return parse_profile(await _load_yaml_file(hass, od))

    ed = _embedded_dir() / f"{profile_id}.yaml"
    if ed.exists():
        return parse_profile(await _load_yaml_file(hass, ed))

    raise ValueError(f"Profiel niet gevonden: {profile_id}")


async def resolve_profile_id_auto(
    hass: HomeAssistant,
    *,
    host: str,
    community: str,
    mp_model: int,
) -> str:
    """
    Kies het best passende profiel voor een apparaat via probe- en scoringregels.

    - Evalueert alle profielen met een "detection"-sectie (behalve "auto").
    - Past "required"-regels strikt toe.
    - Valt terug op PROFILE_GENERIC als geen enkele kandidaat de drempel haalt.
    """
    candidates: list[ParsedProfile] = []
    for pid in list_profile_ids(hass):
        if pid == PROFILE_AUTO:
            continue
        try:
            prof = await load_profile(hass, pid)
        except Exception:
            continue
        if not prof.detection:
            continue
        candidates.append(prof)

    best_id = PROFILE_GENERIC
    best_score = 0

    for prof in candidates:
        det = prof.detection or {}
        probe = det.get("probe") or []
        scoring = det.get("scoring") or {}
        rules = scoring.get("rules") or []
        threshold = int(scoring.get("threshold") or 0)

        values = await _snmp_probe(
            hass,
            host=host,
            community=community,
            mp_model=mp_model,
            probe=probe,
        )
        if not values:
            continue

        score = 0
        failed_required = False

        for r in rules:
            when = r.get("when") or {}
            key = when.get("key")
            op = when.get("op")
            val = when.get("value")
            required = bool(r.get("required"))
            s = int(r.get("score") or 0)

            if _match(op, values.get(key), val):
                score += s
            elif required:
                failed_required = True
                break

        if failed_required:
            continue

        if score >= threshold and score > best_score:
            best_score = score
            best_id = prof.meta.id

    return best_id
