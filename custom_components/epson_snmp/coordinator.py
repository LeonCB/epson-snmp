from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
)
from pysnmp.smi import view

from .const import PROFILE_AUTO
from .profile_loader import load_profile, resolve_profile_id_auto


_LOGGER = logging.getLogger(__name__)


def _create_snmp_engine() -> SnmpEngine:
    """Maak een SnmpEngine en laad de MIB's meteen van schijf.

    pysnmp laadt MIB-modules (zoals SNMPv2-MIB) lazy bij de eerste
    get_cmd()-aanroep met blokkerende os.listdir()/open()-calls. Als dat
    binnen de coroutine gebeurt, blokkeert het Home Assistant's event
    loop ("Detected blocking call to listdir/open"). Door de MIB's hier
    alvast in te laden - deze functie wordt altijd via
    hass.async_add_executor_job aangeroepen - gebeurt die schijf-I/O in
    een aparte thread, net zoals HA's eigen snmp-integratie het doet
    (zie home-assistant/core PR #118521).
    """
    engine = SnmpEngine()
    mib_view_controller = view.MibViewController(
        engine.message_dispatcher.mib_instrum_controller.get_mib_builder()
    )
    engine.cache["mibViewController"] = mib_view_controller
    mib_view_controller.mibBuilder.load_modules()
    return engine


class EpsonSnmpCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coördineert periodieke SNMP-polling en levert de laatste waarden aan entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        host: str,
        community: str,
        mp_model: int,
        scan_interval_seconds: int,
        name: str,
        profile_id: str = PROFILE_AUTO,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{name} Coordinator",
            update_interval=timedelta(seconds=scan_interval_seconds),
        )
        self._host = host
        self._community = community
        self._mp_model = mp_model
        self._profile_id = profile_id
        self._profile = None  # ParsedProfile, lazy geladen
        self._engine = None  # SnmpEngine, lazy aangemaakt (blokkerende call, dus buiten de event loop)

    async def async_get_profile(self):
        """
        Publieke accessor voor het actieve ParsedProfile.

        Hiermee hoeven platforms niet rechtstreeks aan coordinator-internals
        (_ensure_profile/_profile) te komen, terwijl het gedrag gelijk blijft.
        """
        await self._ensure_profile()
        return self._profile

    async def _snmp_get_batch(self, oids: list[str]) -> list[Any]:
        if self._engine is None:
            self._engine = await self.hass.async_add_executor_job(_create_snmp_engine)

        target = await UdpTransportTarget.create((self._host, 161), timeout=2, retries=1)

        err_ind, err_stat, _, var_binds = await get_cmd(
            self._engine,
            CommunityData(self._community, mpModel=self._mp_model),
            target,
            ContextData(),
            *[ObjectType(ObjectIdentity(oid)) for oid in oids],
            lookupMib=False,
        )
        if err_ind or err_stat:
            raise UpdateFailed(str(err_ind or err_stat))

        return [v for _, v in var_binds]

    async def _ensure_profile(self) -> None:
        if self._profile:
            return

        pid = self._profile_id
        if pid == PROFILE_AUTO:
            pid = await resolve_profile_id_auto(
                self.hass,
                host=self._host,
                community=self._community,
                mp_model=self._mp_model,
            )

        self._profile = await load_profile(self.hass, pid)

    async def _async_update_data(self) -> dict[str, Any]:
        await self._ensure_profile()

        if not self._profile.oids:
            raise UpdateFailed("Profiel heeft geen sources/OID's gedefinieerd")

        data: dict[str, Any] = {}

        keys = list(self._profile.oids.keys())
        oids = list(self._profile.oids.values())
        values = await self._snmp_get_batch(oids)

        for k, v in zip(keys, values):
            data[k] = str(v)

        if not data.get("firmware"):
            fw = data.get("firmware_code_raw")
            if fw:
                data["firmware"] = fw

        return data