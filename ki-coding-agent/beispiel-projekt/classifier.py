import re

# Zusätzliche, robust erkannte Schlüsselwörter für Dringlichkeit.
URGENT_KEYWORDS = (
    "dringend", "dringende", "dringender", "eilig", "eilbedürftig",
    "sofort", "sofortig", "asap", "kurzfristig", "heute", "morgen",
    "übermorgen", "uebermorgen", "notfall", "prompt", "zeitnah",
    "unverzüglich", "unverzueglich", "so schnell wie möglich",
    "so schnell wie moeglich", "express", "umgehend", "höchste priorität",
    "hoechste prioritaet",
)

# Schlüsselwörter zur Erkennung von Reklamationen. Varianten mit
# Groß-/Kleinschreibung und einfache Pluralformen bzw. Flexionen (z. B.
# "Reklamationen", "defekte", "beschädigte") werden durch einfache
# Substring-Suche in lowercase-Text erkannt.
REKLAMATION_KEYWORDS = (
    "reklamation", "reklamieren", "reklamiert", "reklamierung",
    "defekt", "kaputt", "beschädigt", "beschaedigt",
    "falsch geliefert", "fehlerhaft", "mangel", "mängel", "maengel",
    "rücksendung", "ruecksendung", "umtausch",
)

# Schlüsselwörter zur Erkennung von Terminanfragen. "termin" wird mit
# Wortgrenzen gesucht, damit z. B. "Liefertermin" nicht fälschlicherweise
# als Terminanfrage erkannt wird.
TERMINANFRAGE_KEYWORDS = (
    "termin", "besprechung", "treffen", "rückruf", "rueckruf",
    "meeting", "terminvorschlag", "kalender",
)

# Schlüsselwörter, die immer mit Wortgrenzen gesucht werden müssen, weil
# sie sonst als Teilstring in anderen, unabhängigen Wörtern vorkommen.
_WORD_BOUNDARY_KEYWORDS = ("termin",)

_EXPLICIT_PRIORITY_PATTERN = re.compile(
    r"(?i)(?:priorit(?:ä|ae)t|priority)\s*:\s*(hoch|mittel|niedrig|high|medium|low)"
)

_PRIORITY_MAP = {
    "hoch": "hoch", "high": "hoch",
    "mittel": "mittel", "medium": "mittel",
    "niedrig": "niedrig", "low": "niedrig",
}

_REQUIRED_FIELDS = ("kunde", "produkt", "menge")


def _safe_text(data, keys):
    """Baut robust einen Suchtext aus mehreren Feldern zusammen."""
    parts = []
    for key in keys:
        try:
            value = data.get(key, "")
        except AttributeError:
            value = ""
        if value is None:
            value = ""
        try:
            parts.append(str(value))
        except Exception:
            parts.append("")
    return " ".join(parts)


def _is_complete(data):
    try:
        return all(data.get(k) not in (None, "", 0) for k in _REQUIRED_FIELDS)
    except AttributeError:
        return False


def _keywords_present(data, keywords):
    """Prüft robust, ob eines der Schlüsselwörter im Text vorkommt.

    Nutzt für Wörter aus _WORD_BOUNDARY_KEYWORDS eine Wortgrenzen-Suche,
    damit z. B. "Liefertermin" nicht fälschlicherweise als "Termin"
    erkannt wird. Alle anderen Wörter werden per einfacher
    Substring-Suche erkannt, damit Varianten wie "Reklamationen" oder
    "defekte" ebenfalls erfasst werden.
    """
    try:
        text = _safe_text(data, ("subject", "body")).lower()
    except Exception:
        return False
    if not text:
        return False
    for kw in keywords:
        if kw in _WORD_BOUNDARY_KEYWORDS:
            try:
                pattern = r"\b" + re.escape(kw) + r"\b"
                if re.search(pattern, text):
                    return True
            except Exception:
                continue
        else:
            if kw in text:
                return True
    return False


def _is_reklamation(data):
    return _keywords_present(data, REKLAMATION_KEYWORDS)


def _is_terminanfrage(data):
    return _keywords_present(data, TERMINANFRAGE_KEYWORDS)


def classify_email(data):
    """Klassifiziert eine bereits geparste E-Mail.

    Bleibt robust gegenüber fehlenden oder ungültigen Eingaben und
    liefert einen der bekannten Werte: 'angebotsanfrage', 'reklamation',
    'terminanfrage' oder 'sonstiges'.

    Reihenfolge:
    1. Eine vollständige Angebotsanfrage (Kunde, Produkt, Menge) hat
       immer Vorrang.
    2. Reklamation.
    3. Terminanfrage.
    4. Sonstiges.
    """
    if not isinstance(data, dict):
        return "sonstiges"
    try:
        if _is_complete(data):
            return "angebotsanfrage"
        if _is_reklamation(data):
            return "reklamation"
        if _is_terminanfrage(data):
            return "terminanfrage"
        return "sonstiges"
    except Exception:
        return "sonstiges"


def is_urgent(data):
    """Erkennt, ob eine Anfrage aufgrund von Formulierungen dringend ist."""
    if not isinstance(data, dict):
        return False
    try:
        text = _safe_text(data, ("subject", "body", "liefertermin")).lower()
    except Exception:
        return False
    return any(word in text for word in URGENT_KEYWORDS)


def determine_priority(data):
    """Ermittelt Priorität ('hoch'/'mittel'/'niedrig') und eine Begründung.

    Reihenfolge:
    1. Eine explizit angegebene Priorität in der E-Mail hat Vorrang.
    2. Erkannte Dringlichkeit (Schlüsselwörter, kurzfristiger Termin).
    3. Vollständige Angebotsanfrage (Kunde, Produkt, Menge vorhanden).
    4. Reklamationen erhalten mindestens die Priorität 'mittel'.
    5. Alles andere gilt als niedrige Priorität.
    """
    if not isinstance(data, dict):
        return "niedrig", "Ungültige oder fehlende E-Mail-Daten"

    try:
        raw_text = _safe_text(data, ("subject", "body", "liefertermin"))
    except Exception:
        raw_text = ""

    try:
        match = _EXPLICIT_PRIORITY_PATTERN.search(raw_text)
    except Exception:
        match = None
    if match:
        mapped = _PRIORITY_MAP.get(match.group(1).lower())
        if mapped:
            return mapped, "Explizite Prioritätsangabe in der E-Mail erkannt"

    if is_urgent(data):
        return "hoch", "Dringlichkeit oder sehr kurzfristiger Liefertermin erkannt"

    if _is_complete(data):
        return "mittel", "Vollständige Angebotsanfrage mit Kunde, Produkt und Menge"

    try:
        if _is_reklamation(data):
            return (
                "mittel",
                "Reklamation erkannt: Mindestpriorität mittel für "
                "Kundenanliegen bei Mängeln, Defekten oder Rücksendungen",
            )
    except Exception:
        pass

    return "niedrig", "Sonstige oder unvollständige Anfrage ohne erkennbare Dringlichkeit"
