from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user
from datetime import datetime
from app import db
from app.models.tournament import Tournament

bp = Blueprint('tournament', __name__, url_prefix='/tournaments')


@bp.route('/')
def list_tournaments():
    """List all tournaments"""
    q = Tournament.query.filter_by(league_id=None)
    if not current_user.is_admin():
        q = q.filter_by(owner_id=current_user.id)
    tournaments = q.order_by(Tournament.date.desc()).all()
    return render_template('tournament/list.html', tournaments=tournaments)


@bp.route('/create', methods=['GET', 'POST'])
def create_tournament():
    """Create a new tournament"""
    if current_user.is_player():
        abort(403)
    if request.method == 'POST':
        name = request.form.get('name')
        date_str = request.form.get('date')
        scoring_system = request.form.get('scoring_system', '3-1-0-0')

        if not name or not date_str:
            flash('Name and date are required', 'error')
            return render_template('tournament/create.html')

        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format', 'error')
            return render_template('tournament/create.html')

        bye_points = request.form.get('bye_points', 1, type=int)
        draw_points = request.form.get('draw_points', 1, type=int)
        allow_byes = request.form.get('allow_byes', '1') == '1'
        round_timer_minutes = request.form.get('round_timer_minutes', 80, type=int)
        seat_scoring = request.form.get('seat_scoring') == '1'
        seat_win_points = request.form.get('seat_win_points', '5.2-5.4-5.6-5.8').strip()
        seat_draw_points = request.form.get('seat_draw_points', '0.2-0.4-0.6-0.8').strip()

        tournament = Tournament(
            name=name,
            date=date,
            scoring_system=scoring_system,
            bye_points=bye_points,
            draw_points=draw_points,
            allow_byes=allow_byes,
            round_timer_minutes=round_timer_minutes if round_timer_minutes > 0 else None,
            seat_scoring=seat_scoring,
            seat_win_points=seat_win_points,
            seat_draw_points=seat_draw_points,
            owner_id=current_user.id,
            status='registration'
        )

        db.session.add(tournament)
        db.session.commit()

        flash(f'Tournament "{name}" created successfully!', 'success')
        return redirect(url_for('tournament.view_tournament', tournament_id=tournament.id))

    return render_template('tournament/create.html')


@bp.route('/<int:tournament_id>')
def view_tournament(tournament_id):
    """View tournament dashboard"""
    tournament = Tournament.query.get_or_404(tournament_id)
    if not current_user.is_admin() and tournament.owner_id != current_user.id:
        abort(403)
    from app.models.round import Round
    players = tournament.get_active_players()
    rounds = tournament.rounds.order_by(Round.round_number).all()
    current_round = tournament.get_current_round()
    return render_template('tournament/dashboard.html',
                           tournament=tournament,
                           player_count=len(players),
                           rounds=rounds,
                           current_round=current_round)


@bp.route('/<int:tournament_id>/start', methods=['POST'])
def start_tournament(tournament_id):
    """Start a tournament (move from registration to active)"""
    tournament = Tournament.query.get_or_404(tournament_id)

    if tournament.status != 'registration':
        flash('Tournament has already started', 'error')
        return redirect(url_for('tournament.view_tournament', tournament_id=tournament.id))

    player_count = tournament.players.filter_by(dropped=False).count()
    if player_count < 3:
        flash('Need at least 3 players to start tournament', 'error')
        return redirect(url_for('tournament.view_tournament', tournament_id=tournament.id))

    tournament.status = 'active'
    db.session.commit()

    flash('Tournament started! Generate pairings for Round 1.', 'success')
    return redirect(url_for('tournament.view_tournament', tournament_id=tournament.id))


@bp.route('/<int:tournament_id>/complete', methods=['POST'])
def complete_tournament(tournament_id):
    """Mark tournament as completed"""
    tournament = Tournament.query.get_or_404(tournament_id)

    if tournament.status != 'active':
        flash('Tournament is not active', 'error')
        return redirect(url_for('tournament.view_tournament', tournament_id=tournament.id))

    tournament.status = 'completed'
    db.session.commit()

    flash('Tournament completed!', 'success')
    return redirect(url_for('tournament.view_tournament', tournament_id=tournament.id))


@bp.route('/<int:tournament_id>/toggle-byes', methods=['POST'])
def toggle_byes(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    tournament.allow_byes = not tournament.allow_byes
    db.session.commit()
    mode = 'Byes enabled' if tournament.allow_byes else '3-player pods enabled'
    flash(mode, 'success')
    return redirect(url_for('tournament.view_tournament', tournament_id=tournament.id))


@bp.route('/<int:tournament_id>/toggle-seat-scoring', methods=['POST'])
def toggle_seat_scoring(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    tournament.seat_scoring = not tournament.seat_scoring
    db.session.commit()
    mode = 'Seat scoring enabled' if tournament.seat_scoring else 'Seat scoring disabled'
    flash(mode, 'success')
    return redirect(url_for('tournament.view_tournament', tournament_id=tournament.id))


@bp.route('/<int:tournament_id>/delete', methods=['POST'])
def delete_tournament(tournament_id):
    """Delete a tournament"""
    tournament = Tournament.query.get_or_404(tournament_id)
    if not current_user.is_admin() and tournament.owner_id != current_user.id:
        abort(403)

    db.session.delete(tournament)
    db.session.commit()

    # Reset auto-increment if no tournaments remain
    if Tournament.query.count() == 0:
        db.session.execute(db.text(
            "DELETE FROM sqlite_sequence WHERE name='tournaments'"
            if 'sqlite' in db.engine.url.drivername
            else "ALTER SEQUENCE tournaments_id_seq RESTART WITH 1"
        ))
        db.session.commit()

    flash(f'Tournament "{tournament.name}" deleted', 'success')
    return redirect(url_for('tournament.list_tournaments'))
