import os
from datetime import datetime, timedelta, timezone
MYT = timezone(timedelta(hours=8))
from functools import wraps
from flask import Flask, render_template, redirect, url_for, flash, abort, session, request, jsonify
from dotenv import load_dotenv
from database import get_connection, create_database, ensure_demo_operator
from sync_service import sync_emails
from assistant_service import ask_assistant

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'local-demo-only-change-before-deployment')
create_database()
DEMO_OPERATOR_ID = ensure_demo_operator()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if 'operator_id' not in session:
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapper


def myt_now():
    return datetime.now(MYT).strftime('%Y-%m-%d %H:%M:%S')

def myt_today():
    return datetime.now(MYT).date().isoformat()

def page_context(conn):
    oid = session['operator_id']
    operator = conn.execute('SELECT name FROM operators WHERE id=?', (oid,)).fetchone()
    unread = conn.execute('''SELECT count(*) FROM notifications
        WHERE operator_id=? AND is_read=0 AND (snoozed_until IS NULL OR snoozed_until<=?)''',
        (oid, myt_now())).fetchone()[0]
    return {'operator_name': operator['name'] if operator else 'Operator', 'unread_count': unread}


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        demo_email = os.getenv('DEMO_LOGIN_EMAIL', 'operator@alertiq.com').lower()
        demo_password = os.getenv('DEMO_LOGIN_PASSWORD', '123456')
        if login_email == demo_email and password == demo_password:
            session.clear()
            session['operator_id'] = DEMO_OPERATOR_ID
            return redirect(url_for('dashboard'))
        flash('Invalid email or password.', 'error')
    return render_template('login.html')


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def dashboard():
    oid = session['operator_id']
    with get_connection() as conn:
        context = page_context(conn)
        stats = conn.execute('''SELECT
        count(*) AS total,
        sum(CASE WHEN status='Completed' THEN 1 ELSE 0 END) AS completed,
        sum(CASE WHEN status!='Completed' AND due_date < ? THEN 1 ELSE 0 END) AS overdue,
        sum(CASE WHEN status!='Completed' AND due_date >= ? THEN 1 ELSE 0 END) AS pending
        FROM tasks WHERE client_id IN (SELECT id FROM clients WHERE operator_id=?)''',
        (myt_today(), myt_today(), oid)).fetchone()        
        context.update(
            total_clients=conn.execute('SELECT count(*) FROM clients WHERE operator_id=?', (oid,)).fetchone()[0],
            pending_followups=stats['pending'] or 0, overdue=stats['overdue'] or 0,
            completed=stats['completed'] or 0,
        )
        context['notifications'] = conn.execute('''SELECT n.*, c.name AS client_name,
    t.title AS task_title, t.description AS task_description,
    t.due_date AS task_due_date
    FROM notifications n
    LEFT JOIN emails e ON n.email_id=e.id
    LEFT JOIN clients c ON e.client_id=c.id
    LEFT JOIN tasks t ON n.task_id=t.id
    WHERE n.operator_id=? AND n.is_read=0
    AND (n.snoozed_until IS NULL OR n.snoozed_until<=?)
    ORDER BY n.created_at DESC,n.id DESC LIMIT 8''',
    (oid, myt_now())).fetchall()    
        return render_template('dashboard.html', **context)


@app.route('/clients')
@login_required
def clients():
    oid = session['operator_id']
    with get_connection() as conn:
        context = page_context(conn)
        context['clients'] = conn.execute('''SELECT c.id,c.name,c.email,
    sum(CASE WHEN t.status!='Completed' AND t.due_date>=? THEN 1 ELSE 0 END) AS pending_tasks,
    sum(CASE WHEN t.status!='Completed' AND t.due_date<? THEN 1 ELSE 0 END) AS overdue_tasks,
    sum(CASE WHEN t.status='Completed' THEN 1 ELSE 0 END) AS completed_tasks
    FROM clients c LEFT JOIN tasks t ON t.client_id=c.id
    WHERE c.operator_id=? GROUP BY c.id ORDER BY c.name''',
    (myt_today(), myt_today(), oid)).fetchall()    
        return render_template('clients.html', **context)


@app.route('/assigned-tasks')
@login_required
def assigned_tasks():
    oid = session['operator_id']
    with get_connection() as conn:
        context = page_context(conn)
        context['tasks'] = conn.execute('''SELECT t.*,c.name AS client_name,c.email AS client_email,
    CASE WHEN t.status!='Completed' AND t.due_date<? THEN 'Overdue'
         ELSE t.status END AS display_status
    FROM tasks t JOIN clients c ON c.id=t.client_id WHERE c.operator_id=?
    ORDER BY CASE WHEN t.status!='Completed' AND t.due_date<? THEN 0
                  WHEN t.status!='Completed' THEN 1 ELSE 2 END, t.due_date''',
    (myt_today(), oid, myt_today())).fetchall()    
        return render_template('assigned_tasks.html', **context)


@app.route('/sync', methods=['POST'])
@login_required
def sync():
    try:
        result = sync_emails()
        flash(f"Sync complete! {result['saved']} new emails saved, {result['notifications']} new alerts created. Existing emails were also checked.", 'success')
    except Exception:
        app.logger.exception('Gmail sync failed')
        flash('Gmail sync failed. Check the terminal for details.', 'error')
    return redirect(url_for('dashboard'))


@app.route('/api/notifications')
@login_required
def notification_data():
    with get_connection() as conn:
        rows = conn.execute('''
            SELECT
                n.id,
                n.message,
                n.priority,
                strftime('%H:%M', n.created_at) AS created_at,                c.name AS client_name,
                t.description AS summary,
                t.due_date
            FROM notifications n
            LEFT JOIN emails e ON n.email_id=e.id
            LEFT JOIN clients c ON e.client_id=c.id
            LEFT JOIN tasks t ON n.task_id=t.id
            WHERE n.operator_id=? AND n.is_read=0
            AND (n.snoozed_until IS NULL OR n.snoozed_until<=?)
            ORDER BY n.created_at DESC,n.id DESC
            LIMIT 20
        ''', (session['operator_id'], myt_now())).fetchall()

    return jsonify([dict(row) for row in rows])

@app.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    with get_connection() as conn:
        cursor = conn.execute('UPDATE notifications SET is_read=1 WHERE id=? AND operator_id=?',
                              (notification_id, session['operator_id']))
        if not cursor.rowcount:
            abort(404)
        conn.commit()
    return jsonify(success=True)


@app.route('/complete/<int:notification_id>', methods=['POST'])
@login_required
def complete_notification(notification_id):
    with get_connection() as conn:
        notification = conn.execute('SELECT task_id FROM notifications WHERE id=? AND operator_id=?',
                                    (notification_id, session['operator_id'])).fetchone()
        if not notification:
            abort(404)
        if notification['task_id']:
            conn.execute("UPDATE tasks SET status='Completed' WHERE id=?", (notification['task_id'],))
            conn.execute('''UPDATE notifications SET is_read=1,snoozed_until=NULL
                            WHERE task_id=? AND operator_id=?''', (notification['task_id'], session['operator_id']))
            flash('Task completed.', 'success')
        else:
            conn.execute('UPDATE notifications SET is_read=1 WHERE id=?', (notification_id,))
            flash('Alert dismissed.', 'success')
        conn.commit()
    return redirect(url_for('dashboard'))


@app.route('/tasks/<int:task_id>/complete', methods=['POST'])
@login_required
def complete_task(task_id):
    with get_connection() as conn:
        task = conn.execute('''SELECT t.id FROM tasks t JOIN clients c ON t.client_id=c.id
                               WHERE t.id=? AND c.operator_id=?''', (task_id, session['operator_id'])).fetchone()
        if not task:
            abort(404)
        conn.execute("UPDATE tasks SET status='Completed' WHERE id=?", (task_id,))
        conn.execute('UPDATE notifications SET is_read=1,snoozed_until=NULL WHERE task_id=? AND operator_id=?',
                     (task_id, session['operator_id']))
        conn.commit()
    flash('Task completed.', 'success')
    return redirect(url_for('assigned_tasks'))


@app.route('/snooze/<int:notification_id>', methods=['POST'])
@login_required
def snooze_notification(notification_id):
    until = (datetime.now(MYT) + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')

    with get_connection() as conn:
        notification = conn.execute(
            '''
            SELECT id
            FROM notifications
            WHERE id=? AND operator_id=?
            ''',
            (notification_id, session['operator_id'])
        ).fetchone()

        if not notification:
            abort(404)

        conn.execute(
            '''
            UPDATE notifications
            SET snoozed_until=?
            WHERE id=? AND operator_id=?
            ''',
            (until, notification_id, session['operator_id'])
        )

        conn.commit()

    flash('Alert snoozed for one hour.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/assistant', methods=['GET', 'POST'])
@login_required
def assistant():
    answer = None
    question = ''

    if request.method == 'POST':
        question = request.form.get('question', '').strip()

        if question:
            answer = ask_assistant(
                session['operator_id'],
                question
            )

    with get_connection() as conn:
        context = page_context(conn)

    return render_template(
        'assistant.html',
        question=question,
        answer=answer,
        **context
    )

@app.route('/api/assistant', methods=['POST'])
@login_required
def assistant_api():
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()

    if not question:
        return jsonify({'answer': 'Please enter a question.'}), 400

    answer = ask_assistant(
        session['operator_id'],
        question
    )

    return jsonify({'answer': answer})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
