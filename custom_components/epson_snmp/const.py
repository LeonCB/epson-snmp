"""
Constanten voor de Epson SNMP-integratie (totaal aantal afgedrukte pagina's).

Deze module bundelt:
- Domain en configuratiesleutels
- Standaardwaarden voor configuratie-opties
- Profiel-identifiers

Door deze definities hier te centraliseren voorkomen we duplicatie van
strings en blijft alles consistent tussen config flow, coordinator en
platforms.
"""

DOMAIN = "epson_snmp"

# Configuratiesleutels
CONF_HOST = "host"
CONF_NAME = "name"
CONF_COMMUNITY = "community"
CONF_VERSION = "version"
CONF_SCAN_INTERVAL = "scan_interval"

# Standaardwaarden
DEFAULT_NAME = "Epson Printer"
DEFAULT_COMMUNITY = "public"
DEFAULT_VERSION = "2c"
DEFAULT_SCAN_INTERVAL = 30

# Profiel-identifiers
PROFILE_AUTO = "auto"
PROFILE_GENERIC = "generic"
