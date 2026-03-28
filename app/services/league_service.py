from datetime import datetime, date
from app import db
from app.models.league import League
from app.models.league_player import LeaguePlayer
from app.models.league_player_link import LeaguePlayerLink
from app.models.tournament import Tournament
from app.models.player import Player
from app.models.pod import Pod
from app.models.pod_assignment import PodAssignment
from app.models.pairing_history import PairingHistory


def create_league(name, num_weeks, owner_id=None):
    league = League(name=name, num_weeks=num_weeks, owner_id=owner_id)
    db.session.add(league)
    db.session.commit()
    return league


def create_week_tournament(league, week_number, tournament_name=None, tournament_date=None,
                           scoring_system='3-1-0-0', bye_points=1, draw_points=1,
                           allow_byes=True, round_timer_minutes=80):
    if week_number < 1 or week_number > league.num_weeks:
        raise ValueError(f'Week number must be between 1 and {league.num_weeks}')

    existing = Tournament.query.filter_by(league_id=league.id, week_number=week_number).first()
    if existing:
        raise ValueError(f'Week {week_number} tournament already exists')

    name = tournament_name or f'{league.name} - Week {week_number}'
    t = Tournament(
        name=name,
        date=tournament_date or date.today(),
        scoring_system=scoring_system,
        bye_points=bye_points,
        draw_points=draw_points,
        allow_byes=allow_byes,
        round_timer_minutes=round_timer_minutes,
        league_id=league.id,
        week_number=week_number,
        owner_id=league.owner_id,
        status='registration'
    )
    db.session.add(t)
    db.session.commit()
    return t


def get_or_create_league_player(league_id, name, week_number=1):
    lp = LeaguePlayer.query.filter_by(league_id=league_id, name=name).first()
    if not lp:
        lp = LeaguePlayer(league_id=league_id, name=name, joined_week=week_number)
        db.session.add(lp)
        db.session.commit()
    return lp


def add_player_to_week(league_player, tournament, commander=None, decklist_url=None):
    existing_link = LeaguePlayerLink.query.filter_by(
        league_player_id=league_player.id, tournament_id=tournament.id
    ).first()
    if existing_link:
        return Player.query.get(existing_link.player_id)

    existing_player = Player.query.filter_by(
        tournament_id=tournament.id, name=league_player.name
    ).first()
    if existing_player:
        return existing_player

    player = Player(
        tournament_id=tournament.id,
        name=league_player.name,
        commander=commander,
        decklist_url=decklist_url
    )
    db.session.add(player)
    db.session.flush()

    link = LeaguePlayerLink(
        league_player_id=league_player.id,
        player_id=player.id,
        tournament_id=tournament.id
    )
    db.session.add(link)
    db.session.commit()
    return player


def _build_league_data(league):
    """Gather all match data for a league. Returns per-league-player stats."""
    tournaments = Tournament.query.filter_by(league_id=league.id).order_by(Tournament.week_number).all()
    completed = [t for t in tournaments if t.status == 'completed']

    league_players = LeaguePlayer.query.filter_by(league_id=league.id).all()

    # Build player_id -> league_player_id mapping
    all_links = LeaguePlayerLink.query.filter(
        LeaguePlayerLink.tournament_id.in_([t.id for t in tournaments])
    ).all()
    player_to_lp = {link.player_id: link.league_player_id for link in all_links}
    lp_to_links = {}
    for link in all_links:
        lp_to_links.setdefault(link.league_player_id, []).append(link)

    # For each league player, gather wins/losses per week
    lp_stats = {}
    for lp in league_players:
        lp_stats[lp.id] = {
            'league_player': lp,
            'wins': 0,
            'losses': 0,
            'weeks_played': 0,
            'weekly': {},  # week_number -> {wins, losses, commander}
            'opponent_lp_ids': [],  # all opponents faced (as league_player_ids)
        }

    for t in completed:
        t_links = {link.player_id: link.league_player_id
                    for link in all_links if link.tournament_id == t.id}
        t_lp_to_player = {link.league_player_id: link.player_id
                          for link in all_links if link.tournament_id == t.id}

        # Get all completed pod assignments for this tournament
        players_in_t = Player.query.filter_by(tournament_id=t.id).all()
        player_ids = [p.id for p in players_in_t]
        player_map = {p.id: p for p in players_in_t}

        assignments = db.session.query(PodAssignment).join(Pod).filter(
            PodAssignment.player_id.in_(player_ids),
            PodAssignment.points_earned.isnot(None)
        ).all()

        # Group assignments by pod to find opponents
        pod_assignments = {}
        for a in assignments:
            pod_assignments.setdefault(a.pod_id, []).append(a)

        # Track per-player wins/losses this tournament
        player_week_stats = {}
        for a in assignments:
            pid = a.player_id
            if pid not in player_week_stats:
                player_week_stats[pid] = {'wins': 0, 'losses': 0}

            pod = Pod.query.get(a.pod_id)
            if pod.is_bye:
                player_week_stats[pid]['wins'] += 1  # bye = win
            elif a.placement == 1:
                player_week_stats[pid]['wins'] += 1
            else:
                player_week_stats[pid]['losses'] += 1

        # Map back to league players
        for pid, stats in player_week_stats.items():
            lp_id = t_links.get(pid)
            if lp_id and lp_id in lp_stats:
                lp_stats[lp_id]['wins'] += stats['wins']
                lp_stats[lp_id]['losses'] += stats['losses']
                lp_stats[lp_id]['weeks_played'] += 1

                player_obj = player_map.get(pid)
                lp_stats[lp_id]['weekly'][t.week_number] = {
                    'wins': stats['wins'],
                    'losses': stats['losses'],
                    'commander': player_obj.commander if player_obj else None,
                    'tournament_id': t.id,
                }

        # Track opponents via pod co-assignments
        for pod_id, pod_as in pod_assignments.items():
            pod = Pod.query.get(pod_id)
            if pod.is_bye:
                continue
            pids_in_pod = [a.player_id for a in pod_as]
            for pid in pids_in_pod:
                lp_id = t_links.get(pid)
                if not lp_id or lp_id not in lp_stats:
                    continue
                for opp_pid in pids_in_pod:
                    if opp_pid == pid:
                        continue
                    opp_lp_id = t_links.get(opp_pid)
                    if opp_lp_id:
                        lp_stats[lp_id]['opponent_lp_ids'].append(opp_lp_id)

    return lp_stats


def calculate_league_standings(league):
    lp_stats = _build_league_data(league)

    # Compute win% for each league player
    win_pcts = {}
    for lp_id, stats in lp_stats.items():
        total = stats['wins'] + stats['losses']
        win_pcts[lp_id] = stats['wins'] / total if total > 0 else 0.0

    standings = []
    for lp_id, stats in lp_stats.items():
        lp = stats['league_player']
        total_matches = stats['wins'] + stats['losses']
        win_pct = win_pcts[lp_id]

        # Opponent win%: average win% of all opponents faced
        opp_ids = stats['opponent_lp_ids']
        if opp_ids:
            ow_pct = sum(win_pcts.get(oid, 0.0) for oid in opp_ids) / len(opp_ids)
        else:
            ow_pct = 0.0

        # Late-join bonus points
        late_join_pts = max(0, lp.joined_week - 1)

        # League points: 2 per win, 1 per loss + late-join bonus
        league_pts = (stats['wins'] * 2) + (stats['losses'] * 1) + late_join_pts

        standings.append({
            'league_player': lp,
            'league_points': league_pts,
            'wins': stats['wins'],
            'losses': stats['losses'],
            'total_matches': total_matches,
            'win_pct': win_pct,
            'opp_win_pct': ow_pct,
            'weeks_played': stats['weeks_played'],
            'joined_week': lp.joined_week,
            'late_join_pts': late_join_pts,
            'weekly': stats['weekly'],
        })

    standings.sort(key=lambda x: (-x['league_points'], -x['win_pct'], -x['opp_win_pct']))
    for rank, s in enumerate(standings, 1):
        s['rank'] = rank

    return standings


def get_week_recap(league, week_number):
    tournament = Tournament.query.filter_by(league_id=league.id, week_number=week_number).first()
    if not tournament:
        return None

    standings = calculate_league_standings(league)
    week_results = []
    for s in standings:
        week_data = s['weekly'].get(week_number)
        if week_data:
            week_results.append({
                'name': s['league_player'].name,
                'week_wins': week_data['wins'],
                'week_losses': week_data['losses'],
                'week_pts': (week_data['wins'] * 2) + (week_data['losses'] * 1),
                'commander': week_data['commander'],
                'league_rank': s['rank'],
                'league_points': s['league_points'],
            })

    week_results.sort(key=lambda x: (-x['week_pts'], x['name']))
    return {'tournament': tournament, 'results': week_results, 'standings': standings}


def get_player_detail(league, league_player_id):
    lp = LeaguePlayer.query.get_or_404(league_player_id)
    standings = calculate_league_standings(league)

    player_standing = None
    for s in standings:
        if s['league_player'].id == lp.id:
            player_standing = s
            break

    return {'league_player': lp, 'standing': player_standing}


def get_roster_search(league_id, query):
    return LeaguePlayer.query.filter(
        LeaguePlayer.league_id == league_id,
        LeaguePlayer.name.ilike(f'%{query}%')
    ).limit(20).all()
