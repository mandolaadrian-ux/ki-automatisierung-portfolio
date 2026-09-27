#!/usr/bin/env python3
import ast, hashlib, json, re, shutil, subprocess, sys, tempfile, urllib.request, urllib.error
from pathlib import Path

ROOT=Path(__file__).resolve().parent

# V30: Jede Ausgabe sofort ins Fenster UND in AGENT_LOG.txt (unabhängig von Pufferung).
import builtins, datetime
_orig_print=builtins.print
def print(*a, **k):
    k.setdefault("flush", True)
    _orig_print(*a, **k)
    try:
        with open(ROOT/"AGENT_LOG.txt","a",encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now():%H:%M:%S}] "+" ".join(str(x) for x in a)+"\n")
    except Exception:
        pass
PROJECT=ROOT/"project"
TASK_FILE=ROOT/"AUFTRAG.txt"
STATE=ROOT/"agent_state_v26"
BEST=STATE/"best"
OLLAMA="http://127.0.0.1:11434/api/generate"
CODER="claude"   # V30: Coder = Claude-API. Prüfer bleiben lokal (Ollama).
API_KEY_FILE=ROOT/"API_KEY.txt"
CODE_REVIEWER="qwen2.5-coder:7b"
TASK_REVIEWER="qwen3:8b"
MAX_CYCLES=20

def run(cmd,cwd,timeout=180):
    p=subprocess.run(cmd,cwd=str(cwd),capture_output=True,text=True,
                     encoding="utf-8",errors="replace",timeout=timeout)
    return p.returncode,(p.stdout or "")+(p.stderr or "")

def tests(cwd):
    rc,out=run([sys.executable,"-m","unittest","discover","-v"],cwd)
    m=re.findall(r"Ran\s+(\d+)\s+tests?",out)
    return rc==0 and bool(m), int(m[-1]) if m else 0, out

def syntax(cwd):
    for p in cwd.glob("*.py"):
        ast.parse(p.read_text(encoding="utf-8"),filename=str(p))

def copytree(a,b):
    if b.exists(): shutil.rmtree(b)
    shutil.copytree(a,b)

def strip_think(text):
    """Entfernt Denkblöcke von qwen3 (<think>...</think>), falls Ollama sie mitliefert."""
    text=re.sub(r"(?is)<think>.*?</think>","",text or "")
    text=re.sub(r"(?is)^.*?</think>","",text)  # unvollständiger Anfang
    return text.strip()

def ask(model,prompt,timeout=300,max_tokens=None):
    options={"temperature":0.1,"num_ctx":8192}
    if max_tokens: options["num_predict"]=max_tokens
    payload={"model":model,"prompt":prompt,"stream":False,"options":options}
    if model.startswith("qwen3"):
        payload["think"]=False   # V30: Denkmodus aus -> keine 600s-Timeouts mehr
    data=json.dumps(payload).encode()
    req=urllib.request.Request(OLLAMA,data=data,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return strip_think(json.loads(r.read().decode()).get("response",""))


# ---------------- Claude-API (Coder) ----------------
_CLAUDE_MODEL=None

def api_key():
    import os
    k=os.environ.get("ANTHROPIC_API_KEY","").strip()
    if not k and API_KEY_FILE.exists():
        k=API_KEY_FILE.read_text(encoding="utf-8-sig").strip()
    if not k or not k.startswith("sk-ant-"):
        raise RuntimeError("Kein gültiger API-Schlüssel in API_KEY.txt (muss mit sk-ant- beginnen).")
    return k

def _api(path,payload=None,timeout=300):
    headers={"x-api-key":api_key(),"anthropic-version":"2023-06-01","content-type":"application/json"}
    data=json.dumps(payload).encode() if payload is not None else None
    req=urllib.request.Request("https://api.anthropic.com"+path,data=data,headers=headers,
                               method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Claude-API HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")

def claude_model():
    """Wählt automatisch das neueste verfügbare Sonnet-Modell (günstig + stark)."""
    global _CLAUDE_MODEL
    if _CLAUDE_MODEL: return _CLAUDE_MODEL
    ids=[m["id"] for m in _api("/v1/models?limit=100",timeout=30).get("data",[])]
    pick=[i for i in ids if "sonnet" in i] or ids
    if not pick: raise RuntimeError("Claude-API liefert keine Modelle.")
    _CLAUDE_MODEL=pick[0]   # Liste ist neueste zuerst
    return _CLAUDE_MODEL

def ask_claude(prompt,timeout=300,max_tokens=16000):
    r=_api("/v1/messages",{"model":claude_model(),"max_tokens":max_tokens,
                           "messages":[{"role":"user","content":prompt}]},timeout=timeout)
    return "".join(b.get("text","") for b in r.get("content",[]) if b.get("type")=="text").strip()

def ask_reviewer_with_retry(model,prompt,label,retries=3,timeout=600):
    last=None
    for attempt in range(1,retries+1):
        try:
            print(f"{label}: Versuch {attempt}/{retries} (Timeout {timeout}s)")
            return ask(model,prompt,timeout=timeout,max_tokens=300)
        except Exception as e:
            last=e
            print(f"{label}: {type(e).__name__}: {e}")
            if attempt < retries:
                print(f"{label}: nur Prüfer wird erneut gestartet; BEST bleibt erhalten.")
    raise last

def context(cwd):
    s=[]
    for p in sorted(cwd.glob("*.py")):
        s.append(f"\n===== FILE: {p.name} =====\n{p.read_text(encoding='utf-8')}\n===== END FILE =====\n")
    return "".join(s)

def reqs(task,base):
    vals=[]
    for pat in [
        r"mindestens\s+(\d+)\s+(?:neue|zusätzliche|zusaetzliche).*?tests?",
        r"(\d+)\s+(?:neue|zusätzliche|zusaetzliche).*?tests?"
    ]:
        vals += [int(x) for x in re.findall(pat,task.lower())]
    # V30: Keine Zahl im Auftrag -> mindestens 1 neuer Test (jede Änderung muss getestet sein).
    new=max(vals) if vals else 1
    return {"baseline_tests":base,"required_new_tests":new,"minimum_total_tests":base+new}

# V26 deliberately avoids JSON and <<<OP>>>. The model returns complete file contents.
# Format:
# ===== FILE: main.py =====
# complete content
# ===== END FILE =====
def parse_files(answer):
    pat=re.compile(r"^===== FILE:\s*([A-Za-z0-9_.-]+)\s*=====\s*\n(.*?)^===== END FILE =====\s*$",
                   re.M|re.S)
    found=pat.findall(answer)
    if not found:
        raise ValueError("Keine vollständigen FILE-Blöcke erkannt")
    result={}
    for name,content in found:
        if not name.endswith(".py") or "/" in name or "\\" in name or ".." in name:
            raise ValueError(f"Ungültiger Dateiname: {name}")
        content=re.sub(r"^\s*```[a-zA-Z]*\s*\n","",content)      # führender ```python
        content=re.sub(r"\n\s*```\s*$","",content.rstrip())      # abschließender ```
        result[name]=content.rstrip()+"\n"
    return result

def apply_files(cwd,files,protected):
    changed=[]
    for name,content in files.items():
        if name in protected:
            raise ValueError(f"Baseline-Test geschützt: {name}")
        ast.parse(content,filename=name)
        (cwd/name).write_text(content,encoding="utf-8")
        changed.append(name)
    return changed

def review(model,role,task,cwd,n,rq):
    prompt=f"""Du bist {role}. Prüfe unabhängig.
AUFTRAG:
{task}
HARTE DATEN: Baseline={rq['baseline_tests']}; neue Tests gefordert={rq['required_new_tests']};
Minimum={rq['minimum_total_tests']}; aktuell grün={n}.
CODE:
{context(cwd)}
Antworte in der ersten Zeile exakt ENTSCHEIDUNG: ZUSTIMMUNG oder ENTSCHEIDUNG: NACHARBEIT.
Danach höchstens 3 Sätze BEFUND. Keine Codeblöcke."""
    return ask_reviewer_with_retry(model,prompt,role)

def approved(s):
    """V30: tolerant. Akzeptiert **ENTSCHEIDUNG: ZUSTIMMUNG**, Punkt am Ende usw.
    Enthält die Entscheidung NACHARBEIT, gilt sie immer als Ablehnung."""
    clean=re.sub(r"[*_`#>]","",strip_think(s))
    m=re.search(r"ENTSCHEIDUNG\s*:\s*(ZUSTIMMUNG|NACHARBEIT)",clean,re.I)
    return bool(m) and m.group(1).upper()=="ZUSTIMMUNG"

def main():
    print("=== KI-AGENT V30 - CODER: CLAUDE-API | PRUEFER: LOKAL ===")
    task=TASK_FILE.read_text(encoding="utf-8-sig").strip()
    syntax(PROJECT)
    ok0,n0,out0=tests(PROJECT)
    print(f"BASELINE: tests={n0} ok={ok0}")
    if not ok0:
        print(out0); return 2
    rq=reqs(task,n0)
    print("ANFORDERUNGS-GATE:",rq)

    protected={p.name for p in PROJECT.glob("test*.py")}
    STATE.mkdir(exist_ok=True)

    # V30: Neuer Auftrag? Dann gehört der alte BEST zu einer anderen Aufgabe -> neu anfangen.
    task_sig=hashlib.sha256(task.encode("utf-8")).hexdigest()
    sig_file=STATE/"auftrag.sha256"
    if BEST.exists() and (not sig_file.exists() or sig_file.read_text().strip()!=task_sig):
        print("NEUER AUFTRAG erkannt: alter Zwischenstand wird verworfen, Start ab aktuellem Projekt.")
        shutil.rmtree(BEST)
    sig_file.write_text(task_sig)

    # RESUME: Never overwrite a valid, better BEST on startup.
    best_n=n0
    if BEST.exists():
        try:
            syntax(BEST)
            bok,bn,bout=tests(BEST)
            if bok and bn >= n0:
                best_n=bn
                print(f"RESUME: vorhandener BEST={best_n} grüne Tests wird weiterverwendet.")
            else:
                print(f"RESUME: vorhandener BEST ungültig/schlechter ({bn}); Baseline wird verwendet.")
                copytree(PROJECT,BEST)
                best_n=n0
        except Exception as e:
            print(f"RESUME: BEST konnte nicht validiert werden ({type(e).__name__}: {e}); Baseline wird verwendet.")
            copytree(PROJECT,BEST)
            best_n=n0
    else:
        copytree(PROJECT,BEST)
        print(f"RESUME: kein BEST vorhanden; Baseline={n0} wird als Startstand gespeichert.")

    feedback=""
    seen=set()

    # If a resumed BEST already meets the hard gate, do not invoke the coder again.
    if best_n >= rq["minimum_total_tests"]:
        print(f"RESUME-GATE: BEST={best_n} erfüllt Minimum {rq['minimum_total_tests']}.")
        print("Coder wird übersprungen; direkte unabhängige Prüfung.")
        try:
            print("KI-PRUEFUNG 1/2 ...")
            r1=review(CODE_REVIEWER,"Code-Prüfer",task,BEST,best_n,rq); print(r1)
            print("KI-PRUEFUNG 2/2 ...")
            r2=review(TASK_REVIEWER,"Auftrags-Prüfer",task,BEST,best_n,rq); print(r2)
        except Exception as e:
            print(f"PRUEFER-STOPP: {type(e).__name__}: {e}")
            print(f"BEST={best_n} bleibt gespeichert. Kein Coding-Neustart.")
            return 6
        if approved(r1) and approved(r2):
            a,na,oa=tests(BEST); b,nb,ob=tests(BEST)
            if a and b and min(na,nb) >= rq["minimum_total_tests"]:
                copytree(BEST,PROJECT)
                print(f"ERFOLG: RESUME-BEST={nb}; beide Prüfer stimmen zu; zwei Wiederholungstests grün; Projekt übernommen.")
                return 0
            print("FINALER WIEDERHOLUNGSTEST FEHLGESCHLAGEN; BEST bleibt erhalten.")
            return 5
        feedback="Prüferfeedback:\n"+r1+"\n"+r2
        print("NACHARBEIT erforderlich; Coder arbeitet ab dem erhaltenen BEST weiter.")

    for cycle in range(1,MAX_CYCLES+1):
        print(f"\n=== ZYKLUS {cycle}/{MAX_CYCLES} | BEST={best_n} ===")
        missing=max(0,rq["minimum_total_tests"]-best_n)
        prompt=f"""Du bist ein autonomer Python-Entwickler.
Arbeite NUR auf dem unten gezeigten aktuellen BEST-Stand.
AUFTRAG:
{task}

Status: {best_n} Tests grün. Minimum: {rq['minimum_total_tests']}. Noch fehlend: {missing}.
Geschützte Baseline-Tests, niemals ausgeben oder ändern: {sorted(protected)}
Letztes Feedback: {feedback or '(keins)'}

Gib KEINE Erklärung, KEIN JSON und KEINE Markdown-Codeblöcke aus.
Gib ausschließlich jede geänderte oder neue Python-Datei VOLLSTÄNDIG so aus:

===== FILE: dateiname.py =====
[vollständiger Python-Dateiinhalt]
===== END FILE =====

Du darfst mehrere FILE-Blöcke liefern. Unveränderte Dateien nicht ausgeben.
Wenn nur Tests fehlen, ändere funktionierenden Produktionscode nicht unnötig.

AKTUELLER BEST-STAND:
{context(BEST)}"""
        try:
            ans=ask_claude(prompt) if CODER=="claude" else ask(CODER,prompt)
            sig=hashlib.sha256(ans.encode()).hexdigest()
            if sig in seen:
                feedback="Identische Antwort bereits versucht. Liefere eine andere vollständige Dateiänderung."
                print("DUPLIKAT VERWORFEN"); continue
            seen.add(sig)
            files=parse_files(ans)
            with tempfile.TemporaryDirectory() as td:
                cand=Path(td)/"candidate"; copytree(BEST,cand)
                changed=apply_files(cand,files,protected)
                syntax(cand)
                ok,n,out=tests(cand)
                print(f"KANDIDAT: tests={n} ok={ok}; geändert={changed}")
                if not ok:
                    feedback="Tests rot. Repariere gezielt auf Basis des unveränderten BEST:\n"+out[-4000:]
                    print(f"ROLLBACK: BEST={best_n} bleibt."); continue
                if n>best_n:
                    old=best_n; copytree(cand,BEST); best_n=n
                    print(f"BEST AKTUALISIERT: {old} -> {best_n}. Nächster Zyklus arbeitet ab {best_n}.")
                elif n==best_n:
                    # Same test count can still be a legitimate implementation repair.
                    # Preserve only after gate is already met; otherwise require measurable progress.
                    if best_n>=rq["minimum_total_tests"]:
                        copytree(cand,BEST)
                        print(f"BEST CODE AKTUALISIERT bei weiterhin {best_n} grünen Tests.")
                    else:
                        feedback=f"Keine messbare Verbesserung. BEST bleibt {best_n}; Ziel {rq['minimum_total_tests']}."
                        print("KEINE VERBESSERUNG:",feedback); continue
                else:
                    feedback=f"Kandidat hat nur {n} grüne Tests; BEST bleibt {best_n}."
                    print("KANDIDAT VERWORFEN:",feedback); continue

                if best_n<rq["minimum_total_tests"]:
                    feedback=(f"Zwischenstand ist grün und gespeichert. Es fehlen noch "
                              f"{rq['minimum_total_tests']-best_n} Tests bis zum Hard Gate.")
                    print("ZWISCHENSTAND GESPEICHERT:",feedback); continue

                print("KI-PRUEFUNG 1/2 ...")
                try:
                    r1=review(CODE_REVIEWER,"Code-Prüfer",task,BEST,best_n,rq); print(r1)
                    print("KI-PRUEFUNG 2/2 ...")
                    r2=review(TASK_REVIEWER,"Auftrags-Prüfer",task,BEST,best_n,rq); print(r2)
                except Exception as e:
                    print(f"PRUEFER-STOPP: {type(e).__name__}: {e}")
                    print(f"BEST={best_n} bleibt gespeichert. Kein neuer Coding-Zyklus wegen Prüfer-Timeout.")
                    return 6
                if not(approved(r1) and approved(r2)):
                    feedback="Prüferfeedback:\n"+r1+"\n"+r2
                    print("NACHARBEIT; BEST BLEIBT ERHALTEN."); continue

                # Two final test runs before committing.
                a,na,oa=tests(BEST); b,nb,ob=tests(BEST)
                if not(a and b and min(na,nb)>=rq["minimum_total_tests"]):
                    print("FINALER WIEDERHOLUNGSTEST FEHLGESCHLAGEN; Projekt bleibt unverändert.")
                    return 5
                copytree(BEST,PROJECT)
                print(f"\nERFOLG: {nb} Tests grün; beide Prüfer stimmen zu; Projekt übernommen.")
                return 0
        except Exception as e:
            feedback=f"{type(e).__name__}: {e}"
            print("VERSUCH VERWORFEN:",feedback)
            print(f"BEST={best_n} bleibt unverändert.")

    print(f"STOPP nach {MAX_CYCLES} Zyklen. BEST={best_n} bleibt in agent_state_v26/best.")
    return 1

if __name__=="__main__":
    raise SystemExit(main())
