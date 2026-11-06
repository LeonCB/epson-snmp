"""DataUpdateCoordinator voor de Epson SNMP-integratie.

Pollt periodiek alle OID's uit het actieve profiel in één SNMP GET en levert
de ruwe waarden (als strings) aan de sensor-entities.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import PROFILE_AUTO
from .profile_loader import load_profile, resolve_profile_id_auto
from .profile_parser import ParsedProfile
from .snmp import SnmpError, async_snmp_get
from .webconfig import WebConfigClient

_LOGGER = logging.getLogger(__name__)

# Paginatellers veranderen langzaam: de webpagina van de printer wordt veel
# minder vaak opgevraagd dan SNMP. Mislukt dat even, dan blijven de laatste
# waarden een tijd staan i.p.v. dat de sensoren direct "onbekend" worden.
WEB_INTERVAL = timedelta(minutes=5)
WEB_MAX_AGE = timedelta(minutes=30)


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
        self.host = host
        self._community = community
        self._mp_model = mp_model
        self._profile_id = profile_id
        self.profile: ParsedProfile | None = None
        self._web = WebConfigClient(hass, host)
        self._usage: dict[str, int] = {}
        self._usage_at: datetime | None = None

    async def _async_setup(self) -> None:
        """Bepaal het profiel één keer, vóór de eerste refresh."""
        pid = self._profile_id
        if pid == PROFILE_AUTO:
            try:
                pid = await resolve_profile_id_auto(
                    self.hass,
                    host=self.host,
                    community=self._community,
                    mp_model=self._mp_model,
                )
            except SnmpError as err:
                raise UpdateFailed(f"{self.host} antwoordt niet op SNMP: {err}") from err
        _LOGGER.debug("Profiel '%s' gekozen voor %s", pid, self.host)
        self.profile = await load_profile(self.hass, pid)

    async def _async_update_data(self) -> dict[str, Any]:
        if self.profile is None:  # HA < 2024.8 roept _async_setup niet zelf aan
            await self._async_setup()
        assert self.profile is not None

        if not self.profile.oids:
            raise UpdateFailed("Profiel heeft geen sources/OID's gedefinieerd")

        try:
            by_oid = await async_snmp_get(
                self.hass,
                host=self.host,
                community=self._community,
                mp_model=self._mp_model,
                oids=list(dict.fromkeys(self.profile.oids.values())),
            )
        except SnmpError as err:
            raise UpdateFailed(f"SNMP-fout bij {self.host}: {err}") from err

        data: dict[str, Any] = {key: by_oid.get(oid) for key, oid in self.profile.oids.items()}

        # Extra tellers van de webpagina van de printer. Mislukt dat, dan
        # blijven de SNMP-sensoren gewoon werken.
        if self.profile.web_sources:
            usage = await self._async_usage()
            for key in self.profile.web_sources:
                for field, value in usage.items():
                    data[f"{key}.{field}"] = value
        return data

    async def _async_usage(self) -> dict[str, int]:
        """Tellers van de webpagina: hoogstens elke WEB_INTERVAL opnieuw opgehaald."""
        now = dt_util.utcnow()
        if self._usage_at is None or now - self._usage_at >= WEB_INTERVAL:
            if (fresh := await self._web.async_fetch_usage()) is not None:
                self._usage, self._usage_at = fresh, now
        if self._usage_at is not None and now - self._usage_at > WEB_MAX_AGE:
            _LOGGER.debug("Paginatellers van %s zijn te oud, worden niet meer getoond", self.host)
            self._usage, self._usage_at = {}, None
        return self._usage
