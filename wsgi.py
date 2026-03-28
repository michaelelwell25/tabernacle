import os
from app import create_app, db

app = create_app(os.environ.get('FLASK_ENV', 'production'))

with app.app_context():
    db.create_all()

    # Idempotent column additions for Postgres (db.create_all doesn't alter existing tables)
    alter_statements = [
        "ALTER TABLE tournaments ADD COLUMN league_id INTEGER REFERENCES leagues(id)",
        "ALTER TABLE tournaments ADD COLUMN week_number INTEGER",
        "ALTER TABLE tournaments ADD COLUMN owner_id INTEGER REFERENCES users(id)",
        "ALTER TABLE leagues ADD COLUMN owner_id INTEGER REFERENCES users(id)",
    ]
    for stmt in alter_statements:
        try:
            db.session.execute(db.text(stmt))
            db.session.commit()
            print(f"[wsgi] Executed: {stmt}")
        except Exception:
            db.session.rollback()
