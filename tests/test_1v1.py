"""Tests for constructed (1v1) tournament support: pairing, results, tiebreakers, playoffs."""
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app import create_app, db
from app.models import Tournament, Player, Round, Pod, PodAssignment, PairingHistory
from app.services.pairing_service import generate_swiss_pairings
from app.services.standings_service import calculate_standings
from app.services.playoff_service import start_playoffs, advance_constructed_playoffs
from app.services.scoring_service import calculate_constructed_mwp, calculate_constructed_gwp
from app.routes.results import _save_results


@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def make_tournament(n_players):
    t = Tournament(
        name='1v1 Test', date=date.today(), status='active',
        format='constructed', scoring_system='3-1-0',
        bye_points=3, draw_points=1, current_round=0,
    )
    db.session.add(t)
    db.session.flush()
    for i in range(n_players):
        db.session.add(Player(tournament_id=t.id, name=f'P{i+1:02d}'))
    db.session.commit()
    return t


def report(pod, winner_id, score=(2, 0)):
    """Set a match result directly (mirrors _save_constructed_results)."""
    for a in pod.assignments:
        if a.player_id == winner_id:
            a.placement, a.points_earned = 1, 3
            a.game_wins, a.game_losses, a.game_draws = score[0], score[1], 0
        else:
            a.placement, a.points_earned = 2, 0
            a.game_wins, a.game_losses, a.game_draws = score[1], score[0], 0
    pod.status = 'completed'
    db.session.commit()


def play_round(tournament, round_number):
    """Generate a round and have the lower player id win each match 2-0."""
    round_obj = generate_swiss_pairings(tournament.id, round_number)
    tournament.current_round = round_number
    db.session.commit()
    for pod in round_obj.pods:
        if pod.is_bye:
            continue
        winner_id = min(a.player_id for a in pod.assignments)
        report(pod, winner_id)
    return round_obj


def test_even_pairing(app):
    t = make_tournament(8)
    round_obj = generate_swiss_pairings(t.id, 1)
    pods = round_obj.pods.all()
    assert len(pods) == 4
    assert all(not p.is_bye for p in pods)
    assert all(p.get_player_count() == 2 for p in pods)


def test_odd_pairing_gets_one_bye(app):
    t = make_tournament(7)
    round_obj = generate_swiss_pairings(t.id, 1)
    byes = [p for p in round_obj.pods if p.is_bye]
    matches = [p for p in round_obj.pods if not p.is_bye]
    assert len(byes) == 1
    assert len(matches) == 3
    bye_assignment = byes[0].assignments.first()
    assert bye_assignment.points_earned == 3
    assert bye_assignment.game_wins == 2
    assert bye_assignment.game_losses == 0


def test_no_repeat_pairings(app):
    t = make_tournament(8)
    for rd in range(1, 4):
        play_round(t, rd)
    records = PairingHistory.query.filter_by(tournament_id=t.id).all()
    pairs = [(min(r.player1_id, r.player2_id), max(r.player1_id, r.player2_id)) for r in records]
    assert len(records) == 12  # 4 matches x 3 rounds
    assert len(set(pairs)) == 12  # all distinct


def test_results_submission(app):
    t = make_tournament(4)
    round_obj = generate_swiss_pairings(t.id, 1)
    pods = round_obj.pods.order_by('pod_number').all()

    m1 = pods[0].assignments.order_by('seat_position').all()
    m2 = pods[1].assignments.order_by('seat_position').all()
    form = {
        f'result_{pods[0].id}': f'{m1[0].player_id}:2-1',
        f'result_{pods[1].id}': 'draw:1-1',
    }
    with app.test_request_context(method='POST', data=form):
        _save_results(round_obj)

    winner, loser = m1[0], m1[1]
    assert (winner.placement, winner.points_earned, winner.game_wins, winner.game_losses) == (1, 3, 2, 1)
    assert (loser.placement, loser.points_earned, loser.game_wins, loser.game_losses) == (2, 0, 1, 2)
    assert all(a.points_earned == 1 and a.placement is None and a.game_wins == 1 for a in m2)
    assert round_obj.is_complete()


def test_constructed_percentages(app):
    t = make_tournament(4)
    for rd in (1, 2):
        play_round(t, rd)

    players = {p.name: p for p in t.players}
    p1 = players['P01']  # lowest id: wins everything 2-0
    assert calculate_constructed_mwp(p1) == 1.0
    assert calculate_constructed_gwp(p1) == 1.0

    standings = calculate_standings(t)
    assert standings[0]['player'].id == p1.id
    # Opponents' percentages respect the MTR 0.33 floor
    assert standings[0]['omw_percentage'] >= 0.33


def test_playoff_top4_single_elim(app):
    t = make_tournament(8)
    for rd in (1, 2, 3):
        play_round(t, rd)

    seeds = [s['player'] for s in calculate_standings(t)][:4]
    semi_round = start_playoffs(t.id, 4)
    assert t.status == 'playoffs'
    assert semi_round.playoff_stage == 'semi'

    semis = semi_round.pods.order_by('pod_number').all()
    assert len(semis) == 2
    m1_ids = {a.player_id for a in semis[0].assignments}
    m2_ids = {a.player_id for a in semis[1].assignments}
    assert m1_ids == {seeds[0].id, seeds[3].id}  # 1v4
    assert m2_ids == {seeds[1].id, seeds[2].id}  # 2v3

    report(semis[0], seeds[0].id)
    report(semis[1], seeds[1].id)

    final_round = advance_constructed_playoffs(t.id)
    assert final_round.playoff_stage == 'final'
    final = final_round.pods.first()
    assert {a.player_id for a in final.assignments} == {seeds[0].id, seeds[1].id}

    report(final, seeds[1].id, score=(2, 1))
    standings = calculate_standings(t)
    assert standings[0]['player'].id == seeds[1].id  # champion on top
    assert standings[1]['player'].id == seeds[0].id  # runner-up second


def test_playoff_top8_bracket(app):
    t = make_tournament(8)
    for rd in (1, 2, 3):
        play_round(t, rd)

    seeds = [s['player'] for s in calculate_standings(t)][:8]
    qf_round = start_playoffs(t.id, 8)
    assert qf_round.playoff_stage == 'quarter'
    qfs = qf_round.pods.order_by('pod_number').all()
    assert len(qfs) == 4
    expected = [(0, 7), (3, 4), (1, 6), (2, 5)]  # 1v8, 4v5, 2v7, 3v6
    for pod, (a_idx, b_idx) in zip(qfs, expected):
        assert {x.player_id for x in pod.assignments} == {seeds[a_idx].id, seeds[b_idx].id}

    for pod in qfs:
        winner_id = min(a.player_id for a in pod.assignments)
        report(pod, winner_id)

    semi_round = advance_constructed_playoffs(t.id)
    assert semi_round.playoff_stage == 'semi'
    assert semi_round.pods.count() == 2
