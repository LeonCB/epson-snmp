"""Epson SNMP-integratie – entrypoints voor Home Assistant.

- async_setup_entry: maakt de coordinator aan, bepaalt het profiel, haalt de
  eerste data op en zet de platforms op.
- async_unload_entry: haalt de platforms weer weg.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_COMMUNITY,
    CONF_HOST,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_VERSION,
)
from .coordinator import EpsonSnmpCoordinator
from .snmp import mp_model_for

PLATFORMS: list[Platform] = [Platform.SENSOR]

EpsonSnmpConfigEntry = ConfigEntry[EpsonSnmpCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EpsonSnmpConfigEntry) -> bool:
    """Zet Epson SNMP op vanuit een config entry."""
    coordinator = EpsonSnmpCoordinator(
        hass,
        host=entry.data[CONF_HOST],
        community=entry.data[CONF_COMMUNITY],
        mp_model=mp_model_for(entry.data[CONF_VERSION]),
        scan_interval_seconds=int(entry.data[CONF_SCAN_INTERVAL]),
        name=entry.data[CONF_NAME],
    )

    # Raist zelf ConfigEntryNotReady als de printer (nog) niet antwoordt.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EpsonSnmpConfigEntry) -> bool:
    """Verwijder een config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
