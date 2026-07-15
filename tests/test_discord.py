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


@pytest.fixture
def client(app, league):
    from app.models.user import User
    u = User(email='to@test.com', name='TO', role='admin')
    u.set_password('secret123')
    db.session.add(u)
    db.session.commit()
    c = app.test_client()
    c.post('/login', data={'email': 'to@test.com', 'password': 'secret123'})
    return c


def test_dashboard_shows_discord_section(client, league, monkeypatch):
    monkeypatch.setenv('DISCORD_APP_ID', '12345')
    r = client.get(f'/leagues/{league.id}')
    assert b'Add Bot to Your Server' not in r.data  # already linked in fixture
    assert b'Send Test Message' in r.data

    league.discord_channel_id = None
    db.session.commit()
    r = client.get(f'/leagues/{league.id}')
    assert b'Add Bot to Your Server' in r.data
    assert f'/link league_id:{league.id}'.encode() in r.data


def test_link_channel_via_ui(client, league):
    r = client.post(f'/leagues/{league.id}/discord',
                    data={'channel_id': '987654321'}, follow_redirects=True)
    assert r.status_code == 200
    assert league.discord_channel_id == '987654321'

    r = client.post(f'/leagues/{league.id}/discord',
                    data={'channel_id': 'not-a-number'}, follow_redirects=True)
    assert league.discord_channel_id == '987654321'  # unchanged
    assert b'must be numbers' in r.data


def test_unlink_channel_via_ui(client, league):
    client.post(f'/leagues/{league.id}/discord', data={'action': 'unlink'})
    assert league.discord_channel_id is None


def test_send_test_message_route(client, league, monkeypatch):
    monkeypatch.setenv('DISCORD_BOT_TOKEN', 'x')
    sent = {}

    def fake_post(channel_id, payload):
        sent['channel_id'] = channel_id
        return True, ''

    import app.services.discord_service as ds
    monkeypatch.setattr(ds, 'post_channel_message', fake_post)
    r = client.post(f'/leagues/{league.id}/discord/test', follow_redirects=True)
    assert b'Test message sent' in r.data
    assert sent['channel_id'] == CHANNEL


def test_bot_invite_url(app, monkeypatch):
    from app.services.discord_service import bot_invite_url
    monkeypatch.delenv('DISCORD_APP_ID', raising=False)
    assert bot_invite_url() is None
    monkeypatch.setenv('DISCORD_APP_ID', '12345')
    url = bot_invite_url()
    assert 'client_id=12345' in url and 'applications.commands' in url


def test_split_channels(league, monkeypatch):
    monkeypatch.setenv('DISCORD_BOT_TOKEN', 'x')
    league.discord_pairings_channel_id = '888'
    db.session.commit()

    # commands still resolve from either channel
    create_week_tournament(league, 1)
    resp = handle_interaction(interaction('checkin'))  # main channel
    assert 'checked in' in content(resp)
    resp = handle_interaction(interaction('whosplaying', channel_id='888'))  # pairings channel
    assert '1 checked in' in content(resp)

    # posts target the pairings channel
    import app.services.discord_service as ds
    sent = {}

    def fake_post(cid, payload):
        sent['cid'] = cid
        return True, ''

    monkeypatch.setattr(ds, 'post_channel_message', fake_post)
    ds.send_test_message(league)
    assert sent['cid'] == '888'


def test_link_with_pairings_channel_option(league):
    resp = handle_interaction(interaction('link', options={'league_id': league.id, 'pairings_channel': '999'},
                                          channel_id='555', permissions='32'))
    assert league.discord_channel_id == '555'
    assert league.discord_pairings_channel_id == '999'
    assert '<#999>' in content(resp)


def test_points_not_signed_up(league):
    create_week_tournament(league, 1)
    resp = handle_interaction(interaction('points'))
    assert '/signup' in content(resp)


def test_points_checkin_only(league):
    create_week_tournament(league, 1)
    handle_interaction(interaction('checkin'))
    resp = handle_interaction(interaction('points'))
    assert '1 league points' in content(resp)
    assert '1 check-in (1 pt)' in content(resp)


def test_points_with_completed_week(league):
    t = create_week_tournament(league, 1)
    for i, uid in enumerate(['1', '2', '3', '4', '5', '6', '7', '8']):
        handle_interaction(interaction('checkin', user_id=uid, username=f'P{uid}'))
    t.status = 'active'
    db.session.commit()

    round_obj = generate_swiss_pairings(t.id, 1)
    for pod in round_obj.pods:
        for j, a in enumerate(pod.assignments.order_by('seat_position').all()):
            a.placement = j + 1
            a.points_earned = 3 if j == 0 else 0
    t.status = 'completed'
    db.session.commit()

    # find a pod winner's discord id
    winner_id = round_obj.pods.first().assignments.order_by('seat_position').first().player
    lp_link = LeaguePlayerLink.query.filter_by(player_id=winner_id.id).first()
    winner_lp = LeaguePlayer.query.get(lp_link.league_player_id)

    resp = handle_interaction(interaction('points', user_id=winner_lp.discord_user_id))
    # 1 pod win (5) + 1 check-in (1) = 6
    assert '6 league points' in content(resp)
    assert '1 pod win (5 pts)' in content(resp)

    # a non-winner: 0 wins + 1 check-in = 1
    loser_a = round_obj.pods.first().assignments.order_by('seat_position').all()[1]
    loser_link = LeaguePlayerLink.query.filter_by(player_id=loser_a.player_id).first()
    loser_lp = LeaguePlayer.query.get(loser_link.league_player_id)
    resp = handle_interaction(interaction('points', user_id=loser_lp.discord_user_id))
    assert '1 league points' in content(resp)


def test_standings_new_formula(league):
    from app.services.league_service import calculate_league_standings
    t = create_week_tournament(league, 1)
    for uid in ['1', '2', '3', '4']:
        handle_interaction(interaction('checkin', user_id=uid, username=f'P{uid}'))
    t.status = 'active'
    db.session.commit()
    round_obj = generate_swiss_pairings(t.id, 1)
    for pod in round_obj.pods:
        for j, a in enumerate(pod.assignments.order_by('seat_position').all()):
            a.placement = j + 1
            a.points_earned = 3 if j == 0 else 0
    t.status = 'completed'
    db.session.commit()

    standings = calculate_league_standings(league)
    assert standings[0]['league_points'] == 6  # 1 win * 5 + 1 check-in
    assert all(s['league_points'] == 1 for s in standings[1:])  # check-in only


def test_standings_command(league):
    resp = handle_interaction(interaction('standings'))
    assert 'No standings yet' in content(resp)

    t = create_week_tournament(league, 1)
    for uid in ['1', '2', '3', '4']:
        handle_interaction(interaction('checkin', user_id=uid, username=f'P{uid}'))
    t.status = 'active'
    db.session.commit()
    round_obj = generate_swiss_pairings(t.id, 1)
    for pod in round_obj.pods:
        for j, a in enumerate(pod.assignments.order_by('seat_position').all()):
            a.placement = j + 1
            a.points_earned = 3 if j == 0 else 0
    t.status = 'completed'
    db.session.commit()

    resp = handle_interaction(interaction('standings'))
    body = content(resp)
    assert 'Test League Standings' in body
    assert '🥇' in body and '6 pts' in body and '1W' in body


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
