from flask import Blueprint, render_template, request, redirect, url_for, flash
from datetime import datetime
from app import db
from app.models.tournament import Tournament
from app.models.round import Round
from app.models.pairing_history import PairingHistory
from app.models.bye_history import ByeHistory
from app.services.pairing_service import generate_swiss_pairings

bp = Blueprint('round', __name__, url_prefix='/rounds')


@bp.route('/tournament/<int:tournament_id>')
def list_rounds(tournament_id):
    """List all rounds for a tournament"""
    tournament = Tournament.query.get_or_404(tournament_id)
    rounds = tournament.rounds.order_by(Round.round_number).all()
    return render_template('round/list.html', tournament=tournament, rounds=rounds)


@bp.route('/<int:round_id>')
def view_round(round_id):
    """View pairings for a specific round"""
    round_obj = Round.query.get_or_404(round_id)
    tournament = round_obj.tournament
    pods = round_obj.pods.order_by('pod_number').all()
    is_latest_round = round_obj.round_number == tournament.current_round
    return render_template('round/pairings.html', tournament=tournament, round=round_obj, pods=pods, is_latest_round=is_latest_round)


@bp.route('/tournament/<int:tournament_id>/generate', methods=['POST'])
def generate_round(tournament_id):
    """Generate pairings for the next round"""
    tournament = Tournament.query.get_or_404(tournament_id)

    if tournament.status != 'active':
        flash('Tournament must be active to generate pairings', 'error')
        return redirect(url_for('tournament.view_tournament', tournament_id=tournament_id))

    # Check if current round is complete
    if tournament.current_round > 0:
        current_round = tournament.get_current_round()
        if current_round and not current_round.is_complete():
            flash(f'Round {tournament.current_round} is not yet complete. Enter all results before generating next round.', 'error')
            return redirect(url_for('round.view_round', round_id=current_round.id))

    # Generate next round
    next_round_number = tournament.current_round + 1

    try:
        round_obj = generate_swiss_pairings(tournament_id, next_round_number)
        tournament.current_round = next_round_number

        db.session.commit()

        flash(f'Round {next_round_number} pairings generated!', 'success')
        return redirect(url_for('round.view_round', round_id=round_obj.id))

    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('tournament.view_tournament', tournament_id=tournament_id))


@bp.route('/<int:round_id>/timer', methods=['POST'])
def reset_timer(round_id):
    from datetime import timedelta
    round_obj = Round.query.get_or_404(round_id)
    tournament = round_obj.tournament
    minutes = request.form.get('minutes', type=int) or tournament.round_timer_minutes or 75
    round_obj.timer_end = datetime.utcnow() + timedelta(minutes=minutes)
    db.session.commit()
    flash(f'Timer set to {minutes} minutes', 'success')
    return redirect(url_for('round.view_round', round_id=round_id))


@bp.route('/<int:round_id>/slips')
def print_slips(round_id):
    round_obj = Round.query.get_or_404(round_id)
    tournament = round_obj.tournament
    pods = round_obj.pods.order_by('pod_number').all()
    return render_template('round/slips.html', tournament=tournament, round=round_obj, pods=pods)


@bp.route('/<int:round_id>/delete', methods=['POST'])
def delete_round(round_id):
    """Delete a round (and all its pods/results)"""
    round_obj = Round.query.get_or_404(round_id)
    tournament = round_obj.tournament
    round_number = round_obj.round_number

    # Only allow deleting the most recent round
    if round_number != tournament.current_round:
        flash('Can only delete the most recent round', 'error')
        return redirect(url_for('round.list_rounds', tournament_id=tournament.id))

    # Check if any results have been entered
    has_results = False
    for pod in round_obj.pods:
        if pod.has_results():
            has_results = True
            break

    if has_results:
        confirmation = request.form.get('confirm')
        if confirmation != 'yes':
            flash('This round has results entered. Confirm deletion.', 'warning')
            return redirect(url_for('round.view_round', round_id=round_id))

    # Clean up pairing history and bye history for this round
    PairingHistory.query.filter_by(
        tournament_id=tournament.id,
        round_number=round_number
    ).delete()
    ByeHistory.query.filter_by(
        tournament_id=tournament.id,
        round_number=round_number
    ).delete()

    db.session.delete(round_obj)
    tournament.current_round = max(0, tournament.current_round - 1)
    db.session.commit()

    flash(f'Round {round_number} deleted', 'success')
    return redirect(url_for('tournament.view_tournament', tournament_id=tournament.id))
