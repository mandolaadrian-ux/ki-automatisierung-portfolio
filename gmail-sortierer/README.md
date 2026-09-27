# Gmail-Sortierer

Sortiert Gmail-Postfächer automatisch mit einer **lokalen KI** (Ollama, qwen3:8b auf einer RTX 2080 Ti).

**Kategorien (Gmail-Labels):** Wichtig KI-Sortiert · Jobangebote · Rechnungen · Zugangsdaten · Werbung · Spam  
Jede bearbeitete Mail erhält zusätzlich `KI-Geprüft`.

## Eigenschaften
- **Sicher:** setzt nur Labels – löscht, verschiebt und verschickt nichts (per Test abgesichert)
- **Probelauf-Modus:** zeigt die Einordnung, ohne etwas zu ändern
- **Ausfallsicher:** ist Ollama nicht erreichbar, greifen Stichwort-Regeln
- **Datenschutz:** E-Mail-Inhalte werden nur lokal von der KI gelesen
- **Automatikbetrieb:** alle 5 Minuten 30 Mails
- Anmeldung per OAuth 2.0 mit PKCE, nur Python-Standardbibliothek

## Nutzung
```
python gmail_sortierer.py            # Probelauf
python gmail_sortierer.py --echt     # Labels setzen
python gmail_sortierer.py --echt --alle 5
python -m unittest -v                # 40 Tests
```
Benötigt eine eigene `client_secret_*.json` (Google Cloud, OAuth-Client „Desktop-App“).

## Ergebnis im Einsatz
Erster echter Lauf: 20 Mails korrekt eingeordnet (Rechnungen 3, Zugangsdaten 5, Werbung 11, Wichtig 1).
