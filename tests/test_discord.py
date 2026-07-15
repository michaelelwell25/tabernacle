"""Tests for Discord integration: slash command handlers and pairing payloads."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app import create_app, db
from app.models import Tournament, Player
from app.models.league import League
from app.models.league_player import LeaguePlayer
from app.models.league_player_link import LeaguePlayerLink
from app.services.league_service import create_league, create_week_tournament, \
    get_or_create_league_player, add_player_to_week
from app.services.pairing_service import generate_swiss_pairings
from app.services.discord_service import handle_interaction, build_pairings_payload

CHANNEL = '111222333444555666'


@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def league(app):
    lg = create_league('Test League', num_weeks=8)
    lg.discord_channel_id = CHANNEL
    db.session.commit()
    return lg


def interaction(command, user_id='42', username='Mike', options=None,
                channel_id=CHANNEL, permissions='0'):
    return {
        'type': 2,
        'channel_id': channel_id,
        'member': {
            'user': {'id': user_id, 'username': username, 'global_name': username},
            'permissions': permissions,
        },
        'data': {'name': command, 'options': [
            {'name': k, 'value': v} for k, v in (options or {}).items()
        ]},
    }


def content(resp):
    return resp['data']['content']


def test_ping_pong(app):
    assert handle_interaction({'type': 1}) == {'type': 1}


def test_unlinked_channel(league):
    resp = handle_interaction(interaction('signup', channel_id='999'))
    assert 'not linked' in content(resp)


def test_link_requires_permission(league):
    resp = handle_interaction(interaction('link', options={'league_id': league.id}))
    assert 'Manage Server' in content(resp)


def test_link_sets_channel(league):
    resp = handle_interaction(interaction('link', options={'league_id': league.id},
                                          channel_id='777', permissions='32'))
    assert 'now linked' in content(resp)
    assert league.discord_channel_id == '777'


def test_signup_creates_roster_entry(league):
    resp = handle_interaction(interaction('signup'))
    assert 'Mike' in content(resp)
    lp = LeaguePlayer.query.filter_by(league_id=league.id, name='Mike').first()
    assert lp is not None
    assert lp.discord_user_id == '42'


def test_signup_custom_name_and_duplicate(league):
    handle_interaction(interaction('signup', options={'name': 'MikeyRocks'}))
    resp = handle_interaction(interaction('signup'))
    assert 'already on the roster' in content(resp)


def test_signup_claims_preexisting_name(league):
    get_or_create_league_player(league.id, 'Mike')
    handle_interaction(interaction('signup'))
    lp = LeaguePlayer.query.filter_by(league_id=league.id, name='Mike').first()
    assert lp.discord_user_id == '42'
    assert LeaguePlayer.query.filter_by(league_id=league.id).count() == 1


def test_signup_name_conflict(league):
    handle_interaction(interaction('signup', user_id='1', username='Mike'))
    resp = handle_interaction(interaction('signup', user_id='2', username='Mike'))
    assert 'already claimed' in content(resp)


def test_checkin_no_open_week(league):
    resp = handle_interaction(interaction('checkin'))
    assert 'No week is open' in content(resp)


def test_checkin_auto_signup_and_duplicate(league):
    t = create_week_tournament(league, 1)
    resp = handle_interaction(interaction('checkin'))
    assert 'checked in for Week 1' in content(resp)
    assert Player.query.filter_by(tournament_id=t.id, name='Mike').count() == 1

    resp = handle_interaction(interaction('checkin'))
    assert 'already checked in' in content(resp)
    assert Player.query.filter_by(tournament_id=t.id).count() == 1


def test_checkout(league):
    t = create_week_tournament(league, 1)
    handle_interaction(interaction('checkin'))
    resp = handle_interaction(interaction('checkout'))
    assert 'out for Week 1' in content(resp)
    assert Player.query.filter_by(tournament_id=t.id).count() == 0
    assert LeaguePlayerLink.query.filter_by(tournament_id=t.id).count() == 0
    # roster entry survives
    assert LeaguePlayer.query.filter_by(league_id=league.id, name='Mike').count() == 1


def test_whosplaying(league):
    create_week_tournament(league, 1)
    resp = handle_interaction(interaction('whosplaying'))
    assert 'Nobody has checked in' in content(resp)

    handle_interaction(interaction('checkin', user_id='1', username='Alice'))
    handle_interaction(interaction('checkin', user_id='2', username='Bob'))
    resp = handle_interaction(interaction('whosplaying'))
    assert '2 checked in' in content(resp)
    assert 'Alice' in content(resp) and 'Bob' in content(resp)


def test_pairings_payload_mentions_and_pods(league):
    t = create_week_tournament(league, 1)
    for i in range(8):
        lp = get_or_create_league_player(league.id, f'P{i+1}')
        lp.discord_user_id = str(100 + i) if i < 4 else None
        db.session.commit()
        add_player_to_week(lp, t)
    t.status = 'active'
    db.session.commit()

    round_obj = generate_swiss_pairings(t.id, 1)
    db.session.commit()

    payload = build_pairings_payload(t, round_obj)
    assert 'Round 1' in payload['content']
    fields = payload['embeds'][0]['fields']
    assert len(fields) == 2  # 8 players -> 2 pods
    all_text = ' '.join(f['value'] for f in fields)
    assert '<@100>' in all_text  # linked player mentioned
    assert 'P5' in all_text or 'P6' in all_text  # unlinked player by name
