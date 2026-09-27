"""SELFTEST V30 - ruft die ECHTE main() auf. Ollama wird hier simuliert.
Ob dein echtes Ollama antwortet, prüft 2_OLLAMA_CHECK.bat separat."""
from pathlib import Path
import importlib.util, io, json, shutil, sys, tempfile, contextlib

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("agent", HERE / "agent_v30.py")
agent = importlib.util.module_from_spec(spec); spec.loader.exec_module(agent)

EXTRA_TESTS = "import unittest\nfrom main import process_email\n\nclass Extra(unittest.TestCase):\n" + "".join(
    f"    def test_extra_{i}(self):\n        self.assertIn('prioritaet', process_email('Hallo {i}'))\n" for i in range(25))

results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name)

def setup(td, with_best=True):
    td = Path(td)
    # Eigenes Testprojekt mit genau 36 Tests - unabhängig von deinem echten project-Ordner.
    proj = td / "project"; proj.mkdir()
    (proj / "main.py").write_text(
        "def process_email(t):\n    return {'prioritaet': 'hoch' if 'dringend' in (t or '') else 'niedrig'}\n",
        encoding="utf-8")
    (proj / "test_baseline.py").write_text(
        "import unittest\nfrom main import process_email\n\nclass B(unittest.TestCase):\n" + "".join(
        f"    def test_b{i}(self):\n        self.assertIn('prioritaet', process_email('x{i}'))\n" for i in range(36)),
        encoding="utf-8")
    # Eigener Testauftrag - unabhängig von deiner AUFTRAG.txt.
    tf = td / "AUFTRAG_TEST.txt"
    tf.write_text("Erstelle mindestens 15 neue künstliche Unit-Tests.", encoding="utf-8")
    state = td / "state"; best = state / "best"
    if with_best:
        shutil.copytree(proj, best)
        (best / "test_neu_v26.py").write_text(EXTRA_TESTS, encoding="utf-8")
        import hashlib   # gleicher Auftrag wie beim Speichern des BEST
        task = tf.read_text(encoding="utf-8-sig").strip()
        (state / "auftrag.sha256").write_text(hashlib.sha256(task.encode("utf-8")).hexdigest())
    agent.PROJECT, agent.STATE, agent.BEST = proj, state, best
    agent.TASK_FILE = tf
    return proj, best

def run_main(fake_ask, cycles=2):
    agent.ask = fake_ask; agent.MAX_CYCLES = cycles
    agent.ask_claude = lambda prompt, **k: fake_ask("claude", prompt)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = agent.main()
    return rc, buf.getvalue()

original_ask = agent.ask

# 1) Zustimmungs-Erkennung
check("Zustimmung: exakt", agent.approved("ENTSCHEIDUNG: ZUSTIMMUNG\nBEFUND: ok"))
check("Zustimmung: fett (**...**)", agent.approved("**ENTSCHEIDUNG: ZUSTIMMUNG**"))
check("Zustimmung: mit Punkt", agent.approved("Entscheidung: Zustimmung."))
check("Zustimmung: nach <think>-Block", agent.approved("<think>hmm NACHARBEIT?</think>\nENTSCHEIDUNG: ZUSTIMMUNG"))
check("Ablehnung: NACHARBEIT", not agent.approved("**ENTSCHEIDUNG: NACHARBEIT**"))
check("Ablehnung: leere Antwort", not agent.approved(""))

# 2) qwen3 bekommt think=false und kurze Antwortlänge (echte ask(), Netzwerk simuliert)
sent = {}
class FakeResp:
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def read(self): return json.dumps({"response": "<think>x</think>ENTSCHEIDUNG: ZUSTIMMUNG"}).encode()
def fake_urlopen(req, timeout=None):
    sent.update(json.loads(req.data.decode())); return FakeResp()
agent.urllib.request.urlopen = fake_urlopen
agent.ask = original_ask
ans = agent.ask_reviewer_with_retry("qwen3:8b", "p", "Test")
check("qwen3: think=false wird gesendet", sent.get("think") is False)
check("Prüfer: Antwortlänge begrenzt (num_predict=300)", sent["options"].get("num_predict") == 300)
check("Denkblock wird aus Antwort entfernt", ans == "ENTSCHEIDUNG: ZUSTIMMUNG")

# 3) Echte main(): BEST 61 vorhanden, Prüfer stimmen zu -> Erfolg, Coder nie aufgerufen
with tempfile.TemporaryDirectory() as td:
    proj, best = setup(td)
    calls = []
    def fake(model, prompt, timeout=300, max_tokens=None):
        calls.append(model)
        if "autonomer Python-Entwickler" in prompt: raise AssertionError("Coder aufgerufen")
        return "**ENTSCHEIDUNG: ZUSTIMMUNG**\nBEFUND: ok"
    rc, out = run_main(fake)
    ok, n, _ = agent.tests(proj)
    check("main(): BEST 61 + Zustimmung -> Erfolg (Rückgabe 0)", rc == 0)
    check("main(): Coder wurde übersprungen", len(calls) == 2)
    check("main(): Projekt hat danach 61 grüne Tests", ok and n == 61)

# 4) Echte main(): Prüfer-Timeout -> Stopp, BEST 61 bleibt
with tempfile.TemporaryDirectory() as td:
    proj, best = setup(td)
    def fake(model, prompt, timeout=300, max_tokens=None): raise TimeoutError("simuliert")
    rc, out = run_main(fake)
    ok, n, _ = agent.tests(best)
    check("main(): Prüfer-Timeout -> Stopp (Rückgabe 6)", rc == 6)
    check("main(): BEST bleibt 61 nach Timeout", ok and n == 61)

# 5) Echte main(): Prüfer wollen Nacharbeit, Coder liefert Müll -> BEST bleibt 61
with tempfile.TemporaryDirectory() as td:
    proj, best = setup(td)
    def fake(model, prompt, timeout=300, max_tokens=None):
        if "autonomer Python-Entwickler" in prompt: return "===== FILE: main.py =====\ndef kaputt(:\n===== END FILE ====="
        return "ENTSCHEIDUNG: NACHARBEIT\nBEFUND: mehr Tests"
    rc, out = run_main(fake)
    ok, n, _ = agent.tests(best)
    check("main(): kaputter Coder-Code wird verworfen", "VERSUCH VERWORFEN" in out)
    check("main(): BEST bleibt 61 nach kaputtem Code", ok and n == 61)

# 6) Echte main(): kein BEST -> startet sauber bei 36
with tempfile.TemporaryDirectory() as td:
    proj, best = setup(td, with_best=False)
    def fake(model, prompt, timeout=300, max_tokens=None): raise TimeoutError("simuliert")
    rc, out = run_main(fake, cycles=1)
    check("main(): ohne BEST Start bei Baseline 36", "Baseline=36" in out)

# 7) Claude-Antwort mit ```python-Zäunen wird trotzdem korrekt gelesen
files = agent.parse_files("===== FILE: test_x.py =====\n```python\nimport unittest\n```\n===== END FILE =====")
check("Code-Zäune (```) werden entfernt", files["test_x.py"] == "import unittest\n")
# 8) Ohne API-Schlüssel klare Fehlermeldung
import os
os.environ.pop("ANTHROPIC_API_KEY", None)
agent.API_KEY_FILE = Path(tempfile.gettempdir()) / "gibt_es_nicht_api_key.txt"
try:
    agent.api_key(); check("Fehlender API-Schlüssel wird erkannt", False)
except RuntimeError:
    check("Fehlender API-Schlüssel wird erkannt", True)

# 9) Flexible Aufträge
check("Auftrag ohne Zahl -> mindestens 1 neuer Test", agent.reqs("Erkenne Reklamationen.", 62)["minimum_total_tests"] == 63)
check("Auftrag mit 20 neuen Tests -> +20", agent.reqs("Erstelle mindestens 20 neue Tests.", 62)["minimum_total_tests"] == 82)
# 10) Neuer Auftrag verwirft alten BEST (kein falscher Erfolg mit altem Stand)
with tempfile.TemporaryDirectory() as td:
    proj, best = setup(td)            # BEST = 61 aus altem Auftrag
    tf = Path(td) / "AUFTRAG.txt"; tf.write_text("Erkenne Reklamationen.", encoding="utf-8")
    agent.TASK_FILE = tf
    calls = []
    def fake(model, prompt, timeout=300, max_tokens=None):
        calls.append(prompt); raise TimeoutError("simuliert")
    rc, out = run_main(fake, cycles=1)
    check("Neuer Auftrag: alter BEST verworfen", "NEUER AUFTRAG" in out and "BEST=36" in out)

failed = [n for n, c in results if not c]
print()
print(f"SELFTEST V30: {'PASS' if not failed else 'FAIL'} ({len(results)-len(failed)}/{len(results)})")
print("Hinweis: Das prüft die Steuerlogik. Ob DEIN Ollama antwortet, zeigt 2_OLLAMA_CHECK.bat.")
sys.exit(1 if failed else 0)
