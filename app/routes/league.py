from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import current_user
from datetime import datetime
from app import db
from app.models.league import League
from app.models.league_player import LeaguePlayer
from app.models.league_player_link import LeaguePlayerLink
from app.models.tournament import Tournament
from app.models.player import Player
from app.services.league_service import (
    create_league, create_week_tournament, get_or_create_league_player,
    add_player_to_week, calculate_league_standings, get_week_recap,
    get_player_detail, get_roster_search
)

bp = Blueprint('league', __name__, url_prefix='/leagues')


@bp.route('/')
def list_leagues():
    q = League.query
    if not current_user.is_admin():
        q = q.filter_by(owner_id=current_user.id)
    leagues = q.order_by(League.created_at.desc()).all()
    return render_template('league/list.html', leagues=leagues)


@bp.route('/create', methods=['GET', 'POST'])
def create():
    if current_user.is_player():
        abort(403)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        num_weeks = request.form.get('num_weeks', 0, type=int)

        if not name:
            flash('League name is required', 'error')
            return render_template('league/create.html')
        if num_weeks < 1:
            flash('Number of weeks must be at least 1', 'error')
            return render_template('league/create.html')

        league = create_league(name, num_weeks, owner_id=current_user.id)
        flash(f'League "{name}" created!', 'success')
        return redirect(url_for('league.dashboard', league_id=league.id))

    return render_template('league/create.html')


@bp.route('/<int:league_id>')
def dashboard(league_id):
    league = League.query.get_or_404(league_id)
    if not current_user.is_admin() and league.owner_id != current_user.id:
        abort(403)
    tournaments = league.tournaments.order_by(Tournament.week_number).all()
    standings = calculate_league_standings(league)
    roster_count = league.league_players.count()

    # Build week status list
    weeks = []
    t_by_week = {t.week_number: t for t in tournaments}
    for w in range(1, league.num_weeks + 1):
        t = t_by_week.get(w)
        weeks.append({
            'number': w,
            'tournament': t,
            'status': t.status if t else 'not_created',
        })

    return render_template('league/dashboard.html', league=league, weeks=weeks,
                           standings=standings[:10], roster_count=roster_count)


@bp.route('/<int:league_id>/standings')
def standings(league_id):
    league = League.query.get_or_404(league_id)
    standings = calculate_league_standings(league)
    return render_template('league/standings.html', league=league, standings=standings)


@bp.route('/<int:league_id>/week/<int:week_number>/create', methods=['POST'])
def create_week(league_id, week_number):
    league = League.query.get_or_404(league_id)

    scoring_system = request.form.get('scoring_system', '3-1-0-0')
    bye_points = request.form.get('bye_points', 1, type=int)
    draw_points = request.form.get('draw_points', 1, type=int)
    allow_byes = request.form.get('allow_byes', '1') == '1'
    round_timer = request.form.get('round_timer_minutes', 80, type=int)

    try:
        t = create_week_tournament(league, week_number,
                                   scoring_system=scoring_system,
                                   bye_points=bye_points,
                                   draw_points=draw_points,
                                   allow_byes=allow_byes,
                                   round_timer_minutes=round_timer)
        flash(f'Week {week_number} tournament created!', 'success')
        return redirect(url_for('league.add_players', league_id=league_id, week_number=week_number))
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('league.dashboard', league_id=league_id))


@bp.route('/<int:league_id>/week/<int:week_number>')
def view_week(league_id, week_number):
    t = Tournament.query.filter_by(league_id=league_id, week_number=week_number).first_or_404()
    return redirect(url_for('tournament.view_tournament', tournament_id=t.id))


@bp.route('/<int:league_id>/week/<int:week_number>/recap')
def week_recap(league_id, week_number):
    league = League.query.get_or_404(league_id)
    recap = get_week_recap(league, week_number)
    if not recap:
        flash(f'Week {week_number} not found', 'error')
        return redirect(url_for('league.dashboard', league_id=league_id))
    return render_template('league/week_recap.html', league=league, week_number=week_number, recap=recap)


@bp.route('/<int:league_id>/roster')
def roster(league_id):
    league = League.query.get_or_404(league_id)
    players = league.league_players.order_by(LeaguePlayer.name).all()
    return render_template('league/roster.html', league=league, players=players)


@bp.route('/<int:league_id>/roster/add', methods=['POST'])
def add_roster_player(league_id):
    league = League.query.get_or_404(league_id)
    name = request.form.get('name', '').strip()
    if not name:
        flash('Player name is required', 'error')
        return redirect(url_for('league.roster', league_id=league_id))

    current_week = league.get_current_week() or 1
    lp = get_or_create_league_player(league_id, name, current_week)
    flash(f'"{name}" added to roster', 'success')
    return redirect(url_for('league.roster', league_id=league_id))


@bp.route('/<int:league_id>/week/<int:week_number>/add-players', methods=['GET', 'POST'])
def add_players(league_id, week_number):
    league = League.query.get_or_404(league_id)
    tournament = Tournament.query.filter_by(league_id=league_id, week_number=week_number).first_or_404()

    if request.method == 'POST':
        # Handle adding selected roster players
        selected_ids = request.form.getlist('league_player_ids')
        new_name = request.form.get('new_player_name', '').strip()

        added = 0
        for lp_id in selected_ids:
            lp = LeaguePlayer.query.get(int(lp_id))
            if lp and lp.league_id == league.id:
                # Check if already linked to this tournament
                existing = LeaguePlayerLink.query.filter_by(
                    league_player_id=lp.id, tournament_id=tournament.id
                ).first()
                if not existing:
                    add_player_to_week(lp, tournament)
                    added += 1

        if new_name:
            lp = get_or_create_league_player(league_id, new_name, week_number)
            existing = LeaguePlayerLink.query.filter_by(
                league_player_id=lp.id, tournament_id=tournament.id
            ).first()
            if not existing:
                add_player_to_week(lp, tournament)
                added += 1

        if added:
            flash(f'Added {added} player{"s" if added != 1 else ""} to Week {week_number}', 'success')
        return redirect(url_for('league.add_players', league_id=league_id, week_number=week_number))

    # GET: show roster with checkboxes
    roster = league.league_players.order_by(LeaguePlayer.name).all()
    # Mark who is already in this week
    linked_lp_ids = set()
    links = LeaguePlayerLink.query.filter_by(tournament_id=tournament.id).all()
    for link in links:
        linked_lp_ids.add(link.league_player_id)

    return render_template('league/add_players.html', league=league, tournament=tournament,
                           week_number=week_number, roster=roster, linked_lp_ids=linked_lp_ids)


@bp.route('/<int:league_id>/player/<int:lp_id>')
def player_detail(league_id, lp_id):
    league = League.query.get_or_404(league_id)
    detail = get_player_detail(league, lp_id)
    return render_template('league/player_detail.html', league=league, detail=detail)


@bp.route('/<int:league_id>/complete', methods=['POST'])
def complete_league(league_id):
    league = League.query.get_or_404(league_id)
    league.status = 'completed'
    db.session.commit()
    flash(f'League "{league.name}" marked as completed', 'success')
    return redirect(url_for('league.dashboard', league_id=league_id))


@bp.route('/<int:league_id>/delete', methods=['POST'])
def delete_league(league_id):
    league = League.query.get_or_404(league_id)
    if not current_user.is_admin() and league.owner_id != current_user.id:
        abort(403)
    name = league.name
    db.session.delete(league)
    db.session.commit()
    flash(f'League "{name}" deleted', 'success')
    return redirect(url_for('league.list_leagues'))


@bp.route('/api/<int:league_id>/roster-search')
def roster_search(league_id):
    q = request.args.get('q', '')
    results = get_roster_search(league_id, q)
    return jsonify([{'id': lp.id, 'name': lp.name} for lp in results])
