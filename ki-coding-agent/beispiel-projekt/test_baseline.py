import unittest
from email_parser import parse_email
from classifier import classify_email
from main import process_email


class BaselineTests(unittest.TestCase):
    def test_parse_customer(self):
        self.assertEqual(parse_email("Kunde: Demo GmbH")["kunde"], "Demo GmbH")

    def test_parse_product(self):
        self.assertEqual(parse_email("Produkt: Papier")["produkt"], "Papier")

    def test_parse_quantity(self):
        self.assertEqual(parse_email("Menge: 120")["menge"], 120)

    def test_parse_delivery(self):
        self.assertEqual(parse_email("Liefertermin: Freitag")["liefertermin"], "Freitag")

    def test_parse_subject(self):
        self.assertEqual(parse_email("Betreff: Anfrage")["subject"], "Anfrage")

    def test_missing_customer(self):
        self.assertIsNone(parse_email("Produkt: Papier")["kunde"])

    def test_missing_product(self):
        self.assertIsNone(parse_email("Kunde: A")["produkt"])

    def test_missing_quantity(self):
        self.assertIsNone(parse_email("Kunde: A")["menge"])

    def test_complete_is_offer(self):
        d = {"kunde": "A", "produkt": "B", "menge": 1}
        self.assertEqual(classify_email(d), "angebotsanfrage")

    def test_incomplete_is_other(self):
        d = {"kunde": "A", "produkt": None, "menge": 1}
        self.assertEqual(classify_email(d), "sonstiges")

    def test_process_keeps_customer(self):
        self.assertEqual(process_email("Kunde: A")["kunde"], "A")

    def test_process_keeps_product(self):
        self.assertEqual(process_email("Produkt: B")["produkt"], "B")

    def test_process_keeps_quantity(self):
        self.assertEqual(process_email("Menge: 5")["menge"], 5)

    def test_process_has_classification(self):
        self.assertIn("klassifizierung", process_email("Hallo"))

    def test_process_has_priority(self):
        self.assertIn("prioritaet", process_email("Hallo"))

    def test_process_has_priority_reason(self):
        self.assertIn("prioritaet_grund", process_email("Hallo"))

    def test_case_insensitive_customer(self):
        self.assertEqual(parse_email("KUNDE: A")["kunde"], "A")

    def test_case_insensitive_product(self):
        self.assertEqual(parse_email("pRoDuKt: B")["produkt"], "B")

    def test_case_insensitive_quantity(self):
        self.assertEqual(parse_email("MENGE: 9")["menge"], 9)

    def test_empty_is_other(self):
        self.assertEqual(process_email("")["klassifizierung"], "sonstiges")

    def test_empty_low_priority(self):
        self.assertEqual(process_email("")["prioritaet"], "niedrig")

    def test_complete_medium_priority(self):
        msg = "Kunde: A\nProdukt: B\nMenge: 2"
        self.assertEqual(process_email(msg)["prioritaet"], "mittel")


if __name__ == "__main__":
    unittest.main()
