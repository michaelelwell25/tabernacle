from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()


def create_app(config_name='development'):
    """Application factory pattern"""
    app = Flask(__name__)

    # Load configuration
    from app.config import config
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # Register blueprints
    from app.routes import tournament, player, round_bp, results, standings, export_bp, playoff
    app.register_blueprint(tournament.bp)
    app.register_blueprint(player.bp)
    app.register_blueprint(round_bp.bp)
    app.register_blueprint(results.bp)
    app.register_blueprint(standings.bp)
    app.register_blueprint(export_bp.bp)
    app.register_blueprint(playoff.bp)

    # Import models to ensure they're registered with SQLAlchemy
    from app import models

    # Register index route
    @app.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('tournament.list_tournaments'))

    return app
