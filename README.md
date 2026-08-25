# Epson – Totaal Aantal Afgedrukte Pagina's (Home Assistant Integratie)

Aangepaste Home Assistant-integratie om het **totaal aantal afgedrukte pagina's** van een Epson-printer bij te houden via SNMP.

Dit is een afgeslankte fork gericht op één enkele waarde: de teller van het totaal aantal pagina's sinds ingebruikname. Inktniveaus, uptime en overige Printer-MIB-gegevens worden bewust niet blootgesteld, omdat die informatie al via een andere integratie binnenkomt.

---

## ✨ Functies

- Automatische detectie van Epson-netwerkprinters via SNMP (Printer-MIB)
- Eén sensor: totaal aantal afgedrukte pagina's
- Apparaatinformatie (merk/type) zichtbaar op de Home Assistant-apparaatkaart
- Volledig native Home Assistant UI, geen YAML-bewerking nodig

---

## 📊 Beschikbare gegevens

### Totaal aantal afgedrukte pagina's

- **Totaal Aantal Afgedrukte Pagina's**
  Totaal aantal afgedrukte pagina's gedurende de levensduur van de printer (Printer-MIB `prtMarkerLifeCount`)

---

## ⚙️ Configuratie

Configuratie verloopt volledig via de Home Assistant-UI:

- Host van de printer
- Naam van het apparaat
- SNMP-community
- SNMP-versie
- Update-interval

Profieldetectie gebeurt altijd automatisch; er is geen apart optiesscherm.

---

## 🖨️ Ondersteunde printers

Alle Epson-netwerkprinters die SNMP (Printer-MIB) ondersteunen — de printer wordt automatisch gedetecteerd via Epson's SNMP-fabrikants-ID, dus een vaste lijst met modellen is niet nodig.

---

## 📦 Installatie

### Handmatige installatie

1. Kopieer de map `epson_snmp` naar:
   ```
   /config/custom_components/
   ```
2. Herstart Home Assistant
3. Voeg de integratie toe via de UI

---

## 📄 Licentie

MIT License
