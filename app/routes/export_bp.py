import io
from flask import Blueprint, make_response
import pandas as pd
from app.models.tournament import Tournament
from app.services.standings_service import calculate_standings

bp = Blueprint('export', __name__, url_prefix='/export')


@bp.route('/tournament/<int:tournament_id>/standings')
def export_standings(tournament_id):
    """Export standings as CSV download"""
    tournament = Tournament.query.get_or_404(tournament_id)
    standings = calculate_standings(tournament)

    rows = []
    for s in standings:
        rows.append({
            'Rank': s['rank'],
            'Player': s['player'].name,
            'Points': s['points'],
            'OMW%': f"{s['omw_percentage'] * 100:.1f}%",
            'GW%': f"{s['gw_percentage'] * 100:.1f}%",
            'OGW%': f"{s['ogw_percentage'] * 100:.1f}%",
            'Matches Played': s['matches_played'],
        })

    df = pd.DataFrame(rows)
    output = io.StringIO()
    df.to_csv(output, index=False)

    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = (
        f'attachment; filename={tournament.name.replace(" ", "_")}_standings.csv'
    )
    return response
