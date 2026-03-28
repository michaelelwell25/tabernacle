import os
from app import create_app, db

app = create_app(os.environ.get('FLASK_ENV', 'production'))

with app.app_context():
    db.create_all()

    # Add league columns to tournaments if missing (db.create_all doesn't alter existing tables)
    try:
        db.session.execute(db.text(
            "ALTER TABLE tournaments ADD COLUMN league_id INTEGER REFERENCES leagues(id)"
        ))
        db.session.commit()
        print("[wsgi] Added league_id column to tournaments")
    except Exception:
        db.session.rollback()

    try:
        db.session.execute(db.text(
            "ALTER TABLE tournaments ADD COLUMN week_number INTEGER"
        ))
        db.session.commit()
        print("[wsgi] Added week_number column to tournaments")
    except Exception:
        db.session.rollback()
