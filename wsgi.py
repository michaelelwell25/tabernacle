import os
from app import create_app, db

app = create_app(os.environ.get('FLASK_ENV', 'production'))

with app.app_context():
    db.create_all()
