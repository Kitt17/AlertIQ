import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
DB_PATH = Path(__file__).parent / 'alertiq.db'


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def create_database():
    with get_connection() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS operators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            operator_id INTEGER NOT NULL REFERENCES operators(id)
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL REFERENCES clients(id),
            title TEXT NOT NULL, description TEXT, due_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            priority TEXT NOT NULL DEFAULT 'Low'
        );
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT UNIQUE, sender TEXT NOT NULL,
            recipient TEXT NOT NULL, subject TEXT NOT NULL,
            body TEXT NOT NULL, received_at TEXT DEFAULT CURRENT_TIMESTAMP,
            client_id INTEGER REFERENCES clients(id),
            task_id INTEGER REFERENCES tasks(id), processed INTEGER DEFAULT 0,
            sender_name TEXT
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_id INTEGER NOT NULL REFERENCES operators(id),
            task_id INTEGER REFERENCES tasks(id),
            email_id INTEGER REFERENCES emails(id),
            message TEXT NOT NULL, priority TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            snoozed_until TEXT
        );
        ''')
        for table, column, definition in (
            ('emails', 'sender_name', 'TEXT'),
            ('notifications', 'snoozed_until', 'TEXT'),
        ):
            cols = {row['name'] for row in conn.execute(f'PRAGMA table_info({table})')}
            if column not in cols:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS one_notification_per_email ON notifications(email_id) WHERE email_id IS NOT NULL')
        conn.commit()


def ensure_demo_operator():
    """Map the local demo login to the Gmail inbox actually being synced."""
    address = (os.getenv('GMAIL_ADDRESS') or 'operator@alertiq.com').strip().lower()
    with get_connection() as conn:
        operator = conn.execute('SELECT id FROM operators WHERE lower(email)=?', (address,)).fetchone()
        if operator:
            return operator['id']
        old = conn.execute("SELECT id FROM operators WHERE lower(email)='operator@alertiq.com'").fetchone()
        if old and address != 'operator@alertiq.com':
            conn.execute('UPDATE operators SET email=?, name=? WHERE id=?', (address, 'Kirtna', old['id']))
            return old['id']
        cursor = conn.execute('INSERT INTO operators(name,email) VALUES (?,?)', ('Kirtna', address))
        return cursor.lastrowid
