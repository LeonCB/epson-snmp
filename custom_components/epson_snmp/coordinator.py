"""DataUpdateCoordinator voor de Epson SNMP-integratie.

Pollt periodiek alle OID's uit het actieve profiel in één SNMP GET en levert
de ruwe waarden (als strings) aan de sensor-entities.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import PROFILE_AUTO
from .profile_loader import load_profile, resolve_profile_id_auto
from .profile_parser import ParsedProfile
from .snmp import SnmpError, async_snmp_get

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
        self.host = host
        self._community = community
        self._mp_model = mp_model
        self._profile_id = profile_id
        self.profile: ParsedProfile | None = None

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

        return {key: by_oid.get(oid) for key, oid in self.profile.oids.items()}
