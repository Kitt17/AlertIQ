# AlertIQ

AlertIQ is a Flask-based email and follow-up management application with an assistant workflow.

## Setup

1. Install Python 3.10 or later.
2. Create and activate a virtual environment.
3. Install dependencies with `pip install -r requirements.txt`.
4. Copy `.env.example` to `.env` and fill in your own credentials. Never commit `.env`.
5. Run `python app.py` and open the local URL printed by Flask.

The application initializes its local SQLite database when it starts. Use a unique `FLASK_SECRET_KEY` and change the demo login credentials before deploying.

## Project structure

- `app.py` — Flask routes and application entry point
- `database.py` — database setup and queries
- `*_service.py` — assistant, email, synchronization, and follow-up logic
- `templates/` — HTML templates
- `static/` — CSS, JavaScript, and images

## Security

Credentials and local database files are intentionally excluded from this repository.
