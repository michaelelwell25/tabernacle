import os
import traceback
from flask import Flask, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

# Public routes that don't need auth
PUBLIC_ENDPOINTS = {
    'player.join_tournament', 'player.moxfield_fetch',
    'judge.create_call', 'auth.login', 'auth.register',
    'auth.logout', 'health', 'static',
}


def create_app(config_name='development'):
    app = Flask(__name__)

    from app.config import config
    app.config.from_object(config[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        from app.models.user import User
        return User.query.get(int(user_id))

    # Auth blueprint
    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp)

    # App blueprints
    from app.routes import tournament, player, round_bp, results, standings, export_bp, playoff, judge, league
    app.register_blueprint(tournament.bp)
    app.register_blueprint(player.bp)
    app.register_blueprint(round_bp.bp)
    app.register_blueprint(results.bp)
    app.register_blueprint(standings.bp)
    app.register_blueprint(export_bp.bp)
    app.register_blueprint(playoff.bp)
    app.register_blueprint(judge.bp)
    app.register_blueprint(league.bp)

    from app import models

    @app.route('/')
    def index():
        return redirect(url_for('tournament.list_tournaments'))

    @app.route('/health')
    def health():
        return 'ok', 200

    @app.before_request
    def require_auth():
        endpoint = request.endpoint
        if endpoint in PUBLIC_ENDPOINTS or (endpoint and endpoint.startswith('static')):
            return

        if not current_user.is_authenticated:
            return redirect(url_for('auth.login', next=request.url))

    @app.errorhandler(500)
    def internal_error(e):
        traceback.print_exc()
        db.session.rollback()
        flash(f'Server error: {str(e)}', 'error')
        return redirect(request.referrer or url_for('index'))

    return app
