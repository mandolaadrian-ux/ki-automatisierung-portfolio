import unittest
from email_parser import parse_email
from classifier import classify_email, determine_priority, is_urgent
from main import process_email


class ExtendedUrgencyTests(unittest.TestCase):
    def test_urgent_synonym_notfall(self):
        self.assertEqual(process_email("Betreff: Notfall Bestellung")["prioritaet"], "hoch")

    def test_urgent_synonym_express(self):
        self.assertEqual(process_email("Betreff: Express Lieferung benötigt")["prioritaet"], "hoch")

    def test_urgent_synonym_umgehend(self):
        self.assertEqual(process_email("Bitte umgehend bearbeiten")["prioritaet"], "hoch")

    def test_urgent_synonym_zeitnah(self):
        self.assertEqual(process_email("Wir brauchen das zeitnah")["prioritaet"], "hoch")

    def test_urgent_uebermorgen_unicode(self):
        self.assertEqual(process_email("Liefertermin: übermorgen")["prioritaet"], "hoch")


class ExplicitPriorityOverrideTests(unittest.TestCase):
    def test_explicit_priority_hoch_overrides_complete(self):
        msg = (
            "Betreff: Anfrage\nKunde: A\nProdukt: B\nMenge: 5\n"
            "Priorität: hoch"
        )
        self.assertEqual(process_email(msg)["prioritaet"], "hoch")

    def test_explicit_priority_low_overrides_complete(self):
        msg = "Kunde: A\nProdukt: B\nMenge: 5\nPriority: low"
        self.assertEqual(process_email(msg)["prioritaet"], "niedrig")

    def test_explicit_priority_mittel_overrides_urgent(self):
        msg = (
            "Betreff: dringend\nKunde: A\nProdukt: B\nMenge: 5\n"
            "Priorität: mittel"
        )
        self.assertEqual(process_email(msg)["prioritaet"], "mittel")


class FieldSynonymTests(unittest.TestCase):
    def test_field_synonym_firma(self):
        self.assertEqual(parse_email("Firma: Acme AG")["kunde"], "Acme AG")

    def test_field_synonym_artikel(self):
        self.assertEqual(parse_email("Artikel: Schrauben")["produkt"], "Schrauben")

    def test_field_synonym_anzahl(self):
        self.assertEqual(parse_email("Anzahl: 42")["menge"], 42)

    def test_field_synonym_lieferdatum(self):
        self.assertEqual(
            parse_email("Lieferdatum: 2030-01-01")["liefertermin"], "2030-01-01"
        )

    def test_english_field_synonyms_classification(self):
        msg = "Customer: A\nProduct: B\nQuantity: 5"
        data = parse_email(msg)
        self.assertEqual(classify_email(data), "angebotsanfrage")


class QuantityParsingTests(unittest.TestCase):
    def test_quantity_thousands_separator(self):
        self.assertEqual(parse_email("Menge: 1.000")["menge"], 1000)

    def test_quantity_comma_separator(self):
        self.assertEqual(parse_email("Menge: 2,500")["menge"], 2500)


class RobustnessTests(unittest.TestCase):
    def test_parse_email_none_input(self):
        data = parse_email(None)
        self.assertEqual(data["body"], "")
        self.assertEqual(data["subject"], "")
        self.assertIsNone(data["kunde"])

    def test_parse_email_non_string_input(self):
        data = parse_email(12345)
        self.assertEqual(data["body"], "12345")
        self.assertIsNone(data["kunde"])

    def test_classify_email_none_input(self):
        self.assertEqual(classify_email(None), "sonstiges")

    def test_classify_email_non_dict_input(self):
        self.assertEqual(classify_email(123), "sonstiges")

    def test_determine_priority_non_dict_input(self):
        priority, reason = determine_priority("kein dict")
        self.assertEqual(priority, "niedrig")
        self.assertTrue(reason)

    def test_is_urgent_empty_dict(self):
        self.assertFalse(is_urgent({}))

    def test_is_urgent_non_dict(self):
        self.assertFalse(is_urgent(None))

    def test_determine_priority_missing_keys(self):
        priority, reason = determine_priority({"produkt": "x"})
        self.assertEqual(priority, "niedrig")
        self.assertTrue(reason)


class NewFieldTests(unittest.TestCase):
    def test_ist_dringend_field_present_false(self):
        data = process_email("Hallo, alles gut.")
        self.assertIn("ist_dringend", data)
        self.assertFalse(data["ist_dringend"])

    def test_ist_dringend_field_present_true(self):
        data = process_email("Betreff: dringend")
        self.assertIn("ist_dringend", data)
        self.assertTrue(data["ist_dringend"])

    def test_existing_fields_preserved(self):
        msg = "Kunde: A\nProdukt: B\nMenge: 3"
        data = process_email(msg)
        for key in (
            "subject", "body", "kunde", "produkt", "menge",
            "liefertermin", "klassifizierung", "prioritaet",
            "prioritaet_grund", "ist_dringend",
        ):
            self.assertIn(key, data)


if __name__ == "__main__":
    unittest.main()
