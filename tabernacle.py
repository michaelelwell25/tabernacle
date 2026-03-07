"""
Tabernacle - Desktop launcher for the cEDH Tournament Manager.

Usage:
    python tabernacle.py            Launch as a desktop app (FlaskUI window)
    python tabernacle.py --server   Launch as a normal Flask dev server on port 5000
"""
import sys
import os
from dotenv import load_dotenv

load_dotenv()

from app import create_app, db

app = create_app('production')

# Ensure database tables exist on first run
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    if '--server' in sys.argv:
        app.run(host='127.0.0.1', port=5000, debug=False)
    else:
        from flaskwebgui import FlaskUI
        FlaskUI(
            app=app,
            server='flask',
            width=1200,
            height=800,
            window_title='Tabernacle'
        ).run()
