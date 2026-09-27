# KI-Coding-Agent

Ein Agent, der ein bestehendes Python-Projekt nach einem Auftrag in `AUFTRAG.txt` selbstständig
erweitert – und nur übernimmt, was nachweislich funktioniert.

## Ablauf
1. Baseline-Tests messen
2. **Claude-API** schreibt Code und neue Tests
3. Syntaxprüfung → alle Tests → nur bei Verbesserung wird der Stand gespeichert (sonst Rollback)
4. Zwei **lokale KI-Prüfer** (Ollama) bewerten das Ergebnis
5. Zwei finale Testläufe → Übernahme ins Projekt

## Ergebnisse
| Auftrag | Vorher | Nachher | Zyklen |
|---|---|---|---|
| E-Mail-Assistent: Prioritäten, robuste Felder | 36 Tests | 62 Tests | 1 |
| Neue Kategorien Reklamation / Terminanfrage | 62 Tests | 93 Tests | 1 |

## Was ich dabei gelernt habe
Kleine lokale Modelle (7–8 B) sind gut für Prüf- und Einordnungsaufgaben, scheitern aber an
mehrstufigem Programmieren. Die Hybrid-Lösung – starkes Modell schreibt, lokales Modell prüft,
Tests entscheiden – war stabil.

## Nutzung
```
python SELFTEST.py        # Steuerlogik prüfen
python OLLAMA_CHECK.py    # Claude-API + Ollama prüfen
python ALLES_AUTOMATISCH.py
```
Benötigt `API_KEY.txt` (Anthropic) – wird nie hochgeladen.
