# Epson – Totaal Aantal Afgedrukte Pagina's (Home Assistant Integratie)

![versie](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fapi.github.com%2Frepos%2FLeonCB%2Fepson-snmp%2Freleases%2Flatest&query=%24.tag_name&label=versie&color=blue)

Aangepaste Home Assistant-integratie om het **totaal aantal afgedrukte pagina's** van een Epson-printer bij te houden via SNMP.

---

## Functies

- Automatische detectie van Epson-netwerkprinters via SNMP (Printer-MIB)
- Totaal aantal afgedrukte pagina's (SNMP, Printer-MIB `prtMarkerLifeCount`).
- Afgedrukte pagina's in zwart-wit, kleur, 1-zijdig en 2-zijdig, van de webpagina van de printer (*Status → Verbruik status*). Deze sensoren verschijnen alleen als je printer die pagina heeft.
- Verbindingstest bij het instellen; werkt met SNMP v1 en v2c.

---

## Installatie

### HACS

1. HACS → ⋮ → *Aangepaste repositories* → `https://github.com/LeonCB/epson-snmp`, categorie *Integratie*
2. Installeer **Epson - Totaal aantal afgedrukte pagina's** en herstart Home Assistant
3. Voeg de integratie toe via *Instellingen → Apparaten & diensten*

### Handmatige installatie

1. Kopieer de map `epson_snmp` naar:
   ```
   /config/custom_components/
   ```
2. Herstart Home Assistant
3. Voeg de integratie toe via de UI

---

## Licentie

MIT License
