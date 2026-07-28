"""Seat order must match between the site and the Discord bot.

Regression: Pod.assignments had no order_by, so templates iterated rows in
insertion order while discord_service sorted by seat_position. _assign_seats
picks seats via random.choice, so the two disagreed ~96% of the time --
players landed at the right table in the wrong order.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app import create_app, db
from app.models.league import League
from app.services.league_service import create_league, create_week_tournament, \
    get_or_create_league_player, add_player_to_week
from app.services.pairing_service import generate_swiss_pairings
from app.services.discord_service import build_pairings_payload


@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def round_obj(app):
    lg = create_league('Seat Order League', num_weeks=8)
    t = create_week_tournament(lg, 1)
    for i in range(12):
        add_player_to_week(get_or_create_league_player(lg.id, f'P{i+1}'), t)
    t.status = 'active'
    db.session.commit()
    r = generate_swiss_pairings(t.id, 1)
    db.session.commit()
    return r


def test_assignments_default_to_seat_order(round_obj):
    """Unordered iteration -- what every template does -- is already sorted."""
    for pod in round_obj.pods:
        seats = [a.seat_position for a in pod.assignments]
        assert seats == sorted(seats), f'pod {pod.pod_number} out of seat order: {seats}'


def test_site_and_bot_agree(round_obj):
    """The order a template renders must equal the order the bot posts."""
    payload = build_pairings_payload(round_obj.tournament, round_obj)
    bot_pods = [f['value'].split('\n') for f in payload['embeds'][0]['fields']]

    for pod, bot_names in zip(round_obj.pods.order_by('pod_number'), bot_pods):
        site = [a.player.name for a in pod.assignments]
        bot = [n.split('. ', 1)[1] for n in bot_names]
        assert site == bot, f'pod {pod.pod_number}: site {site} != bot {bot}'
