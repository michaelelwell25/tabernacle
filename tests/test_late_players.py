"""Tests for adding league players to a week that has already started, and for
repairing players registered without a league roster link."""
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app import create_app, db
from app.models import Tournament, Player
from app.models.user import User
from app.models.league import League
from app.models.league_player import LeaguePlayer
from app.models.league_player_link import LeaguePlayerLink
from app.services.league_service import (
    create_league, create_week_tournament, get_or_create_league_player,
    add_player_to_week, calculate_league_standings, get_unlinked_counts,
)
from app.services.pairing_service import generate_swiss_pairings


@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def logged_in_client(app):
    """Test client authenticated as a TO (every route sits behind login)."""
    user = User(email='to@example.com', name='TO', role='to')
    user.set_password('secret')
    db.session.add(user)
    db.session.commit()
    client = app.test_client()
    client.post('/login', data={'email': 'to@example.com', 'password': 'secret'})
    return client


def make_week(n_players=8, week=1):
    league = create_league('Test League', 4)
    t = create_week_tournament(league, week)
    for i in range(n_players):
        lp = get_or_create_league_player(league.id, f'P{i+1:02d}', week)
        add_player_to_week(lp, t)
    t.status = 'active'
    db.session.commit()
    return league, t


def play_round(t, round_number):
    r = generate_swiss_pairings(t.id, round_number)
    t.current_round = round_number
    db.session.commit()
    for pod in r.pods:
        assignments = sorted(pod.assignments, key=lambda a: a.player_id)
        for idx, a in enumerate(assignments):
            a.placement = 1 if idx == 0 else 2
            a.points_earned = 3 if idx == 0 else 0
        pod.status = 'completed'
    db.session.commit()
    return r


def test_late_player_gets_paired_next_round(app):
    league, t = make_week(8)
    play_round(t, 1)

    lp = get_or_create_league_player(league.id, 'Latecomer', 1)
    player = add_player_to_week(lp, t)

    r2 = generate_swiss_pairings(t.id, 2)
    paired = {a.player_id for pod in r2.pods for a in pod.assignments}
    assert player.id in paired


def test_late_player_check_in_counts_in_standings(app):
    league, t = make_week(8)
    play_round(t, 1)

    lp = get_or_create_league_player(league.id, 'Latecomer', 1)
    add_player_to_week(lp, t)
    t.status = 'completed'
    db.session.commit()

    row = next(s for s in calculate_league_standings(league)
               if s['league_player'].id == lp.id)
    assert row['checkins'] == 1


def test_manual_registration_on_league_week_is_linked(app):
    league, t = make_week(4)
    client = logged_in_client(app)
    resp = client.post(f'/players/tournament/{t.id}/register',
                       data={'name': 'Latecomer'}, follow_redirects=True)
    assert resp.status_code == 200

    player = Player.query.filter_by(tournament_id=t.id, name='Latecomer').first()
    assert player is not None
    link = LeaguePlayerLink.query.filter_by(player_id=player.id).first()
    assert link is not None, 'manually registered league player should get a roster link'
    assert LeaguePlayer.query.get(link.league_player_id).name == 'Latecomer'


def test_unlinked_player_is_detected_and_can_be_linked(app):
    league, t = make_week(4)
    # Simulate the old bug: a player registered straight into the week
    orphan = Player(tournament_id=t.id, name='Ghost')
    db.session.add(orphan)
    db.session.commit()

    assert get_unlinked_counts(league) == {1: 1}

    # A roster entry for the same human already exists from an earlier week
    lp = get_or_create_league_player(league.id, 'Ghost', 1)

    client = logged_in_client(app)
    resp = client.post(f'/leagues/{league.id}/week/1/add-players',
                       data={'action': 'link', 'player_id': orphan.id,
                             'link_league_player_id': lp.id},
                       follow_redirects=True)
    assert resp.status_code == 200

    link = LeaguePlayerLink.query.filter_by(player_id=orphan.id).first()
    assert link is not None and link.league_player_id == lp.id
    assert get_unlinked_counts(league) == {}


def test_adding_roster_player_adopts_existing_unlinked_row(app):
    league, t = make_week(4)
    orphan = Player(tournament_id=t.id, name='Ghost')
    db.session.add(orphan)
    db.session.commit()

    lp = get_or_create_league_player(league.id, 'Ghost', 1)
    client = logged_in_client(app)
    client.post(f'/leagues/{league.id}/week/1/add-players',
                data={'league_player_ids': [lp.id]}, follow_redirects=True)

    # No duplicate player row, and the existing one now belongs to the roster entry
    assert Player.query.filter_by(tournament_id=t.id, name='Ghost').count() == 1
    link = LeaguePlayerLink.query.filter_by(league_player_id=lp.id, tournament_id=t.id).first()
    assert link is not None and link.player_id == orphan.id


def test_link_rejects_double_checkin(app):
    league, t = make_week(4)
    lp = LeaguePlayer.query.filter_by(league_id=league.id, name='P01').first()
    orphan = Player(tournament_id=t.id, name='P01 dupe')
    db.session.add(orphan)
    db.session.commit()

    client = logged_in_client(app)
    client.post(f'/leagues/{league.id}/week/1/add-players',
                data={'action': 'link', 'player_id': orphan.id,
                      'link_league_player_id': lp.id},
                follow_redirects=True)

    # P01 is already checked in under their own player row; no second link
    assert LeaguePlayerLink.query.filter_by(league_player_id=lp.id).count() == 1
    assert LeaguePlayerLink.query.filter_by(player_id=orphan.id).first() is None


def test_playoff_week_rejects_new_players(app):
    league, t = make_week(4)
    t.status = 'playoffs'
    db.session.commit()
    lp = get_or_create_league_player(league.id, 'TooLate', 1)

    client = logged_in_client(app)
    client.post(f'/leagues/{league.id}/week/1/add-players',
                data={'league_player_ids': [lp.id]}, follow_redirects=True)

    assert LeaguePlayerLink.query.filter_by(league_player_id=lp.id).first() is None
