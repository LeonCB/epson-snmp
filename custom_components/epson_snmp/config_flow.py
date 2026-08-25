from __future__ import annotations
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_COMMUNITY,
    CONF_HOST,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_VERSION,
    DEFAULT_COMMUNITY,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERSION,
    DOMAIN,
)

"""
Config flow voor de Epson SNMP-integratie (totaal aantal afgedrukte pagina's).

Deze module definieert de eerste opzet-stap voor de gebruiker (host, naam,
community, SNMP-versie, scan interval). Profielkeuze is niet instelbaar door
de gebruiker; de integratie detecteert het profiel altijd automatisch
(zie profile_loader.py).

Let op: connectiviteitscontrole is hier bewust minimaal gehouden om het
opzetten snel te houden en regressies te voorkomen. Of de integratie echt
klaar is, wordt afgehandeld door de eerste refresh van de coordinator.
"""


class EpsonSnmpConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Regelt de config flow voor Epson SNMP."""
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Eerste stap waarin de gebruiker de verbindingsinstellingen opgeeft."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()

            # Unieke ID op basis van host (kan later eventueel op serienummer worden gezet).
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input.get(CONF_NAME) or DEFAULT_NAME,
                data={
                    CONF_HOST: host,
                    CONF_NAME: user_input.get(CONF_NAME, DEFAULT_NAME),
                    CONF_COMMUNITY: user_input.get(CONF_COMMUNITY, DEFAULT_COMMUNITY),
                    CONF_VERSION: user_input.get(CONF_VERSION, DEFAULT_VERSION),
                    CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Optional(CONF_COMMUNITY, default=DEFAULT_COMMUNITY): str,
                vol.Optional(CONF_VERSION, default=DEFAULT_VERSION): str,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
