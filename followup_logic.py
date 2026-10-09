from datetime import datetime, timedelta, timezone

from database import get_connection
from email_analyzer import analyze_email

MYT = timezone(timedelta(hours=8))


def process_followups():
    """Analyze only new emails and create/reconcile notifications."""

    with get_connection() as conn:
        ids = [
            row['id']
            for row in conn.execute(
                'SELECT id FROM emails WHERE processed=0 ORDER BY id'
            )
        ]

    created = skipped = 0

    for email_id in ids:
        result = analyze_email(email_id)

        if not result or result.get('error') or not result['requires_action']:
            skipped += 1
            continue

        with get_connection() as conn:
            existing = conn.execute(
                'SELECT id FROM notifications WHERE email_id=?',
                (email_id,)
            ).fetchone()

            message = f"{result['client_name']}: {result['action_required'] or result['task_title']}"
            created_at = datetime.now(MYT).strftime('%Y-%m-%d %H:%M:%S')
            if existing:
                # Repair an existing notification without creating duplicates.
                conn.execute(
                    '''
                    UPDATE notifications
                    SET operator_id=?, task_id=?, message=?, priority=?
                    WHERE id=?
                    ''',
                    (
                        result['operator_id'],
                        result['task_id'],
                        message,
                        result['priority'],
                        existing['id']
                    )
                )
                skipped += 1

            else:
                conn.execute(
                    '''
                    INSERT INTO notifications
                    (operator_id,task_id,email_id,message,priority,created_at)
                    VALUES (?,?,?,?,?,?)
                    ''',
                    (
                        result['operator_id'],
                        result['task_id'],
                        email_id,
                        message,
                        result['priority'],
                        created_at
                    )
                )
                created += 1

            conn.commit()

    return created, skipped
