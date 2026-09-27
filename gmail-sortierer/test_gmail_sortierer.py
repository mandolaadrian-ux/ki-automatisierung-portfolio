"""Tests ohne Internet, ohne Gmail-Konto, ohne Ollama (alles simuliert)."""
import base64, unittest
import gmail_sortierer as g


def b64(t): return base64.urlsafe_b64encode(t.encode()).decode().rstrip("=")


def msg(mid, subject, sender="a@b.de", text="Hallo", mime="text/plain"):
    return {"id": mid, "snippet": text[:50], "payload": {
        "headers": [{"name": "Subject", "value": subject}, {"name": "From", "value": sender}],
        "mimeType": "multipart/alternative",
        "parts": [{"mimeType": mime, "body": {"data": b64(text)}}]}}


class FakeGmail:
    def __init__(self, mails, labels=None, conflict=()):
        self.mails = {m["id"]: m for m in mails}
        self.label_list = labels or []
        self.conflict = set(conflict)
        self.created, self.modified = [], []
    def labels(self): return list(self.label_list)
    def create_label(self, name):
        if name in self.conflict: raise RuntimeError("Gmail HTTP 409: Label name exists or conflicts")
        if name in getattr(self, "reserved", ()): raise RuntimeError('Gmail HTTP 400: {"message": "Invalid label name"}')
        l = {"id": "L_" + name, "name": name}; self.label_list.append(l); self.created.append(name); return l
    def search(self, q, limit):
        open_ids = [i for i in self.mails if not any(m == i for m, _ in self.modified)]
        return open_ids[:limit], len(open_ids)
    def get(self, i): return self.mails[i]
    def add_labels(self, i, ids): self.modified.append((i, ids))


class TestKategorie(unittest.TestCase):
    def test_exakt(self): self.assertEqual(g.parse_category("rechnungen"), "rechnungen")
    def test_gross_und_punkt(self): self.assertEqual(g.parse_category("Jobangebote."), "jobangebote")
    def test_einzahl(self): self.assertEqual(g.parse_category("Rechnung"), "rechnungen")
    def test_neue_kategorien(self):
        for w in ("zugangsdaten", "werbung", "spam"): self.assertEqual(g.parse_category(w), w)
    def test_fett(self): self.assertEqual(g.parse_category("**wichtig**"), "wichtig")
    def test_mit_denkblock(self): self.assertEqual(g.parse_category("<think>rechnung?</think>sonstiges"), "sonstiges")
    def test_unklar(self): self.assertIsNone(g.parse_category("keine Ahnung"))
    def test_mehrdeutig(self): self.assertIsNone(g.parse_category("vielleicht wichtig oder sonstiges"))
    def test_beginnt_eindeutig(self): self.assertEqual(g.parse_category("wichtig, weil Frist"), "wichtig")


class TestRegeln(unittest.TestCase):
    def test_rechnung(self): self.assertEqual(g.rule_classify("shop@x.de", "Ihre Rechnung Nr. 5", ""), "rechnungen")
    def test_job(self): self.assertEqual(g.rule_classify("jobs@stepstone.de", "Neue Stellenangebote", ""), "jobangebote")
    def test_wichtig(self): self.assertEqual(g.rule_classify("amt@x.de", "Frist bis Freitag", ""), "wichtig")
    def test_werbung(self): self.assertEqual(g.rule_classify("news@x.de", "Newsletter Mai", ""), "werbung")
    def test_sonstiges(self): self.assertEqual(g.rule_classify("oma@x.de", "Fotos vom Wochenende", ""), "sonstiges")
    def test_zugangsdaten(self):
        self.assertEqual(g.rule_classify("google", "Sie haben einige Google-Kontodaten mit 7pass.de geteilt", ""), "zugangsdaten")
    def test_zugangsdaten_vor_werbung(self):
        self.assertEqual(g.rule_classify("x", "Dein Bestätigungscode", "Angebot"), "zugangsdaten")
    def test_lg_beendigung(self):
        self.assertEqual(g.rule_classify("LG", "[LG-Konto] Benachrichtigung über die Beendigung", ""), "zugangsdaten")
    def test_spam(self): self.assertEqual(g.rule_classify("x", "Sie haben gewonnen!", ""), "spam")


class TestKlassifizierung(unittest.TestCase):
    MAIL = {"from": "a@b.de", "subject": "Ihre Rechnung", "text": "Betrag 20 EUR"}
    def test_ki_antwort(self):
        self.assertEqual(g.classify(self.MAIL, ask=lambda p: "jobangebote"), ("jobangebote", "KI"))
    def test_ollama_aus_regel_ersatz(self):
        def boom(p): raise ConnectionError("Ollama aus")
        self.assertEqual(g.classify(self.MAIL, ask=boom), ("rechnungen", "Regel"))
    def test_unklare_ki_regel_ersatz(self):
        self.assertEqual(g.classify(self.MAIL, ask=lambda p: "hmm"), ("rechnungen", "Regel"))
    def test_prompt_enthaelt_betreff(self):
        seen = []
        g.classify(self.MAIL, ask=lambda p: seen.append(p) or "sonstiges")
        self.assertIn("Ihre Rechnung", seen[0])


class TestMailLesen(unittest.TestCase):
    def test_plaintext(self):
        m = g.parse_message(msg("1", "Hi", text="Guten Tag\nWelt"))
        self.assertEqual((m["subject"], m["text"]), ("Hi", "Guten Tag Welt"))
    def test_html_ohne_tags(self):
        m = g.parse_message(msg("1", "Hi", text="<p>Hallo&nbsp;<b>Welt</b></p><style>x{}</style>", mime="text/html"))
        self.assertEqual(m["text"], "Hallo Welt")
    def test_ohne_betreff(self):
        m = g.parse_message({"id": "1", "snippet": "s", "payload": {"headers": []}})
        self.assertEqual((m["subject"], m["text"]), ("(kein Betreff)", "s"))


class TestLabels(unittest.TestCase):
    def test_fehlende_werden_angelegt(self):
        gm = FakeGmail([])
        ids = g.ensure_labels(gm)
        self.assertEqual(set(gm.created), {"Wichtig KI-Sortiert", "Jobangebote", "Rechnungen", "Zugangsdaten",
                                           "Werbung", "Spam", "KI-Geprüft"})
        self.assertEqual(len(ids), 7)
        self.assertNotIn("sonstiges", ids)
    def test_vorhandene_werden_genutzt(self):
        gm = FakeGmail([], labels=[{"id": "X", "name": "rechnungen"}])
        self.assertEqual(g.ensure_labels(gm)["rechnungen"], "X")
        self.assertNotIn("Rechnungen", gm.created)
    def test_konflikt_mit_systemlabel(self):
        gm = FakeGmail([], conflict={"Werbung"})
        self.assertEqual(g.ensure_labels(gm)["werbung"], "L_KI-Werbung")
    def test_reservierter_name_wichtig(self):
        gm = FakeGmail([]); gm.reserved = {"Spam"}
        self.assertEqual(g.ensure_labels(gm)["spam"], "L_KI-Spam")
    def test_andere_fehler_brechen_ab(self):
        gm = FakeGmail([])
        gm.create_label = lambda n: (_ for _ in ()).throw(RuntimeError("Gmail HTTP 403: forbidden"))
        with self.assertRaises(RuntimeError): g.ensure_labels(gm)
    def test_probelauf_legt_nichts_an(self):
        gm = FakeGmail([])
        g.ensure_labels(gm, create=False)
        self.assertEqual(gm.created, [])


class TestDurchlauf(unittest.TestCase):
    MAILS = [msg("1", "Rechnung 42"), msg("2", "Stellenangebot Python"), msg("3", "Newsletter")]
    ANSWERS = {"Rechnung 42": "rechnungen", "Stellenangebot Python": "jobangebote", "Newsletter": "sonstiges"}
    def ask(self, prompt):
        return next(v for k, v in self.ANSWERS.items() if k in prompt)

    def test_probelauf_aendert_nichts(self):
        gm = FakeGmail(self.MAILS)
        counts = g.run(gm, probelauf=True, ask=self.ask, log=lambda *a: None)
        self.assertEqual(gm.modified, []); self.assertEqual(gm.created, [])
        self.assertEqual(counts["rechnungen"], 1)

    def test_echt_setzt_kategorie_und_fertig_label(self):
        gm = FakeGmail(self.MAILS)
        g.run(gm, probelauf=False, ask=self.ask, log=lambda *a: None)
        self.assertEqual(dict(gm.modified), {"1": ["L_Rechnungen", "L_KI-Geprüft"],
                                             "2": ["L_Jobangebote", "L_KI-Geprüft"],
                                             "3": ["L_KI-Geprüft"]})      # sonstiges: nur Prüf-Label

    def test_schon_gepruefte_mail_uebersprungen(self):
        mails = [dict(msg("1", "Rechnung 42"), labelIds=["L_KI-Geprüft"])]
        gm = FakeGmail(mails, labels=[{"id": "L_KI-Geprüft", "name": "KI-Geprüft"}])
        g.run(gm, probelauf=False, ask=self.ask, log=lambda *a: None)
        self.assertEqual(gm.modified, [])

    def test_kaputte_mail_wird_uebersprungen(self):
        gm = FakeGmail(self.MAILS)
        orig = gm.get
        gm.get = lambda i: (_ for _ in ()).throw(RuntimeError("kaputt")) if i == "2" else orig(i)
        out = []
        g.run(gm, probelauf=False, ask=self.ask, log=out.append)
        self.assertEqual(sorted(i for i, _ in gm.modified), ["1", "3"])
        self.assertTrue(any("übersprungen" in l for l in out))

    def test_nur_hinzufuegen_nie_loeschen(self):
        self.assertFalse(hasattr(g.Gmail, "delete"))
        self.assertNotIn("removeLabelIds", open(g.__file__, encoding="utf-8").read())
        self.assertNotIn("/send", open(g.__file__, encoding="utf-8").read())


class TestAnmeldung(unittest.TestCase):
    def test_desktop_client_freier_port(self):
        self.assertRegex(g.pick_redirect("installed", {}), r"^http://127\.0\.0\.1:\d+/$")
    def test_web_client_n8n_port_nicht_nutzbar(self):
        with self.assertRaises(SystemExit):
            g.pick_redirect("web", {"redirect_uris": ["http://localhost:5678/rest/oauth2-credential/callback"]})
    def test_web_client_mit_eigenem_port(self):
        uris = ["http://localhost:5678/rest/oauth2-credential/callback", "http://localhost:8765/"]
        self.assertEqual(g.pick_redirect("web", {"redirect_uris": uris}), "http://localhost:8765/")


class TestZugangsdatei(unittest.TestCase):
    def test_desktop_datei_wird_bevorzugt(self):
        import json, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); sub = root / "Gmail-Sortierer"; sub.mkdir()
            (root / "client_secret_2aaa.json").write_text(json.dumps({"web": {"client_id": "n8n"}}))
            (root / "client_secret_bbbb.json").write_text(json.dumps({"installed": {"client_id": "desk"}}))
            old = g.HERE; g.HERE = sub
            try:
                self.assertEqual(g.load_client(), ("installed", {"client_id": "desk"}))
            finally:
                g.HERE = old


if __name__ == "__main__":
    unittest.main()
