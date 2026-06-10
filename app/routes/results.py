from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models.round import Round
from app.models.pod import Pod
from app.models.pod_assignment import PodAssignment

bp = Blueprint('results', __name__, url_prefix='/results')


def _save_constructed_results(round_obj):
    """Parse 1v1 results. Form value: '<winner_id>:<w>-<l>[-<d>]' or 'draw:<g1>-<g2>[-<d>]'."""
    tournament = round_obj.tournament
    flat_win = tournament.get_scoring_points()[1]

    for pod in round_obj.pods.order_by('pod_number').all():
        if pod.is_bye:
            continue

        result = request.form.get(f'result_{pod.id}')
        if not result or ':' not in result:
            continue

        outcome, score = result.split(':', 1)
        parts = list(map(int, score.split('-')))
        g1, g2 = parts[0], parts[1]
        gd = parts[2] if len(parts) > 2 else 0
        assignments = pod.assignments.order_by('seat_position').all()

        if outcome == 'draw':
            for assignment, own, opp in zip(assignments, (g1, g2), (g2, g1)):
                assignment.placement = None
                assignment.points_earned = tournament.draw_points
                assignment.game_wins = own
                assignment.game_losses = opp
                assignment.game_draws = gd
        else:
            winner_id = int(outcome)
            for assignment in assignments:
                if assignment.player_id == winner_id:
                    assignment.placement = 1
                    assignment.points_earned = flat_win
                    assignment.game_wins = g1
                    assignment.game_losses = g2
                else:
                    assignment.placement = 2
                    assignment.points_earned = 0
                    assignment.game_wins = g2
                    assignment.game_losses = g1
                assignment.game_draws = gd

        pod.status = 'completed'

    db.session.commit()


def _save_results(round_obj):
    tournament = round_obj.tournament

    if tournament.is_constructed():
        return _save_constructed_results(round_obj)

    pods = round_obj.pods.order_by('pod_number').all()
    scoring = tournament.get_scoring_points()
    flat_win = scoring[1]
    use_seats = tournament.seat_scoring

    if use_seats:
        seat_wins = tournament.get_seat_win_points()
        seat_draws = tournament.get_seat_draw_points()

    for pod in pods:
        if pod.is_bye:
            continue

        result_key = f'result_{pod.id}'
        result = request.form.get(result_key)

        if result == 'draw':
            for assignment in pod.assignments:
                assignment.placement = None
                if use_seats:
                    assignment.points_earned = seat_draws.get(assignment.seat_position, 0.4)
                else:
                    assignment.points_earned = tournament.draw_points
        elif result:
            winner_id = int(result)
            for assignment in pod.assignments:
                if assignment.player_id == winner_id:
                    assignment.placement = 1
                    if use_seats:
                        assignment.points_earned = seat_wins.get(assignment.seat_position, flat_win)
                    else:
                        assignment.points_earned = flat_win
                else:
                    assignment.placement = None
                    assignment.points_earned = 0

        if result:
            pod.status = 'completed'

    db.session.commit()


@bp.route('/<int:round_id>/submit', methods=['GET', 'POST'])
def submit_results(round_id):
    round_obj = Round.query.get_or_404(round_id)
    tournament = round_obj.tournament

    if request.method == 'POST':
        _save_results(round_obj)
        flash(f'Results for Round {round_obj.round_number} saved!', 'success')
        return redirect(url_for('round.view_round', round_id=round_id))

    pods = round_obj.pods.order_by('pod_number').all()
    return render_template('results/submit.html',
                           tournament=tournament,
                           round=round_obj,
                           pods=pods)


@bp.route('/pod/<int:pod_id>/clear', methods=['POST'])
def clear_pod_result(pod_id):
    pod = Pod.query.get_or_404(pod_id)
    round_obj = pod.round
    for assignment in pod.assignments:
        assignment.placement = None
        assignment.points_earned = None
        assignment.game_wins = None
        assignment.game_losses = None
        assignment.game_draws = None
    pod.status = 'pending'
    db.session.commit()
    flash(f'Table {pod.table_number} result cleared.', 'success')
    return redirect(url_for('round.view_round', round_id=round_obj.id))


@bp.route('/<int:round_id>/submit-and-next', methods=['POST'])
def submit_and_next(round_id):
    import traceback, sys
    round_obj = Round.query.get_or_404(round_id)
    tournament = round_obj.tournament

    try:
        _save_results(round_obj)
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        db.session.rollback()
        flash(f'Error saving results: {str(e)}', 'error')
        return redirect(url_for('round.view_round', round_id=round_id))

    if not round_obj.is_complete():
        flash('Results saved, but not all pods have results — cannot generate next round.', 'warning')
        return redirect(url_for('round.view_round', round_id=round_id))

    from app.services.pairing_service import generate_swiss_pairings
    try:
        # Ensure current_round reflects actual latest round
        latest = Round.query.filter_by(tournament_id=tournament.id, is_playoff=False)\
            .order_by(Round.round_number.desc()).first()
        if latest and latest.round_number > tournament.current_round:
            tournament.current_round = latest.round_number
            db.session.commit()

        next_round_number = tournament.current_round + 1
        new_round = generate_swiss_pairings(tournament.id, next_round_number)
        tournament.current_round = next_round_number
        db.session.commit()
        flash(f'Results saved! Round {new_round.round_number} generated.', 'success')
        return redirect(url_for('round.view_round', round_id=new_round.id))
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        db.session.rollback()
        flash(f'Results saved, but could not generate next round: {str(e)}', 'error')
        return redirect(url_for('round.view_round', round_id=round_id))
