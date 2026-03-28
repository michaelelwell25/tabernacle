import os
from app import create_app, db
from flask_migrate import upgrade

app = create_app(os.environ.get('FLASK_ENV', 'production'))

with app.app_context():
    upgrade()
    db.create_all()
