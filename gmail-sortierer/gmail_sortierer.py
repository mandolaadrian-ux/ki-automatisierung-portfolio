#!/usr/bin/env python3
"""Gmail-Sortierer - Nachbau des n8n-Workflows "My workflow 2".

Ablauf (wie in n8n):
  Mails abrufen -> KI (Ollama, lokal auf deiner Grafikkarte) ordnet zu
  -> Wichtig / Jobangebote / Rechnungen / Zugangsdaten / Werbung / Spam -> Label + "KI-Geprüft" setzen
  -> Zusammenfassung: wie viele sortiert, wie viele noch offen.

Sicherheit: Das Programm setzt NUR Labels. Es löscht nichts, verschiebt nichts,
verschickt nichts. Mit --probelauf wird gar nichts verändert.

Nur Python-Standardbibliothek, keine Installation nötig.
"""
import base64, hashlib, html, http.server, json, os, re, secrets, socket, sys, threading
import time, urllib.error, urllib.parse, urllib.request, webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKEN_FILE = HERE / "token.json"

CONFIG = {
    "max_mails": 30,                                          # pro Durchlauf
    "suche": "in:inbox -label:KI-Geprüft",                    # gelesen + ungelesen, jedes Alter
    "ollama_url": "http://127.0.0.1:11434/api/generate",
    "ollama_model": "qwen3:8b",
    "labels": {                                               # Kategorie -> Gmail-Label (None = kein Kategorie-Label)
        "wichtig": "Wichtig KI-Sortiert",
        "jobangebote": "Jobangebote",
        "rechnungen": "Rechnungen",
        "zugangsdaten": "Zugangsdaten",
        "werbung": "Werbung",
        "spam": "Spam",
        "sonstiges": None,
    },
    "fertig_label": "KI-Geprüft",                             # bekommt JEDE bearbeitete Mail
}
CATEGORIES = ("wichtig", "jobangebote", "rechnungen", "zugangsdaten", "werbung", "spam", "sonstiges")
SCOPE = "https://www.googleapis.com/auth/gmail.modify"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me/"

# Ausgabe sofort anzeigen (auch unter Windows ohne Pufferung)
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception: pass


# ======================================================================
# 1) KI-Sortierung
# ======================================================================
PROMPT = """Ordne die folgende E-Mail genau EINER Kategorie zu.

zugangsdaten = Passwort zurücksetzen, Login-/Bestätigungscodes, Anmeldung, Kontosicherheit, Sicherheitswarnungen,
               Kontoänderungen, Datenfreigabe an andere Dienste, Konto wird gelöscht/beendet
jobangebote  = Stellenangebote, Job-Alerts, Recruiter, Bewerbungen, Vorstellungsgespräche
rechnungen   = Rechnungen, Zahlungen, Mahnungen, Quittungen, Belege, Abbuchungen, Bestellbestätigungen mit Betrag
wichtig      = persönlich an mich gerichtet oder verlangt eine Reaktion: Fristen, Termine, Behörden, Verträge,
               Kündigungen
werbung      = Newsletter, Rabatte, Angebote, Produktneuheiten, Marketing von bekannten Firmen
spam         = unerwünscht, dubios, Betrugs- oder Phishing-Verdacht, Gewinnspiele, unbekannte Massenmails
sonstiges    = passt in keine Kategorie

Antworte NUR mit einem Wort: zugangsdaten, jobangebote, rechnungen, wichtig, werbung, spam oder sonstiges.

Von: {absender}
Betreff: {betreff}
Text: {text}"""

RULES = {   # Ersatz, falls Ollama nicht antwortet (Reihenfolge = Priorität)
    "zugangsdaten": ("passwort", "password", "kennwort", "bestätigungscode", "verification code", "sicherheitscode",
                     "anmeldung", "login", "neue anmeldung", "sicherheitswarnung", "security alert", "zwei-faktor",
                     "2fa", "konto gesperrt", "kontodaten", "konto beendet", "beendigung", "zugang"),
    "jobangebote": ("stellenangebot", "job", "bewerbung", "karriere", "recruiter", "vorstellungsgespräch",
                    "stepstone", "indeed", "xing", "vacancy"),
    "spam": ("gewinner", "gewonnen", "lottery", "bitcoin", "krypto-gewinn", "erbschaft", "dringende überweisung"),
    "rechnungen": ("rechnung", "invoice", "zahlung", "mahnung", "quittung", "beleg", "abbuchung", "lastschrift",
                   "bestellbestätigung", "receipt", "payment"),
    "wichtig": ("kündigung", "frist", "termin", "finanzamt", "behörde", "vertrag", "dringend"),
    "werbung": ("newsletter", "rabatt", "% off", "angebot", "sale", "gutschein", "abmelden", "unsubscribe", "deal"),
}


def parse_category(answer):
    """Liest die Kategorie aus der KI-Antwort. Unklar -> None."""
    text = re.sub(r"(?is)<think>.*?</think>", "", answer or "").lower()
    text = re.sub(r"[*\"'`.:]", " ", text).strip()
    stems = {"zugangsdaten": "zugangsdat", "jobangebote": "jobangebot", "rechnungen": "rechnung", "wichtig": "wichtig",
             "werbung": "werbung", "spam": "spam", "sonstiges": "sonstig"}
    for c, stem in stems.items():          # Antwort beginnt mit der Kategorie -> eindeutig
        if text.startswith(stem): return c
    found = [c for c, stem in stems.items() if stem in text]
    return found[0] if len(found) == 1 else None


def rule_classify(absender, betreff, text):
    blob = f"{absender} {betreff} {text}".lower()
    for cat, words in RULES.items():
        if any(w in blob for w in words):
            return cat
    return "sonstiges"


def ask_ollama(prompt, timeout=120):
    payload = {"model": CONFIG["ollama_model"], "prompt": prompt, "stream": False,
               "think": False, "options": {"temperature": 0, "num_predict": 20, "num_ctx": 4096}}
    req = urllib.request.Request(CONFIG["ollama_url"], data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode()).get("response", "")


def classify(mail, ask=ask_ollama):
    """Gibt (kategorie, quelle) zurück. quelle = 'KI' oder 'Regel'."""
    prompt = PROMPT.format(absender=mail["from"], betreff=mail["subject"], text=mail["text"][:1500])
    try:
        cat = parse_category(ask(prompt))
        if cat: return cat, "KI"
    except Exception:
        pass
    return rule_classify(mail["from"], mail["subject"], mail["text"]), "Regel"


# ======================================================================
# 2) Mail-Inhalt lesen
# ======================================================================
def _b64(data):
    return base64.urlsafe_b64decode((data or "") + "=" * (-len(data or "") % 4)).decode("utf-8", "replace")


def extract_text(payload):
    """Holt lesbaren Text aus einer Gmail-Nachricht (text/plain bevorzugt, sonst HTML ohne Tags)."""
    plain, htm = [], []
    def walk(part):
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime == "text/plain": plain.append(_b64(data))
        elif data and mime == "text/html": htm.append(_b64(data))
        for p in part.get("parts", []) or []: walk(p)
    walk(payload or {})
    if plain: return re.sub(r"\s+", " ", " ".join(plain)).strip()
    raw = " ".join(htm)
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def parse_message(msg):
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    text = extract_text(msg.get("payload")) or msg.get("snippet", "")
    subject = re.sub(r"\s+", " ", headers.get("subject", "")).strip() or "(kein Betreff)"
    return {"id": msg["id"], "from": headers.get("from", ""), "subject": subject,
            "text": text}


# ======================================================================
# 3) Google-Anmeldung (OAuth, einmalig im Browser)
# ======================================================================
def load_client():
    """Sucht client_secret*.json hier und in Downloads. Bevorzugt eine Desktop-App-Datei
    ("installed"), weil die n8n-Datei ("web") auf Port 5678 festgelegt ist."""
    files = sorted(HERE.glob("client_secret*.json")) + sorted(HERE.parent.glob("client_secret*.json"))
    if not files:
        raise SystemExit("FEHLT: client_secret_....json (Google-Zugangsdatei).\n"
                         "-> In diesen Ordner oder in den Ordner darüber (Downloads) legen.")
    found = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "installed" in data:
            return "installed", data["installed"]
        if "web" in data:
            found.append(data["web"])
    if found:
        return "web", found[0]
    raise SystemExit("Keine gültige client_secret-Datei gefunden.")


def pick_redirect(kind, client):
    """Desktop-Client: beliebiger freier Port. Web-Client: eine eingetragene localhost-Adresse (nicht n8n:5678)."""
    if kind == "installed":
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        return f"http://127.0.0.1:{port}/"
    for uri in client.get("redirect_uris", []):
        u = urllib.parse.urlparse(uri)
        if u.hostname in ("localhost", "127.0.0.1") and u.port and u.port != 5678:
            return uri
    raise SystemExit(
        "Dein Google-Client ist für n8n eingerichtet (Weiterleitung auf Port 5678).\n"
        "-> console.cloud.google.com -> APIs & Dienste -> Anmeldedaten -> dein OAuth-Client\n"
        "   -> 'Autorisierte Weiterleitungs-URIs' -> hinzufügen:  http://localhost:8765/\n"
        "   -> Speichern, die JSON-Datei NEU herunterladen und hier die alte ersetzen.\n"
        "   Oder einfacher: einen neuen OAuth-Client vom Typ 'Desktop-App' anlegen.")


def _post_form(url, fields):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def login():
    kind, client = load_client()
    redirect = pick_redirect(kind, client)
    u = urllib.parse.urlparse(redirect)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    auth_url = client.get("auth_uri", "https://accounts.google.com/o/oauth2/auth") + "?" + urllib.parse.urlencode({
        "client_id": client["client_id"], "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in q or "error" in q:
                result.update({k: v[0] for k, v in q.items()})
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write("<h2>Fertig - du kannst dieses Fenster schließen.</h2>".encode())
        def log_message(self, *a): pass

    srv = http.server.HTTPServer((u.hostname or "127.0.0.1", u.port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("Browser öffnet sich: bei Google anmelden und Zugriff erlauben ...")
    print("(Falls nicht: diesen Link öffnen)\n" + auth_url)
    webbrowser.open(auth_url)
    t0 = time.time()
    while not result and time.time() - t0 < 300: time.sleep(0.5)
    srv.shutdown()
    if result.get("state") != state or "code" not in result:
        raise SystemExit(f"Anmeldung abgebrochen: {result.get('error', 'keine Antwort innerhalb 5 Minuten')}")
    tok = _post_form(client.get("token_uri", "https://oauth2.googleapis.com/token"), {
        "code": result["code"], "client_id": client["client_id"], "client_secret": client.get("client_secret", ""),
        "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier})
    tok["expires_at"] = time.time() + tok.get("expires_in", 3600) - 60
    TOKEN_FILE.write_text(json.dumps(tok), encoding="utf-8")
    print("Anmeldung gespeichert (token.json). Nächstes Mal geht es ohne Browser.\n")
    return tok


def access_token():
    if not TOKEN_FILE.exists():
        return login()["access_token"]
    tok = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    if time.time() < tok.get("expires_at", 0):
        return tok["access_token"]
    _, client = load_client()
    try:
        new = _post_form(client.get("token_uri", "https://oauth2.googleapis.com/token"), {
            "client_id": client["client_id"], "client_secret": client.get("client_secret", ""),
            "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"})
    except urllib.error.HTTPError:
        TOKEN_FILE.unlink(missing_ok=True)
        return login()["access_token"]
    tok.update(new); tok["expires_at"] = time.time() + new.get("expires_in", 3600) - 60
    TOKEN_FILE.write_text(json.dumps(tok), encoding="utf-8")
    return tok["access_token"]


# ======================================================================
# 4) Gmail-Zugriff
# ======================================================================
class Gmail:
    def _call(self, method, path, body=None):
        req = urllib.request.Request(GMAIL + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": "Bearer " + access_token(),
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Gmail HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")

    def labels(self):
        return self._call("GET", "labels").get("labels", [])

    def create_label(self, name):
        return self._call("POST", "labels", {"name": name, "labelListVisibility": "labelShow",
                                             "messageListVisibility": "show"})

    def search(self, query, limit):
        r = self._call("GET", "messages?" + urllib.parse.urlencode({"q": query, "maxResults": limit}))
        return [m["id"] for m in r.get("messages", [])], r.get("resultSizeEstimate", 0)

    def get(self, msg_id):
        return self._call("GET", f"messages/{msg_id}?format=full")

    def add_labels(self, msg_id, label_ids):
        return self._call("POST", f"messages/{msg_id}/modify", {"addLabelIds": label_ids})


def ensure_labels(gmail, create=True):
    """Liefert {kategorie/fertig: label_id}. Fehlende Labels werden angelegt.
    Kollidiert ein Name mit einem Gmail-Systemlabel (z. B. 'Wichtig'), wird 'KI-<Name>' verwendet."""
    existing = {l["name"].lower(): l["id"] for l in gmail.labels()}
    wanted = {k: v for k, v in CONFIG["labels"].items() if v}; wanted["_fertig"] = CONFIG["fertig_label"]
    ids = {}
    for key, name in wanted.items():
        for candidate in (name, "KI-" + name):
            if candidate.lower() in existing:
                ids[key] = existing[candidate.lower()]; break
            if not create:
                ids[key] = f"(neu: {candidate})"; break
            try:
                ids[key] = gmail.create_label(candidate)["id"]; break
            except RuntimeError as e:
                msg = str(e).lower()
                # Gmail meldet reservierte Namen (z. B. "Wichtig") als 400 "Invalid label name",
                # vorhandene als 409 "exists/conflict" -> dann "KI-<Name>" versuchen.
                if not any(k in msg for k in ("409", "exists", "conflict", "invalid label name")):
                    raise
        else:
            raise RuntimeError(f"Label '{name}' konnte nicht angelegt werden.")
    return ids


# ======================================================================
# 5) Ein Durchlauf
# ======================================================================
def run(gmail, probelauf=True, ask=ask_ollama, log=print):
    log(f"=== GMAIL-SORTIERER {'(PROBELAUF - nichts wird verändert)' if probelauf else '(ECHT)'} ===")
    label_ids = ensure_labels(gmail, create=not probelauf)
    ids, _ = gmail.search(CONFIG["suche"], CONFIG["max_mails"])
    log(f"{len(ids)} ungeprüfte Mails gefunden (max. {CONFIG['max_mails']} pro Durchlauf).\n")
    counts = {c: 0 for c in CATEGORIES}
    done_id = label_ids.get("_fertig")
    for i, mid in enumerate(ids, 1):
        try:
            raw = gmail.get(mid)
            if done_id and done_id in (raw.get("labelIds") or []):
                log(f"{i:2d}. schon KI-geprüft -> übersprungen"); continue
            mail = parse_message(raw)
            cat, source = classify(mail, ask)
            counts[cat] += 1
            name = CONFIG["labels"].get(cat) or "(nur KI-Geprüft)"
            log(f"{i:2d}. [{name:<19}] ({source:5}) {mail['subject'][:60]}  -  {mail['from'][:40]}")
            if not probelauf:
                add = [label_ids[cat]] if cat in label_ids else []
                gmail.add_labels(mid, add + [done_id])
        except Exception as e:
            log(f"{i:2d}. FEHLER bei Mail {mid}: {e}  -> übersprungen")
    _, remaining = gmail.search(CONFIG["suche"], 1)
    log("\nZUSAMMENFASSUNG: " + ", ".join(f"{CONFIG['labels'][c] or 'ohne Kategorie'} {n}" for c, n in counts.items()))
    log(f"Noch ungeprüft (ungefähr): {remaining if not probelauf else 'unverändert (Probelauf)'}")
    return counts


def main(argv):
    probelauf = "--echt" not in argv
    loop = None
    if "--alle" in argv:
        loop = int(argv[argv.index("--alle") + 1])
    gmail = Gmail()
    while True:
        try:
            run(gmail, probelauf=probelauf)
        except SystemExit:
            raise
        except Exception as e:
            print(f"FEHLER: {e}")
        if not loop: break
        print(f"\nNächster Durchlauf in {loop} Minuten (Fenster offen lassen, Strg+C beendet).\n")
        time.sleep(loop * 60)


if __name__ == "__main__":
    main(sys.argv[1:])
