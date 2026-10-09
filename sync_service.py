from gmail_service import fetch_and_save_emails
from followup_logic import process_followups


def sync_emails():
    saved = fetch_and_save_emails()
    created, skipped = process_followups()
    return {'saved': saved, 'notifications': created, 'skipped': skipped}
