"""Echter Test gegen dein lokales Ollama: sind die Modelle da und antworten die Prüfer schnell genug?"""
from pathlib import Path
import importlib.util, json, time, urllib.request, sys
import os
def warte(text="Enter zum Beenden"):
    if not os.environ.get("AUTO"): input(text)

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("agent", HERE / "agent_v30.py")
agent = importlib.util.module_from_spec(spec); spec.loader.exec_module(agent)

print("=== OLLAMA-CHECK (echt, kein Simulieren) ===")
try:
    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=10) as r:
        installed = {m["name"] for m in json.loads(r.read().decode())["models"]}
except Exception as e:
    print(f"FEHLER: Ollama nicht erreichbar ({e}).")
    print("-> Ollama starten (Ollama-App öffnen) und nochmal versuchen.")
    warte(); sys.exit(1)

ok_all = True
for model in sorted({agent.CODE_REVIEWER, agent.TASK_REVIEWER}):
    if model not in installed:
        print(f"FEHLT: {model}  -> in der Eingabeaufforderung: ollama pull {model}")
        ok_all = False; continue
    prompt = ("Du bist Prüfer. Antworte in der ersten Zeile exakt "
              "ENTSCHEIDUNG: ZUSTIMMUNG und danach einen kurzen Satz BEFUND.")
    t = time.time()
    try:
        ans = agent.ask(model, prompt, timeout=600, max_tokens=300)
    except Exception as e:
        print(f"FEHLER {model}: {type(e).__name__}: {e}"); ok_all = False; continue
    dt = time.time() - t
    erkannt = agent.approved(ans)
    print(f"\n{model}: {dt:.0f} Sekunden, Zustimmung erkannt: {'JA' if erkannt else 'NEIN'}")
    print("Antwort:", ans[:300].replace("\n", " | "))
    if not erkannt: ok_all = False

print("\n--- Claude-API (Coder) ---")
try:
    t = time.time()
    m = agent.claude_model()
    ans = agent.ask_claude("Antworte nur mit: OK", timeout=60, max_tokens=20)
    print(f"Claude-API: Modell {m}, {time.time()-t:.0f} Sekunden, Antwort: {ans[:40]}")
except Exception as e:
    print(f"Claude-API FEHLER: {e}")
    if "Schlüssel" in str(e) or "401" in str(e):
        print("-> API_KEY.txt prüfen: Schlüssel (sk-ant-...) muss IN der Datei stehen.")
    ok_all = False

print()
print("CHECK: PASS - Claude-Coder und lokale Prüfer funktionieren." if ok_all
      else "CHECK: FAIL - siehe oben.")
warte()
sys.exit(0 if ok_all else 1)
