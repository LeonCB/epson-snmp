from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_COMMUNITY,
    CONF_HOST,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_VERSION,
    DOMAIN,
    PROFILE_AUTO,
)
from .coordinator import EpsonSnmpCoordinator

"""
Epson SNMP integratie – entrypoints voor Home Assistant.

Deze module regelt de levenscyclus van de config entry:
- async_setup_entry: initialiseert de coordinator en zet de platforms op.
- async_unload_entry: haalt platforms weg en verwijdert de coordinator.

Er mag geen netwerk-I/O rechtstreeks in de event loop draaien; de coordinator
handelt SNMP-polling veilig af buiten de loop.
"""

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[str] = ["sensor"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Opzetten via YAML (wordt niet gebruikt; alleen voor HA-compatibiliteit)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Zet Epson SNMP op vanuit een config entry."""
    host: str = entry.data[CONF_HOST]
    name: str = entry.data[CONF_NAME]
    community: str = entry.data[CONF_COMMUNITY]
    version: str = str(entry.data[CONF_VERSION]).lower()
    scan_seconds: int = int(entry.data[CONF_SCAN_INTERVAL])
    profile_id: str = PROFILE_AUTO  # profielkeuze niet configureerbaar; altijd auto-detectie

    # pysnmp mpModel: 0=v1, 1=v2c
    mp_model = 0 if version in ("1", "v1") else 1

    coordinator = EpsonSnmpCoordinator(
        hass,
        host=host,
        community=community,
        mp_model=mp_model,
        scan_interval_seconds=scan_seconds,
        name=name,
        profile_id=profile_id,
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        # HA verwacht ConfigEntryNotReady voordat de platforms worden doorgezet
        raise ConfigEntryNotReady(str(err)) from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Verwijder een config entry en ruim de coordinator op."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

    return unload_ok