"""Gedeelde SNMP-hulpfuncties voor de Epson SNMP-integratie.

Eén SnmpEngine per Home Assistant-instantie wordt gedeeld door de coordinator,
de auto-detectie en de config flow. Het aanmaken van de engine laadt MIB's van
schijf (blokkerend) en gebeurt daarom één keer in een executor-thread. Daarna
is pysnmp's asyncio-API volledig non-blocking en kan hij direct in de event
loop van Home Assistant draaien.
"""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.core import HomeAssistant
from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
)
from pysnmp.proto.rfc1905 import EndOfMibView, NoSuchInstance, NoSuchObject
from pysnmp.smi import view

from .const import DOMAIN

SNMP_PORT = 161
SNMP_TIMEOUT = 2
SNMP_RETRIES = 1

_ENGINE_KEY = f"{DOMAIN}_engine"
_ENGINE_LOCK_KEY = f"{DOMAIN}_engine_lock"

# SNMPv2c geeft deze waarden terug voor OID's die het apparaat niet kent.
_MISSING = (NoSuchObject, NoSuchInstance, EndOfMibView)


class SnmpError(Exception):
    """SNMP-request mislukt (timeout, verkeerde community, onbereikbaar)."""


def mp_model_for(version: str) -> int:
    """Vertaal een SNMP-versie ("1", "v1", "2c", ...) naar pysnmp's mpModel."""
    return 0 if str(version).lower() in ("1", "v1") else 1


def _create_engine() -> SnmpEngine:
    """Maak een SnmpEngine en laad de MIB's meteen (blokkerend, dus in executor).

    pysnmp laadt MIB-modules anders lazy bij de eerste get_cmd()-aanroep met
    blokkerende listdir()/open()-calls in de event loop. Dezelfde aanpak als
    HA's eigen snmp-integratie (home-assistant/core PR #118521).
    """
    engine = SnmpEngine()
    mib_view_controller = view.MibViewController(
        engine.message_dispatcher.mib_instrum_controller.get_mib_builder()
    )
    engine.cache["mibViewController"] = mib_view_controller
    mib_view_controller.mibBuilder.load_modules()
    return engine


async def async_get_engine(hass: HomeAssistant) -> SnmpEngine:
    """Geef de gedeelde SnmpEngine terug; maak hem de eerste keer aan."""
    if (engine := hass.data.get(_ENGINE_KEY)) is not None:
        return engine
    lock: asyncio.Lock = hass.data.setdefault(_ENGINE_LOCK_KEY, asyncio.Lock())
    async with lock:
        if (engine := hass.data.get(_ENGINE_KEY)) is None:
            engine = await hass.async_add_executor_job(_create_engine)
            hass.data[_ENGINE_KEY] = engine
    return engine


async def _get(
    engine: SnmpEngine,
    target: UdpTransportTarget,
    auth: CommunityData,
    oids: list[str],
) -> tuple[Any, Any, int, list[Any]]:
    return await get_cmd(
        engine,
        auth,
        target,
        ContextData(),
        *[ObjectType(ObjectIdentity(oid)) for oid in oids],
        lookupMib=False,
    )


async def async_snmp_get(
    hass: HomeAssistant,
    *,
    host: str,
    community: str,
    mp_model: int,
    oids: list[str],
) -> dict[str, str | None]:
    """Haal een reeks OID's op in één SNMP GET.

    Geeft {oid: waarde} terug; OID's die het apparaat niet ondersteunt krijgen
    None. Raises SnmpError als het apparaat helemaal niet antwoordt.
    """
    if not oids:
        return {}

    engine = await async_get_engine(hass)
    auth = CommunityData(community, mpModel=mp_model)
    try:
        target = await UdpTransportTarget.create(
            (host, SNMP_PORT), timeout=SNMP_TIMEOUT, retries=SNMP_RETRIES
        )
    except Exception as err:  # o.a. DNS-fouten
        raise SnmpError(f"Kan {host} niet resolven: {err}") from err

    err_ind, err_stat, err_idx, var_binds = await _get(engine, target, auth, oids)
    if err_ind:
        raise SnmpError(str(err_ind))

    if err_stat:
        # SNMPv1 laat het hele request mislukken als één OID onbekend is
        # (noSuchName). Vraag de OID's dan los op, zodat de rest wel werkt.
        if len(oids) == 1:
            return {oids[0]: None}
        out: dict[str, str | None] = {}
        for oid in oids:
            out.update(
                await async_snmp_get(
                    hass, host=host, community=community, mp_model=mp_model, oids=[oid]
                )
            )
        return out

    return {
        oid: (None if isinstance(value, _MISSING) else str(value))
        for oid, (_, value) in zip(oids, var_binds, strict=False)
    }
