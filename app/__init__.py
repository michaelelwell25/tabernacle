import os
import traceback
from flask import Flask, redirect, url_for, request, flash, render_template
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
    from app.routes import tournament, player, round_bp, results, standings, export_bp, playoff, judge, league, admin
    app.register_blueprint(tournament.bp)
    app.register_blueprint(player.bp)
    app.register_blueprint(round_bp.bp)
    app.register_blueprint(results.bp)
    app.register_blueprint(standings.bp)
    app.register_blueprint(export_bp.bp)
    app.register_blueprint(playoff.bp)
    app.register_blueprint(judge.bp)
    app.register_blueprint(league.bp)
    app.register_blueprint(admin.bp)

    from app import models

    @app.route('/')
    def index():
        from app.models.tournament import Tournament
        from app.models.league import League

        if current_user.is_authenticated and current_user.is_admin():
            tournaments = Tournament.query
            leagues = League.query
        elif current_user.is_authenticated:
            tournaments = Tournament.query.filter_by(owner_id=current_user.id)
            leagues = League.query.filter_by(owner_id=current_user.id)
        else:
            return redirect(url_for('auth.login'))

        total_tournaments = tournaments.count()
        active_tournaments = tournaments.filter(Tournament.status.in_(['active', 'playoffs'])).count()
        total_leagues = leagues.count()
        active_leagues = leagues.filter_by(status='active').count()
        recent_tournaments = tournaments.order_by(Tournament.date.desc()).limit(5).all()
        active_leagues_list = leagues.filter_by(status='active').all()

        return render_template('home.html',
            total_tournaments=total_tournaments,
            active_tournaments=active_tournaments,
            total_leagues=total_leagues,
            active_leagues=active_leagues,
            recent_tournaments=recent_tournaments,
            active_leagues_list=active_leagues_list,
        )

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
