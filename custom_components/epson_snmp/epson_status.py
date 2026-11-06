"""Decoder voor het Epson ST2-statusbericht.

Veel Epson-printers (waaronder de EcoTank-modellen) geven via een eigen
SNMP-OID het binaire "@BDC ST2"-statusbericht terug:

    1.3.6.1.4.1.1248.1.2.2.44.1.1.2.1.115.116.1.0.1   ("st", payload 0x01)

Opbouw: [00] "@BDC ST2\\r\\n" <lengte, 2 bytes little-endian> en daarna een
reeks velden <type, 1 byte> <lengte, 1 byte> <data>.

Veld 0x36 bevat de papiertellers: vijf 32-bits getallen (little-endian).
Gebaseerd op de documentatie van github.com/Ircama/epson_print_conf.
"""

from __future__ import annotations

_HEADER = b"BDC ST2\r\n"

FIELD_PAPER_COUNT = 0x36
_PAPER_COUNT_KEYS = ("normal", "page", "color", "monochrome", "blank")


def _to_bytes(raw: bytes | str | None) -> bytes | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return raw
    # Terugval: tekst die als latin-1 gedecodeerd is, is verliesloos terug te zetten.
    try:
        return raw.encode("latin-1")
    except UnicodeEncodeError:
        return None


def parse_fields(raw: bytes | str | None) -> dict[int, bytes]:
    """Splits een ST2-bericht in {veldtype: data}. Leeg bij een ongeldig bericht."""
    data = _to_bytes(raw)
    if not data:
        return {}
    start = data.find(_HEADER)
    if start < 0:
        return {}
    pos = start + len(_HEADER)
    if len(data) < pos + 2:
        return {}
    length = int.from_bytes(data[pos : pos + 2], "little")
    buf = data[pos + 2 : pos + 2 + length]

    fields: dict[int, bytes] = {}
    i = 0
    while i + 2 <= len(buf):
        ftype, flen = buf[i], buf[i + 1]
        item = buf[i + 2 : i + 2 + flen]
        if len(item) != flen:
            break  # afgekapt bericht: houd wat we al hebben
        fields[ftype] = item
        i += 2 + flen
    return fields


def parse_status(raw: bytes | str | None) -> dict[str, int]:
    """Geef de bekende waarden uit een ST2-bericht terug.

    Sleutels: paper_count_normal, paper_count_page, paper_count_color,
    paper_count_monochrome, paper_count_blank. Velden die de printer niet
    meestuurt ontbreken in het resultaat.
    """
    out: dict[str, int] = {}
    item = parse_fields(raw).get(FIELD_PAPER_COUNT)
    if item is not None and len(item) >= 4 * len(_PAPER_COUNT_KEYS):
        for n, key in enumerate(_PAPER_COUNT_KEYS):
            value = int.from_bytes(item[4 * n : 4 * n + 4], "little", signed=True)
            if value >= 0:
                out[f"paper_count_{key}"] = value
    return out
