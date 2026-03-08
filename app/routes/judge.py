from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime
from app import db
from app.models.tournament import Tournament
from app.models.judge_call import JudgeCall

bp = Blueprint('judge', __name__, url_prefix='/judge')


@bp.route('/<int:tournament_id>')
def judge_queue(tournament_id):
    """Judge queue page — shows open/claimed calls."""
    tournament = Tournament.query.get_or_404(tournament_id)
    open_calls = JudgeCall.query.filter_by(
        tournament_id=tournament_id, status='open'
    ).order_by(JudgeCall.created_at).all()
    claimed_calls = JudgeCall.query.filter_by(
        tournament_id=tournament_id, status='claimed'
    ).order_by(JudgeCall.claimed_at.desc()).all()
    resolved_calls = JudgeCall.query.filter_by(
        tournament_id=tournament_id, status='resolved'
    ).order_by(JudgeCall.resolved_at.desc()).limit(20).all()
    return render_template('judge/queue.html', tournament=tournament,
                           open_calls=open_calls, claimed_calls=claimed_calls,
                           resolved_calls=resolved_calls)


@bp.route('/call/<int:call_id>/claim', methods=['POST'])
def claim_call(call_id):
    call = JudgeCall.query.get_or_404(call_id)
    judge_name = request.form.get('judge_name', '').strip() or 'Judge'
    call.status = 'claimed'
    call.claimed_by = judge_name
    call.claimed_at = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('judge.judge_queue', tournament_id=call.tournament_id))


@bp.route('/call/<int:call_id>/resolve', methods=['POST'])
def resolve_call(call_id):
    call = JudgeCall.query.get_or_404(call_id)
    call.status = 'resolved'
    call.resolved_at = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('judge.judge_queue', tournament_id=call.tournament_id))


@bp.route('/call/<int:call_id>/reopen', methods=['POST'])
def reopen_call(call_id):
    call = JudgeCall.query.get_or_404(call_id)
    call.status = 'open'
    call.claimed_by = None
    call.claimed_at = None
    db.session.commit()
    return redirect(url_for('judge.judge_queue', tournament_id=call.tournament_id))


# Public API for players to create calls
@bp.route('/<int:tournament_id>/call', methods=['POST'])
def create_call(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    player_name = request.form.get('player_name', '').strip()
    table_number = request.form.get('table_number', type=int)
    reason = request.form.get('reason', '').strip()

    if not player_name:
        return jsonify({'error': 'Name required'}), 400

    # Prevent spam — check for existing open call from same player
    existing = JudgeCall.query.filter_by(
        tournament_id=tournament_id, player_name=player_name, status='open'
    ).first()
    if existing:
        return jsonify({'error': 'You already have an open judge call'}), 409

    call = JudgeCall(
        tournament_id=tournament_id,
        player_name=player_name,
        table_number=table_number,
        round_number=tournament.current_round,
        reason=reason or None,
        status='open'
    )
    db.session.add(call)
    db.session.commit()
    return jsonify({'ok': True, 'call_id': call.id})
