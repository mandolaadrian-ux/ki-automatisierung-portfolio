import unittest
from main import process_email


class PriorityV21Tests(unittest.TestCase):
    def test_urgent_word(self):
        self.assertEqual(process_email("Betreff: DRINGEND")["prioritaet"], "hoch")

    def test_asap(self):
        self.assertEqual(process_email("Subject: ASAP")["prioritaet"], "hoch")

    def test_tomorrow(self):
        self.assertEqual(process_email("Liefertermin: morgen")["prioritaet"], "hoch")

    def test_today(self):
        self.assertEqual(process_email("Liefertermin: HEUTE")["prioritaet"], "hoch")

    def test_short_notice(self):
        self.assertEqual(process_email("Betreff: kurzfristig benötigt")["prioritaet"], "hoch")

    def test_complete_medium(self):
        msg = "Kunde: Alpha\nProdukt: Karton\nMenge: 50"
        self.assertEqual(process_email(msg)["prioritaet"], "mittel")

    def test_complete_mixed_case(self):
        msg = "KUNDE: Alpha\npRoDuKt: Karton\nMENGE: 50"
        self.assertEqual(process_email(msg)["prioritaet"], "mittel")

    def test_missing_customer_low(self):
        self.assertEqual(process_email("Produkt: A\nMenge: 3")["prioritaet"], "niedrig")

    def test_missing_product_low(self):
        self.assertEqual(process_email("Kunde: A\nMenge: 3")["prioritaet"], "niedrig")

    def test_missing_quantity_low(self):
        self.assertEqual(process_email("Kunde: A\nProdukt: B")["prioritaet"], "niedrig")

    def test_other_message_low(self):
        self.assertEqual(process_email("Hallo, vielen Dank.")["prioritaet"], "niedrig")

    def test_reason_nonempty(self):
        self.assertTrue(process_email("Hallo")["prioritaet_grund"])

    def test_urgent_overrides_incomplete(self):
        self.assertEqual(process_email("Betreff: eilig\nProdukt: B")["prioritaet"], "hoch")

    def test_classification_preserved(self):
        msg = "Kunde: A\nProdukt: B\nMenge: 3"
        self.assertEqual(process_email(msg)["klassifizierung"], "angebotsanfrage")


if __name__ == "__main__":
    unittest.main()
