"""Führt alle 4 Schritte automatisch nacheinander aus.
Stoppt beim ersten Fehler. Alles wird in BERICHT.txt mitgeschrieben."""
from pathlib import Path
import os, subprocess, sys, datetime

HERE = Path(__file__).resolve().parent
BERICHT = HERE / "BERICHT.txt"
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

env = dict(os.environ, AUTO="1", PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONUNBUFFERED="1")
log = open(BERICHT, "w", encoding="utf-8")
try: (HERE / "AGENT_LOG.txt").unlink()
except Exception: pass

def schreibe(text=""):
    print(text); log.write(text + "\n"); log.flush()

def schritt(nr, titel, datei):
    schreibe(f"\n{'=' * 60}\nSCHRITT {nr}/3: {titel}\n{'=' * 60}")
    p = subprocess.Popen([sys.executable, "-u", str(HERE / datei)], cwd=HERE, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for zeile in iter(p.stdout.readline, b""):
        schreibe(zeile.decode("utf-8", errors="replace").rstrip())
    return p.wait()

def ende(ok, nachricht):
    schreibe(f"\n{'#' * 60}\n{'FERTIG: ' if ok else 'GESTOPPT: '}{nachricht}\n{'#' * 60}")
    schreibe(f"\nBericht gespeichert: {BERICHT}")
    schreibe("-> Schick mir BERICHT.txt (oder einen Screenshot).")
    log.close(); input("\nEnter zum Beenden"); sys.exit(0 if ok else 1)

schreibe(f"KI-AGENT V30 - AUTOMATISCHER ABLAUF  ({datetime.datetime.now():%d.%m.%Y %H:%M})")

if schritt(1, "Selbsttest", "SELFTEST.py") != 0:
    ende(False, "Selbsttest fehlgeschlagen.")
if schritt(2, "Check: Claude-API + Ollama (echt)", "OLLAMA_CHECK.py") != 0:
    ende(False, "Check fehlgeschlagen (Claude-API oder Ollama). Siehe oben.")
try: (HERE / "AGENT_LOG.txt").unlink()
except Exception: pass
rc = schritt(3, "Agent: Claude-Coder + Prüfer + 2 Endtests", "agent_v30.py")
if rc == 0:
    ende(True, "ERFOLG. Das fertige Projekt liegt im Ordner 'project'.")
ende(False, f"Agent endete mit Code {rc} (6 = Prüfer-Timeout, 5 = Endtest, 1 = Zyklen aufgebraucht).")
