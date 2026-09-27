from classifier import classify_email, determine_priority, is_urgent
from email_parser import parse_email
from json_formatter import to_json


def process_email(email_text):
    data = parse_email(email_text)
    data["klassifizierung"] = classify_email(data)
    priority, reason = determine_priority(data)
    data["prioritaet"] = priority
    data["prioritaet_grund"] = reason
    data["ist_dringend"] = is_urgent(data)
    return data


def process_email_json(email_text):
    return to_json(process_email(email_text))


if __name__ == "__main__":
    sample = """Betreff: Angebot dringend
Kunde: Demo GmbH
Produkt: Papier
Menge: 1000
Liefertermin: morgen"""
    print(process_email_json(sample))
