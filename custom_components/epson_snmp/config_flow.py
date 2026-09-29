"""Config flow voor de Epson SNMP-integratie.

De gebruiker geeft host, naam, community, SNMP-versie en scan-interval op.
Voordat de entry wordt aangemaakt, controleert de flow met één SNMP GET
(sysObjectID) of de printer bereikbaar is. Het profiel wordt altijd
automatisch gedetecteerd (zie profile_loader.py).
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

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
    MIN_SCAN_INTERVAL,
    OID_SYS_OBJECT_ID,
    SNMP_VERSIONS,
)
from .snmp import SnmpError, async_snmp_get, mp_model_for

_LOGGER = logging.getLogger(__name__)


class EpsonSnmpConfigFlow(ConfigFlow, domain=DOMAIN):
    """Regelt de config flow voor Epson SNMP."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Eerste stap waarin de gebruiker de verbindingsinstellingen opgeeft."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            try:
                result = await async_snmp_get(
                    self.hass,
                    host=host,
                    community=user_input[CONF_COMMUNITY],
                    mp_model=mp_model_for(user_input[CONF_VERSION]),
                    oids=[OID_SYS_OBJECT_ID],
                )
            except SnmpError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Onverwachte fout bij verbindingstest met %s", host)
                errors["base"] = "unknown"
            else:
                if result.get(OID_SYS_OBJECT_ID) is None:
                    errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={**user_input, CONF_HOST: host},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Optional(CONF_COMMUNITY, default=DEFAULT_COMMUNITY): str,
                vol.Optional(CONF_VERSION, default=DEFAULT_VERSION): vol.In(SNMP_VERSIONS),
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )
