"""Paginatellers uitlezen via de webpagina van de printer (Epson Web Config).

SNMP geeft alleen het totaal aantal pagina's. De Web Config-pagina
"Status > Verbruik status" toont daarnaast zwart-wit, kleur, 1-zijdig en
2-zijdig, en is zonder beheerderslogin te openen:

    https://<printer>/PRESENTATION/ADVANCED/INFO_MENTINFO/TOP

De pagina bestaat uit <dt class="key">label</dt><dd class="value">getal</dd>.
Met een taalcookie (dezelfde die Web Config's eigen taalkeuze zet) vragen we
de pagina in het Engels op. Negeert een printer die cookie, dan wordt op
trefwoorden in een paar talen gezocht en anders op volgorde (totaal,
zwart-wit, kleur, 2-zijdig, 1-zijdig), zoals Epson ze toont.
"""

from __future__ import annotations

import logging
from html.parser import HTMLParser

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

_LOGGER = logging.getLogger(__name__)

USAGE_PATH = "/PRESENTATION/ADVANCED/INFO_MENTINFO/TOP"
_TIMEOUT = aiohttp.ClientTimeout(total=10)
_ENGLISH = {"Cookie": "EPSON_COOKIE_LANG=lang_b&1/lang_a&1"}

# Volgorde waarin Epson de regels onder "Afdrukinformatie" toont.
FIELDS = ("total", "monochrome", "color", "duplex", "simplex")

_KEYWORDS = {
    "duplex": ("2-zijdig", "2-sided", "two-sided", "duplex", "2-seitig", "recto verso"),
    "simplex": ("1-zijdig", "1-sided", "one-sided", "simplex", "1-seitig"),
    "monochrome": ("zwart-wit", "zwart en wit", "b&w", "black & white", "black and white",
                   "monochrom", "schwarzweiß", "schwarz-weiß", "noir et blanc"),
    "color": ("kleur", "color", "colour", "farb", "couleur"),
}


class _PairParser(HTMLParser):
    """Verzamelt (label, waarde)-paren uit <dt class="key"> en <dd class="value">."""

    def __init__(self) -> None:
        super().__init__()
        self.pairs: list[tuple[str, str]] = []
        self._label: str | None = None
        self._capture: str | None = None  # "dt" of "dd"
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = (dict(attrs).get("class") or "").split()
        if tag == "dt" and "key" in classes:
            self._capture, self._buf = "dt", []
        elif tag == "dd" and "value" in classes:
            self._capture, self._buf = "dd", []

    def handle_endtag(self, tag: str) -> None:
        if tag != self._capture:
            return
        text = " ".join("".join(self._buf).split())
        if tag == "dt":
            self._label = text
        elif self._label is not None:
            self.pairs.append((self._label, text))
            self._label = None
        self._capture = None

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)


def parse_usage(html: str) -> dict[str, int]:
    """Haal totaal, zwart-wit, kleur, 2-zijdig en 1-zijdig uit de pagina."""
    parser = _PairParser()
    parser.feed(html)
    # De eerste vijf getallen zijn de regels onder "Afdrukinformatie";
    # daarna volgen kopie/scan/fax/printertaal, die we hier niet gebruiken.
    numeric = [(label.lower(), int(v)) for label, v in parser.pairs if v.isdigit()][:5]
    if len(numeric) < 5:
        return {}

    out: dict[str, int] = {}
    for label, value in numeric:
        for field, words in _KEYWORDS.items():
            if field not in out and any(w in label for w in words):
                out[field] = value
                break
        else:
            out.setdefault("total", value)

    if set(out) != set(FIELDS):
        # Onbekende taal: val terug op Epson's vaste volgorde.
        out = dict(zip(FIELDS, (v for _, v in numeric), strict=True))
    return out


class WebConfigClient:
    """Haalt de verbruikspagina op en onthoudt wat werkt (HTTPS of HTTP)."""

    def __init__(self, hass: HomeAssistant, host: str) -> None:
        self._hass = hass
        self._host = host
        self._scheme: str | None = None  # werkend schema, na de eerste keer
        self._session: aiohttp.ClientSession | None = None
        self.unsupported = False  # pagina bestaat niet (404): nooit meer vragen

    def _get_session(self) -> aiohttp.ClientSession:
        # Eigen sessie zonder cookie-opslag: anders kan een opgeslagen cookie
        # de meegestuurde taalcookie overschrijven. Zelfondertekend certificaat,
        # dus geen certificaatcontrole.
        if self._session is None:
            self._session = async_create_clientsession(
                self._hass, verify_ssl=False, cookie_jar=aiohttp.DummyCookieJar()
            )
        return self._session

    async def async_fetch_usage(self) -> dict[str, int] | None:
        """Lees de tellers. None bij een (tijdelijke) fout of onbruikbare pagina."""
        if self.unsupported:
            return None
        # HTTPS eerst: bij een doorverwijzing van HTTP naar HTTPS valt de
        # taalcookie weg. Modellen zonder HTTPS vallen terug op HTTP.
        schemes = (self._scheme,) if self._scheme else ("https", "http")
        for scheme in schemes:
            url = f"{scheme}://{self._host}{USAGE_PATH}"
            try:
                async with self._get_session().get(
                    url, timeout=_TIMEOUT, headers=_ENGLISH, allow_redirects=True
                ) as resp:
                    if resp.status == 404:
                        _LOGGER.debug("%s bestaat niet op deze printer", url)
                        self.unsupported = True
                        return None
                    if resp.status != 200:
                        _LOGGER.debug("%s gaf HTTP %s", url, resp.status)
                        continue
                    final_scheme = resp.url.scheme
                    html = await resp.text(errors="replace")
            except (TimeoutError, aiohttp.ClientError) as err:
                _LOGGER.debug("%s niet bereikbaar: %s", url, err)
                continue
            result = parse_usage(html)
            if result:
                self._scheme = final_scheme
                return result
            _LOGGER.debug("%s bevat geen verbruikstellers", url)
        return None
