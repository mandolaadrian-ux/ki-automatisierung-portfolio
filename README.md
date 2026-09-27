# Adrian Mandola – KI-Automatisierung

Krankenpfleger und Quereinsteiger in KI-Automatisierung. Ich baue Agenten, die wiederkehrende
Büroarbeit übernehmen – mit **lokaler KI** (Ollama), damit Daten den Rechner nicht verlassen.

## Projekte

| Projekt | Was es tut | Technik |
|---|---|---|
| [Gmail-Sortierer](gmail-sortierer/) | Ordnet E-Mails per lokaler KI in Kategorien (Wichtig, Rechnungen, Zugangsdaten, Werbung, Jobangebote, Spam) | Python, Gmail-API, OAuth 2.0, Ollama (qwen3) |
| [KI-Coding-Agent](ki-coding-agent/) | Erweitert ein Python-Projekt selbstständig nach einem Auftrag – mit Tests, Rollback und zwei KI-Prüfern | Python, Claude-API, Ollama, unittest |

## Arbeitsweise
- Zuerst Probelauf, erst dann echte Änderungen
- Jede Funktion mit automatischen Tests
- Keine Zugangsdaten im Code
