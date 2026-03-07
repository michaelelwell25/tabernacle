from flask import Blueprint, render_template
from app.models.tournament import Tournament
from app.services.standings_service import calculate_standings

bp = Blueprint('standings', __name__, url_prefix='/standings')


@bp.route('/tournament/<int:tournament_id>')
def view_standings(tournament_id):
    """View standings table for a tournament"""
    tournament = Tournament.query.get_or_404(tournament_id)
    standings = calculate_standings(tournament)
    return render_template('standings/view.html',
                           tournament=tournament,
                           standings=standings)
