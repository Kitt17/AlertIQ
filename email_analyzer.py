from datetime import datetime, timedelta, timezone
import json
import re

from database import get_connection
from gemini_service import analyze_email as analyze_with_gemini

MYT = timezone(timedelta(hours=8))


def parse_gemini_response(response_text):
    """Convert Gemini's JSON response into a Python dictionary."""

    if not response_text:
        return None

    text = response_text.strip()

    # Remove Markdown code fences if Gemini adds them.
    text = re.sub(r'^```json\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^```\s*', '', text)
    text = re.sub(r'\s*```$', '', text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def analyze_email(email_id):
    """Analyze an email with Gemini and create/reuse its client and task."""

    with get_connection() as conn:

        record = conn.execute(
            'SELECT * FROM emails WHERE id=?',
            (email_id,)
        ).fetchone()

        if not record:
            return None

        sender = record['sender'].strip().lower()
        recipient = record['recipient'].strip().lower()

        # Find the operator receiving the email.
        operator = conn.execute(
            'SELECT id FROM operators WHERE lower(email)=?',
            (recipient,)
        ).fetchone()

        if not operator:
            return {
                'email_id': email_id,
                'error': f'No operator registered for {recipient}',
                'requires_action': False
            }

        operator_id = operator['id']

        # Find or create the client.
        client = conn.execute(
            'SELECT * FROM clients WHERE lower(email)=?',
            (sender,)
        ).fetchone()

        display_name = (
            (record['sender_name'] or '').strip()
            or sender.split('@')[0]
        )

        if not client:
            cursor = conn.execute(
                '''
                INSERT INTO clients(name,email,operator_id)
                VALUES (?,?,?)
                ''',
                (display_name, sender, operator_id)
            )

            client_id = cursor.lastrowid
            client_name = display_name

        else:
            client_id = client['id']
            client_name = client['name']

            # Keep the client's existing assigned operator.
            operator_id = client['operator_id']

            if record['sender_name'] and client_name == sender.split('@')[0]:
                client_name = record['sender_name'].strip()

                conn.execute(
                    'UPDATE clients SET name=? WHERE id=?',
                    (client_name, client_id)
                )

        # GEMINI AI ANALYSIS

        ai_response = analyze_with_gemini(
            record['subject'],
            record['sender'],
            record['body']
        )

        ai_result = parse_gemini_response(ai_response)

        if not ai_result:
            return {
                'email_id': email_id,
                'error': 'Gemini returned invalid JSON',
                'requires_action': False
            }

        requires_action = bool(
            ai_result.get('follow_up_required', False)
        )

        priority = ai_result.get('priority', 'Low')

        if priority not in ('High', 'Medium', 'Low'):
            priority = 'Low'

        # Use Gemini's client name when available.
        ai_client = ai_result.get('client')

        if ai_client and ai_client != sender:
            client_name = ai_client

            conn.execute(
                'UPDATE clients SET name=? WHERE id=?',
                (client_name, client_id)
            )

        task_id = record['task_id']
        task_title = None

        # CREATE TASK IF AI SAYS ACTION IS REQUIRED

        if requires_action:

            if task_id:
                task = conn.execute(
                    'SELECT id,title FROM tasks WHERE id=?',
                    (task_id,)
                ).fetchone()

                if task:
                    task_title = task['title']
                else:
                    task_id = None

            if not task_id:

                task_title = (
                    ai_result.get('action_required')
                    or record['subject']
                    or 'Client follow-up'
                )

                # Use AI deadline when available.
                deadline = ai_result.get('deadline')

                if deadline:
                    try:
                        datetime.strptime(deadline, '%Y-%m-%d')
                        due = deadline
                    except ValueError:
                        deadline = None

                if not deadline:
                    due = (
                        datetime.now(MYT)
                        + timedelta(
                            days=1 if priority == 'High' else 2
                        )
                    ).date().isoformat()

                summary = ai_result.get('summary') or record['body'][:1200]

                cursor = conn.execute(
                    '''
                    INSERT INTO tasks
                    (client_id,title,description,due_date,status,priority)
                    VALUES (?,?,?,?,?,?)
                    ''',
                    (
                        client_id,
                        task_title,
                        summary,
                        due,
                        'Pending',
                        priority
                    )
                )

                task_id = cursor.lastrowid

        # Mark the email as processed.
        conn.execute(
            '''
            UPDATE emails
            SET client_id=?, task_id=?, processed=1
            WHERE id=?
            ''',
            (client_id, task_id, email_id)
        )

        conn.commit()

        return {
            'email_id': email_id,
            'client_id': client_id,
            'client_name': client_name,
            'operator_id': operator_id,
            'task_id': task_id,
            'task_title': task_title,
            'priority': priority,
            'requires_action': requires_action,
            'email_type': (
                'Follow-up Request'
                if requires_action
                else 'General Email'
            ),
            'summary': ai_result.get('summary'),
            'action_required': ai_result.get('action_required'),
            'deadline': ai_result.get('deadline')
        }
