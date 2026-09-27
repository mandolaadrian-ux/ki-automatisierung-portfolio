import unittest
from classifier import classify_email, determine_priority
from email_parser import parse_email
from main import process_email


class ReklamationClassificationTests(unittest.TestCase):
    def test_reklamation_keyword_basic(self):
        msg = "Betreff: Reklamation\nWir möchten die Ware reklamieren."
        self.assertEqual(process_email(msg)["klassifizierung"], "reklamation")

    def test_reklamation_keyword_plural_variant(self):
        msg = "Ich habe mehrere Reklamationen zu Ihrer Lieferung."
        self.assertEqual(process_email(msg)["klassifizierung"], "reklamation")

    def test_reklamation_keyword_defekt(self):
        msg = "Das Gerät ist defekt angekommen."
        self.assertEqual(process_email(msg)["klassifizierung"], "reklamation")

    def test_reklamation_keyword_defekte_variant(self):
        msg = "Wir haben mehrere defekte Artikel erhalten."
        self.assertEqual(process_email(msg)["klassifizierung"], "reklamation")

    def test_reklamation_keyword_kaputt(self):
        msg = "Der Artikel kam kaputt bei uns an."
        self.assertEqual(process_email(msg)["klassifizierung"], "reklamation")

    def test_reklamation_keyword_beschaedigt(self):
        msg = "Die Verpackung war beschädigt."
        self.assertEqual(process_email(msg)["klassifizierung"], "reklamation")

    def test_reklamation_keyword_falsch_geliefert(self):
        msg = "Es wurde die falsche Ware falsch geliefert."
        self.assertEqual(process_email(msg)["klassifizierung"], "reklamation")

    def test_reklamation_keyword_fehlerhaft(self):
        msg = "Die Rechnung war fehlerhaft."
        self.assertEqual(process_email(msg)["klassifizierung"], "reklamation")

    def test_reklamation_keyword_mangel(self):
        msg = "Wir stellen einen Mangel an der Ware fest."
        self.assertEqual(process_email(msg)["klassifizierung"], "reklamation")

    def test_reklamation_keyword_ruecksendung(self):
        msg = "Bitte veranlassen Sie eine Rücksendung."
        self.assertEqual(process_email(msg)["klassifizierung"], "reklamation")

    def test_reklamation_keyword_umtausch(self):
        msg = "Wir bitten um einen Umtausch des Artikels."
        self.assertEqual(process_email(msg)["klassifizierung"], "reklamation")

    def test_case_insensitive_reklamation(self):
        msg = "DEFEKT UND KAPUTT ANGEKOMMEN"
        self.assertEqual(process_email(msg)["klassifizierung"], "reklamation")


class TerminanfrageClassificationTests(unittest.TestCase):
    def test_terminanfrage_keyword_termin(self):
        msg = "Können wir einen Termin vereinbaren?"
        self.assertEqual(process_email(msg)["klassifizierung"], "terminanfrage")

    def test_terminanfrage_keyword_besprechung(self):
        msg = "Ich schlage eine Besprechung nächste Woche vor."
        self.assertEqual(process_email(msg)["klassifizierung"], "terminanfrage")

    def test_terminanfrage_keyword_treffen(self):
        msg = "Lassen Sie uns ein Treffen ausmachen."
        self.assertEqual(process_email(msg)["klassifizierung"], "terminanfrage")

    def test_terminanfrage_keyword_rueckruf(self):
        msg = "Ich bitte um einen Rückruf heute Nachmittag."
        self.assertEqual(process_email(msg)["klassifizierung"], "terminanfrage")

    def test_terminanfrage_keyword_meeting(self):
        msg = "Sollen wir ein Meeting ansetzen?"
        self.assertEqual(process_email(msg)["klassifizierung"], "terminanfrage")

    def test_terminanfrage_keyword_terminvorschlag(self):
        msg = "Anbei mein Terminvorschlag für kommende Woche."
        self.assertEqual(process_email(msg)["klassifizierung"], "terminanfrage")

    def test_terminanfrage_keyword_kalender(self):
        msg = "Bitte tragen Sie das in Ihren Kalender ein."
        self.assertEqual(process_email(msg)["klassifizierung"], "terminanfrage")

    def test_liefertermin_field_does_not_trigger_terminanfrage(self):
        msg = "Liefertermin: übermorgen"
        # "Liefertermin" darf nicht als eigenständiges "Termin" erkannt werden
        self.assertNotEqual(process_email(msg)["klassifizierung"], "terminanfrage")


class OrderingAndPriorityTests(unittest.TestCase):
    def test_complete_offer_overrides_reklamation(self):
        msg = "Kunde: A\nProdukt: B\nMenge: 5\nDas Produkt war defekt."
        self.assertEqual(process_email(msg)["klassifizierung"], "angebotsanfrage")

    def test_complete_offer_overrides_terminanfrage(self):
        msg = "Kunde: A\nProdukt: B\nMenge: 5\nBitte um einen Termin."
        self.assertEqual(process_email(msg)["klassifizierung"], "angebotsanfrage")

    def test_reklamation_before_terminanfrage_order(self):
        msg = "Bitte um Rückruf, da das Gerät defekt ist."
        self.assertEqual(process_email(msg)["klassifizierung"], "reklamation")

    def test_reklamation_priority_mittel(self):
        msg = "Die Ware ist beschädigt angekommen."
        result = process_email(msg)
        self.assertEqual(result["klassifizierung"], "reklamation")
        self.assertEqual(result["prioritaet"], "mittel")
        self.assertTrue(result["prioritaet_grund"])

    def test_reklamation_priority_hoch_when_urgent(self):
        msg = "Betreff: dringend\nDas Gerät ist defekt."
        result = process_email(msg)
        self.assertEqual(result["klassifizierung"], "reklamation")
        self.assertEqual(result["prioritaet"], "hoch")

    def test_reklamation_priority_reason_mentions_reklamation(self):
        priority, reason = determine_priority(
            {"subject": "", "body": "Der Artikel ist kaputt."}
        )
        self.assertEqual(priority, "mittel")
        self.assertIn("Reklamation", reason)


class RobustnessNewClassesTests(unittest.TestCase):
    def test_empty_input_no_crash_new_classes(self):
        result = process_email("")
        self.assertEqual(result["klassifizierung"], "sonstiges")

    def test_classify_email_reklamation_direct_dict(self):
        data = {"subject": "", "body": "Umtausch gewünscht", "kunde": None,
                "produkt": None, "menge": None, "liefertermin": None}
        self.assertEqual(classify_email(data), "reklamation")

    def test_classify_email_terminanfrage_direct_dict(self):
        data = {"subject": "", "body": "Wir vereinbaren ein Meeting", "kunde": None,
                "produkt": None, "menge": None, "liefertermin": None}
        self.assertEqual(classify_email(data), "terminanfrage")

    def test_parse_email_reklamation_still_parses_fields(self):
        msg = "Kunde: A\nDas Produkt ist defekt."
        data = parse_email(msg)
        self.assertEqual(data["kunde"], "A")
        self.assertEqual(classify_email(data), "reklamation")

    def test_none_input_reklamation_no_crash(self):
        # sicherstellen, dass ungewöhnliche Eingaben nicht abstürzen
        data = parse_email(None)
        self.assertEqual(classify_email(data), "sonstiges")


if __name__ == "__main__":
    unittest.main()
