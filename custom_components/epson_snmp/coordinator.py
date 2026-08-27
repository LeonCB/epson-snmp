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

from .const import PROFILE_AUTO
from .profile_loader import load_profile, resolve_profile_id_auto


_LOGGER = logging.getLogger(__name__)


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
            self._engine = await self.hass.async_add_executor_job(SnmpEngine)

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

        supplies_cfg = self._profile.supplies or {}
        if supplies_cfg.get("enabled"):
            out = []
            probe = supplies_cfg.get("probe") or {}
            level = supplies_cfg.get("level") or {}

            index_prefix = supplies_cfg.get("index_prefix")
            if index_prefix is None:
                index_prefix = probe.get(
                    "index_prefix") or level.get("index_prefix")

            def _idx_oid(base: str, idx: int) -> str:
                """Bouw een geïndexeerde OID, met optionele dubbele index."""
                if index_prefix is None:
                    return f"{base}.{idx}"
                return f"{base}.{index_prefix}.{idx}"

            has_color = "color_oid" in probe
            has_level = "value_oid" in level and "max_oid" in level

            for i in range(1, 9):
                index_oids = [_idx_oid(probe["desc_oid"], i)]
                if has_color:
                    index_oids.append(_idx_oid(probe["color_oid"], i))
                if has_level:
                    index_oids.append(_idx_oid(level["value_oid"], i))
                    index_oids.append(_idx_oid(level["max_oid"], i))

                try:
                    results = await self._snmp_get_batch(index_oids)
                except Exception:
                    break

                desc = results[0]
                if not desc:
                    break

                entry = {
                    "index": i,
                    "desc": str(desc),
                    "color": None,
                    "level": None,
                    "max": None,
                }

                pos = 1
                if has_color:
                    entry["color"] = str(results[pos])
                    pos += 1
                if has_level:
                    entry["level"] = str(results[pos])
                    entry["max"] = str(results[pos + 1])

                out.append(entry)

            data["supplies"] = out

        return data