"""Every route that creates a round must announce it to Discord.

Regression: results.submit_and_next generated the next round but never called
post_round_pairings, so rounds created by submitting the last result went
unannounced. Only round_bp.generate_round posted.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app import create_app, db
from app.models.user import User
from app.models.pod import Pod
from app.services.league_service import create_league, create_week_tournament, \
    get_or_create_league_player, add_player_to_week

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
    lg = create_league('Announce League', num_weeks=8)
    lg.discord_channel_id = CHANNEL
    db.session.commit()
    return lg


@pytest.fixture
def tournament(league):
    t = create_week_tournament(league, 1)
    for i in range(8):
        add_player_to_week(get_or_create_league_player(league.id, f'P{i+1}'), t)
    t.status = 'active'
    db.session.commit()
    return t


@pytest.fixture
def client(app):
    u = User(email='to@test.com', name='TO', role='admin')
    u.set_password('secret123')
    db.session.add(u)
    db.session.commit()
    c = app.test_client()
    c.post('/login', data={'email': 'to@test.com', 'password': 'secret123'})
    return c


@pytest.fixture
def posts(monkeypatch):
    """Capture every payload the app tries to send to Discord."""
    monkeypatch.setenv('DISCORD_BOT_TOKEN', 'x')
    sent = []

    def fake_post(channel_id, payload):
        sent.append((channel_id, payload))
        return True, ''

    import app.services.discord_service as ds
    monkeypatch.setattr(ds, 'post_channel_message', fake_post)
    return sent


def _fill_results(round_obj):
    """Build the form payload declaring a winner in every pod."""
    data = {}
    for pod in round_obj.pods:
        if pod.is_bye:
            continue
        winner = pod.assignments.first()
        data[f'result_{pod.id}'] = str(winner.player_id)
    return data


def test_generate_button_announces(client, tournament, posts):
    r = client.post(f'/rounds/tournament/{tournament.id}/generate',
                    follow_redirects=True)
    assert r.status_code == 200
    assert len(posts) == 1, 'generate button should post pairings'
    assert 'Round 1' in posts[0][1]['content']


def test_manual_announce_button(client, tournament, posts):
    client.post(f'/rounds/tournament/{tournament.id}/generate', follow_redirects=True)
    round1 = tournament.get_current_round()
    posts.clear()

    r = client.post(f'/rounds/{round1.id}/announce', follow_redirects=True)
    assert b'posted to Discord' in r.data
    assert len(posts) == 1
    assert 'Round 1' in posts[0][1]['content']


def test_manual_announce_surfaces_failure(client, tournament, league, posts):
    client.post(f'/rounds/tournament/{tournament.id}/generate', follow_redirects=True)
    round1 = tournament.get_current_round()
    league.discord_channel_id = None
    db.session.commit()

    r = client.post(f'/rounds/{round1.id}/announce', follow_redirects=True)
    assert b'No Discord channel is linked' in r.data


def test_announce_requires_login(app, tournament):
    anon = app.test_client()
    r = anon.post(f'/rounds/1/announce')
    assert r.status_code in (302, 401), 'announce route must not be public'


def test_submit_and_next_announces(client, tournament, posts):
    client.post(f'/rounds/tournament/{tournament.id}/generate',
                follow_redirects=True)
    round1 = tournament.get_current_round()
    posts.clear()

    r = client.post(f'/results/{round1.id}/submit-and-next',
                    data=_fill_results(round1), follow_redirects=True)
    assert r.status_code == 200
    assert len(posts) == 1, 'submit-and-next should post round 2 pairings'
    assert 'Round 2' in posts[0][1]['content']
