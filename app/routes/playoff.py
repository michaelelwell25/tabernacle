from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models.tournament import Tournament
from app.models.round import Round
from app.services.playoff_service import start_playoffs, advance_to_finals
from app.services.standings_service import calculate_standings

bp = Blueprint('playoff', __name__, url_prefix='/playoffs')


@bp.route('/tournament/<int:tournament_id>/start', methods=['POST'])
def start_playoff(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    cut_size = request.form.get('cut_size', type=int)

    if not cut_size:
        flash('Select a playoff cut size', 'error')
        return redirect(url_for('tournament.view_tournament', tournament_id=tournament_id))

    try:
        round_obj = start_playoffs(tournament_id, cut_size)
        db.session.commit()
        flash(f'Playoffs started! Top {cut_size} cut.', 'success')
        return redirect(url_for('playoff.view_playoff', tournament_id=tournament_id))
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('tournament.view_tournament', tournament_id=tournament_id))


@bp.route('/tournament/<int:tournament_id>')
def view_playoff(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    playoff_rounds = Round.query.filter_by(
        tournament_id=tournament_id, is_playoff=True
    ).order_by(Round.round_number).all()

    standings = calculate_standings(tournament)
    cut = tournament.playoff_cut or 0
    top_players = [s for s in standings if not s['player'].dropped][:cut]

    return render_template('playoff/view.html',
                           tournament=tournament,
                           playoff_rounds=playoff_rounds,
                           top_players=top_players)


@bp.route('/tournament/<int:tournament_id>/advance', methods=['POST'])
def advance(tournament_id):
    try:
        round_obj = advance_to_finals(tournament_id)
        db.session.commit()
        flash('Finals generated!', 'success')
        return redirect(url_for('playoff.view_playoff', tournament_id=tournament_id))
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('playoff.view_playoff', tournament_id=tournament_id))


@bp.route('/tournament/<int:tournament_id>/complete', methods=['POST'])
def complete_playoff(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)

    final_round = Round.query.filter_by(
        tournament_id=tournament_id, is_playoff=True, playoff_stage='final'
    ).first()

    if not final_round or not final_round.is_complete():
        flash('Finals must be completed first', 'error')
        return redirect(url_for('playoff.view_playoff', tournament_id=tournament_id))

    tournament.status = 'completed'
    db.session.commit()
    flash('Tournament completed!', 'success')
    return redirect(url_for('tournament.view_tournament', tournament_id=tournament_id))
