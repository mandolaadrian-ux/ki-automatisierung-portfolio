import re


_FIELD_PATTERNS = {
    "subject": r"(?im)^\s*(?:betreff|subject|titel)\s*:\s*(.+)$",
    "kunde": r"(?im)^\s*(?:kunde|customer|firma|company)\s*:\s*(.+)$",
    "produkt": r"(?im)^\s*(?:produkt|product|artikel|ware)\s*:\s*(.+)$",
    "menge": r"(?im)^\s*(?:menge|quantity|anzahl|stückzahl|stueckzahl)\s*:\s*([\d\.,]+)",
    "liefertermin": r"(?im)^\s*(?:liefertermin|delivery|termin|lieferdatum|wunschtermin)\s*:\s*(.+)$",
}


def _to_int(value):
    """Wandelt eine Mengenangabe robust in eine Ganzzahl um."""
    if value is None:
        return None
    cleaned = re.sub(r"[.\s]", "", str(value))
    cleaned = cleaned.replace(",", "")
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except (ValueError, TypeError):
        return None


def parse_email(email_text):
    """Einfacher, robuster Parser für künstliche Text-E-Mails.

    Funktioniert auch bei fehlenden, leeren oder ungewöhnlichen Eingaben
    und erkennt zusätzliche deutsche/englische Feld-Varianten.
    """
    if email_text is None:
        text = ""
    else:
        if isinstance(email_text, str):
            text = email_text
        else:
            try:
                text = str(email_text)
            except Exception:
                text = ""

    data = {
        "subject": "",
        "body": text,
        "kunde": None,
        "produkt": None,
        "menge": None,
        "liefertermin": None,
    }

    for key, pattern in _FIELD_PATTERNS.items():
        try:
            m = re.search(pattern, text)
        except Exception:
            m = None
        if not m:
            continue
        raw_value = m.group(1).strip()
        if not raw_value:
            continue
        if key == "menge":
            data[key] = _to_int(raw_value)
        else:
            data[key] = raw_value
    return data
