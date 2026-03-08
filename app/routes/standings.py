from flask import Blueprint, render_template
from app.models.tournament import Tournament
from app.services.standings_service import calculate_standings

bp = Blueprint('standings', __name__, url_prefix='/standings')


def _calculate_projections(tournament, standings):
    """For each active player, project their rank if they win vs lose."""
    if tournament.status != 'active' or not tournament.playoff_cut:
        return {}

    cut = tournament.playoff_cut
    scoring = tournament.get_scoring_points()
    win_pts = scoring[1]

    projections = {}
    for s in standings:
        p = s['player']
        if p.dropped:
            continue

        current_rank = s['rank']
        current_pts = s['points']

        # Count how many players would be above this player if they win
        win_total = current_pts + win_pts
        above_if_win = sum(1 for x in standings if not x['player'].dropped
                          and x['player'].id != p.id
                          and x['points'] >= win_total)

        # Count how many players would be above if they lose (0 pts)
        above_if_lose = sum(1 for x in standings if not x['player'].dropped
                           and x['player'].id != p.id
                           and x['points'] >= current_pts)

        best_rank = above_if_win + 1
        worst_rank = above_if_lose + 1

        if worst_rank <= cut:
            projections[p.id] = 'clinched'
        elif best_rank > cut:
            projections[p.id] = 'eliminated'
        elif best_rank <= cut:
            projections[p.id] = 'win-and-in'

    return projections


@bp.route('/tournament/<int:tournament_id>')
def view_standings(tournament_id):
    """View standings table for a tournament"""
    tournament = Tournament.query.get_or_404(tournament_id)
    standings = calculate_standings(tournament)
    projections = _calculate_projections(tournament, standings)
    return render_template('standings/view.html',
                           tournament=tournament,
                           standings=standings,
                           projections=projections)
