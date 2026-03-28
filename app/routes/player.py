from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from app import db
from app.models.tournament import Tournament
from app.models.player import Player

bp = Blueprint('player', __name__, url_prefix='/players')


@bp.route('/api/moxfield-fetch')
def moxfield_fetch():
    """Proxy endpoint for Moxfield API to avoid CORS issues."""
    url = request.args.get('url', '')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    from app.services.moxfield_service import fetch_moxfield_deck
    commander, deck_name = fetch_moxfield_deck(url)
    if commander:
        return jsonify({'commander': commander, 'deck_name': deck_name})
    return jsonify({'error': 'Could not fetch deck'}), 404


@bp.route('/tournament/<int:tournament_id>')
def list_players(tournament_id):
    """List all players in a tournament"""
    tournament = Tournament.query.get_or_404(tournament_id)
    players = tournament.players.order_by(Player.name).all()
    return render_template('player/list.html', tournament=tournament, players=players)


@bp.route('/tournament/<int:tournament_id>/register', methods=['GET', 'POST'])
def register_player(tournament_id):
    """Register a new player for a tournament"""
    tournament = Tournament.query.get_or_404(tournament_id)

    if tournament.status == 'completed':
        flash('Cannot register players for a completed tournament', 'error')
        return redirect(url_for('player.list_players', tournament_id=tournament_id))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        commander = request.form.get('commander', '').strip()
        decklist_url = request.form.get('decklist_url', '').strip()
        dci_number = request.form.get('dci_number', '').strip()

        if not name:
            flash('Player name is required', 'error')
            return render_template('player/register.html', tournament=tournament)

        existing = Player.query.filter_by(
            tournament_id=tournament_id,
            name=name
        ).first()

        if existing:
            flash(f'Player "{name}" is already registered', 'error')
            return render_template('player/register.html', tournament=tournament)

        # Auto-fetch commander from Moxfield if URL provided and commander not manually set
        if decklist_url and 'moxfield.com' in decklist_url and not commander:
            from app.services.moxfield_service import fetch_moxfield_deck
            fetched_commander, _ = fetch_moxfield_deck(decklist_url)
            if fetched_commander:
                commander = fetched_commander

        player = Player(
            tournament_id=tournament_id,
            name=name,
            commander=commander if commander else None,
            decklist_url=decklist_url if decklist_url else None,
            dci_number=dci_number if dci_number else None
        )

        db.session.add(player)
        db.session.commit()

        flash(f'Player "{name}" registered successfully!', 'success')
        return redirect(url_for('player.list_players', tournament_id=tournament_id))

    return render_template('player/register.html', tournament=tournament)


@bp.route('/join/<int:tournament_id>', methods=['GET', 'POST'])
def join_tournament(tournament_id):
    """Public-facing self-registration page for players."""
    tournament = Tournament.query.get_or_404(tournament_id)
    can_register = tournament.status in ('registration', 'active')
    players = tournament.players.order_by(Player.name).all()
    player_count = len(players)

    if request.method == 'POST' and can_register:
        name = request.form.get('name', '').strip()
        commander = request.form.get('commander', '').strip()
        decklist_url = request.form.get('decklist_url', '').strip()

        if not name:
            flash('Name is required', 'error')
            return render_template('player/join.html', tournament=tournament, players=players,
                                   player_count=player_count, can_register=can_register)

        existing = Player.query.filter_by(tournament_id=tournament_id, name=name).first()
        if existing:
            flash(f'"{name}" is already registered', 'error')
            return render_template('player/join.html', tournament=tournament, players=players,
                                   player_count=player_count, can_register=can_register)

        if decklist_url and 'moxfield.com' in decklist_url and not commander:
            from app.services.moxfield_service import fetch_moxfield_deck
            fetched_commander, _ = fetch_moxfield_deck(decklist_url)
            if fetched_commander:
                commander = fetched_commander

        player = Player(
            tournament_id=tournament_id,
            name=name,
            commander=commander if commander else None,
            decklist_url=decklist_url if decklist_url else None,
            user_id=current_user.id if current_user.is_authenticated else None
        )
        db.session.add(player)
        db.session.commit()

        flash(f'Welcome, {name}! You\'re registered.', 'success')
        return redirect(url_for('player.join_tournament', tournament_id=tournament_id))

    # Build current round seating data for player lookup
    seat_data = []
    timer_end = None
    current_round = None
    if tournament.status in ('active', 'playoffs') and tournament.current_round > 0:
        current_round = tournament.get_current_round()
        if current_round:
            timer_end = current_round.timer_end
            for pod in current_round.pods:
                for a in pod.assignments:
                    seat_data.append({
                        'name': a.player.name,
                        'table': pod.table_number,
                        'seat': a.seat_position,
                        'is_bye': pod.is_bye,
                        'opponents': [x.player.name for x in pod.assignments if x.player_id != a.player_id]
                    })

    # Build round history per player for display
    from app.models.round import Round
    from app.models.pod import Pod
    from app.models.pod_assignment import PodAssignment
    round_history = {}
    rounds = Round.query.filter_by(tournament_id=tournament_id).order_by(Round.round_number).all()
    for r in rounds:
        for pod in r.pods:
            for a in pod.assignments:
                pname = a.player.name
                if pname not in round_history:
                    round_history[pname] = []
                entry = {
                    'round': r.round_number,
                    'table': pod.table_number,
                    'is_bye': pod.is_bye,
                    'opponents': [x.player.name for x in pod.assignments if x.player_id != a.player_id],
                    'result': 'bye' if pod.is_bye else ('win' if a.placement == 1 else ('draw' if a.points_earned and a.points_earned > 0 and a.placement is None else ('loss' if a.points_earned is not None else 'pending'))),
                    'points': a.points_earned
                }
                round_history[pname].append(entry)

    # Build pod pairings data for current round display
    pods_data = []
    if current_round:
        for pod in current_round.pods.order_by('pod_number').all():
            pod_info = {
                'table': pod.table_number,
                'is_bye': pod.is_bye,
                'status': pod.status,
                'players': []
            }
            for a in sorted(pod.assignments, key=lambda x: x.seat_position):
                pod_info['players'].append({
                    'name': a.player.name,
                    'commander': a.player.commander or '',
                    'seat': a.seat_position
                })
            pods_data.append(pod_info)

    # Build standings data
    standings_data = []
    projections_data = {}
    from app.services.standings_service import calculate_standings
    if tournament.current_round and tournament.current_round > 0:
        standings = calculate_standings(tournament)
        from app.routes.standings import _calculate_projections
        projections_data = _calculate_projections(tournament, standings)
        for s in standings:
            standings_data.append({
                'name': s['player'].name,
                'points': s['points'],
                'omw': s['omw_percentage'],
                'gw': s['gw_percentage'],
                'matches': s['matches_played'],
                'dropped': s['player'].dropped,
                'player_id': s['player'].id,
                'projection': projections_data.get(s['player'].id, ''),
            })

    return render_template('player/join.html', tournament=tournament, players=players,
                           player_count=player_count, can_register=can_register,
                           seat_data=seat_data, round_history=round_history,
                           timer_end=timer_end, pods_data=pods_data,
                           standings_data=standings_data)


@bp.route('/tournament/<int:tournament_id>/import-csv', methods=['POST'])
def import_csv(tournament_id):
    """Import players from a CSV file."""
    import csv
    import io
    tournament = Tournament.query.get_or_404(tournament_id)

    if tournament.status == 'completed':
        flash('Cannot import players to a completed tournament', 'error')
        return redirect(url_for('player.list_players', tournament_id=tournament_id))

    file = request.files.get('csv_file')
    if not file or not file.filename:
        flash('No file selected', 'error')
        return redirect(url_for('player.list_players', tournament_id=tournament_id))

    try:
        content = file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content))

        # Normalize column headers (case-insensitive, strip whitespace)
        if not reader.fieldnames:
            flash('CSV file is empty', 'error')
            return redirect(url_for('player.list_players', tournament_id=tournament_id))

        added = 0
        skipped = 0
        for row in reader:
            # Case-insensitive column lookup
            norm = {k.strip().lower(): v.strip() for k, v in row.items() if k}
            name = norm.get('name') or norm.get('player') or norm.get('player name') or ''
            if not name:
                continue

            existing = Player.query.filter_by(tournament_id=tournament_id, name=name).first()
            if existing:
                skipped += 1
                continue

            commander = norm.get('commander') or norm.get('commanders') or ''
            decklist_url = norm.get('decklist') or norm.get('decklist_url') or norm.get('url') or norm.get('deck') or ''

            # Auto-fetch commander from Moxfield if URL provided
            if decklist_url and 'moxfield.com' in decklist_url and not commander:
                from app.services.moxfield_service import fetch_moxfield_deck
                fetched, _ = fetch_moxfield_deck(decklist_url)
                if fetched:
                    commander = fetched

            player = Player(
                tournament_id=tournament_id,
                name=name,
                commander=commander if commander else None,
                decklist_url=decklist_url if decklist_url else None
            )
            db.session.add(player)
            added += 1

        db.session.commit()
        msg = f'Imported {added} player{"s" if added != 1 else ""}'
        if skipped:
            msg += f' ({skipped} duplicate{"s" if skipped != 1 else ""} skipped)'
        flash(msg, 'success')

    except Exception as e:
        flash(f'Error reading CSV: {str(e)}', 'error')

    return redirect(url_for('player.list_players', tournament_id=tournament_id))


@bp.route('/<int:player_id>/edit', methods=['POST'])
def edit_player(player_id):
    player = Player.query.get_or_404(player_id)
    commander = request.form.get('commander', '').strip()
    decklist_url = request.form.get('decklist_url', '').strip()

    if decklist_url:
        player.decklist_url = decklist_url
        if not commander and 'moxfield.com' in decklist_url:
            from app.services.moxfield_service import fetch_moxfield_deck
            fetched_commander, _ = fetch_moxfield_deck(decklist_url)
            if fetched_commander:
                commander = fetched_commander

    player.commander = commander if commander else player.commander
    db.session.commit()
    flash(f'Updated {player.name}', 'success')
    return redirect(url_for('player.list_players', tournament_id=player.tournament_id))


@bp.route('/<int:player_id>/drop', methods=['POST'])
def drop_player(player_id):
    """Drop a player from the tournament"""
    player = Player.query.get_or_404(player_id)
    tournament = player.tournament

    if tournament.status == 'completed':
        flash('Cannot drop players from a completed tournament', 'error')
        return redirect(url_for('player.list_players', tournament_id=tournament.id))

    if player.dropped:
        flash(f'Player "{player.name}" is already dropped', 'warning')
        return redirect(url_for('player.list_players', tournament_id=tournament.id))

    player.dropped = True
    player.drop_round = tournament.current_round
    db.session.commit()

    flash(f'Player "{player.name}" has been dropped from the tournament', 'success')
    return redirect(url_for('player.list_players', tournament_id=tournament.id))


@bp.route('/<int:player_id>/undrop', methods=['POST'])
def undrop_player(player_id):
    """Re-add a dropped player to the tournament"""
    player = Player.query.get_or_404(player_id)
    tournament = player.tournament

    if not player.dropped:
        flash(f'Player "{player.name}" is not dropped', 'warning')
        return redirect(url_for('player.list_players', tournament_id=tournament.id))

    player.dropped = False
    player.drop_round = None
    db.session.commit()

    flash(f'Player "{player.name}" has been re-added to the tournament', 'success')
    return redirect(url_for('player.list_players', tournament_id=tournament.id))


@bp.route('/<int:player_id>/delete', methods=['POST'])
def delete_player(player_id):
    """Delete a player from the tournament"""
    player = Player.query.get_or_404(player_id)
    tournament_id = player.tournament_id
    player_name = player.name

    # Only allow deletion if tournament hasn't started or player hasn't played any matches
    if player.get_matches_played() > 0:
        flash(f'Cannot delete "{player_name}" - they have already played matches', 'error')
        return redirect(url_for('player.list_players', tournament_id=tournament_id))

    db.session.delete(player)
    db.session.commit()

    flash(f'Player "{player_name}" deleted', 'success')
    return redirect(url_for('player.list_players', tournament_id=tournament_id))
