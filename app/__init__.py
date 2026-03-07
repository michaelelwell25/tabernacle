import os
from flask import Flask, session, redirect, url_for, request, render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()

# Public routes that don't need auth
PUBLIC_ENDPOINTS = {'player.join_tournament', 'auth.login', 'health', 'static'}


def create_app(config_name='development'):
    app = Flask(__name__)

    from app.config import config
    app.config.from_object(config[config_name])

    db.init_app(app)
    migrate.init_app(app, db)

    # Auth blueprint
    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp)

    # App blueprints
    from app.routes import tournament, player, round_bp, results, standings, export_bp, playoff
    app.register_blueprint(tournament.bp)
    app.register_blueprint(player.bp)
    app.register_blueprint(round_bp.bp)
    app.register_blueprint(results.bp)
    app.register_blueprint(standings.bp)
    app.register_blueprint(export_bp.bp)
    app.register_blueprint(playoff.bp)

    from app import models

    @app.route('/')
    def index():
        return redirect(url_for('tournament.list_tournaments'))

    @app.route('/health')
    def health():
        return 'ok', 200

    @app.before_request
    def require_auth():
        admin_pw = os.environ.get('ADMIN_PASSWORD') or app.config.get('ADMIN_PASSWORD')
        if not admin_pw:
            return  # No password set = no auth required (local dev)

        endpoint = request.endpoint
        if endpoint in PUBLIC_ENDPOINTS or (endpoint and endpoint.startswith('static')):
            return

        if not session.get('authenticated'):
            return redirect(url_for('auth.login', next=request.url))

    return app
