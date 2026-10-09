import imaplib
import email
import os
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from datetime import datetime, timezone, timedelta
MYT = timezone(timedelta(hours=8))
from dotenv import load_dotenv
from database import get_connection

load_dotenv()


def decode_text(value):
    if not value:
        return ''
    try:
        return str(make_header(decode_header(value)))
    except (UnicodeError, ValueError):
        return str(value)


def get_email_body(message):
    for part in message.walk():
        if part.get_content_type() != 'text/plain' or part.get_content_disposition() == 'attachment':
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or 'utf-8'
        try:
            return payload.decode(charset, errors='replace')
        except LookupError:
            return payload.decode('utf-8', errors='replace')
    return '[No plain-text body available]'


def fetch_and_save_emails():
    address = (os.getenv('GMAIL_ADDRESS') or '').strip().lower()
    password = os.getenv('GMAIL_APP_PASSWORD')
    if not address or not password:
        raise RuntimeError('Missing Gmail credentials in .env')
    saved = 0
    mailbox = imaplib.IMAP4_SSL('imap.gmail.com', 993)
    try:
        mailbox.login(address, password)
        status, _ = mailbox.select('INBOX', readonly=True)
        if status != 'OK':
            raise RuntimeError('Cannot open Gmail inbox')
        status, data = mailbox.uid('search', None, 'ALL')
        if status != 'OK':
            raise RuntimeError('Cannot search Gmail inbox')
        # User-requested limit: newest two inbox messages per sync.
        uids = data[0].split()[-2:] if data and data[0] else []
        with get_connection() as conn:
            for uid in uids:
                status, records = mailbox.uid('fetch', uid, '(RFC822)')
                if status != 'OK':
                    continue
                raw = next((item[1] for item in records if isinstance(item, tuple)), None)
                if not raw:
                    continue
                message = email.message_from_bytes(raw)
                sender_name, sender = parseaddr(decode_text(message.get('From')))
                if not sender:
                    continue
                # The configured inbox is the actual receiving operator's mailbox.
                recipient = address
                subject = decode_text(message.get('Subject')) or '(No subject)'
                received = datetime.now(MYT)
                if message.get('Date'):
                    try:
                        received = parsedate_to_datetime(message['Date']).astimezone(MYT)
                    except (ValueError, TypeError, OverflowError):
                        pass
                cursor = conn.execute('''
                    INSERT OR IGNORE INTO emails
                    (message_id,sender,sender_name,recipient,subject,body,received_at,processed)
                    VALUES (?,?,?,?,?,?,?,0)
                ''', (f'{address}:{uid.decode()}', sender.strip().lower(), sender_name.strip() or None,
                      recipient, subject, get_email_body(message), received.strftime('%Y-%m-%d %H:%M:%S')))
                saved += int(cursor.rowcount == 1)
            conn.commit()
        return saved
    finally:
        try:
            mailbox.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
