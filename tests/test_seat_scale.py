"""Scale test: seat diversity + repeat pairings at 100 and 200 players.
Uses the built-in SEAT_WEIGHT in pairing_service (augmenting-path matching).
"""
import random
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Tournament, Player, Round, Pod, PodAssignment, PairingHistory
from app.models.seat_history import SeatHistory
from app.services.pairing_service import generate_swiss_pairings
from datetime import date


def run_tournament(app, n_players, n_rounds):
    with app.app_context():
        db.create_all()
        t = Tournament(
            name=f'Scale {n_players}p',
            date=date.today(),
            status='active',
            current_round=0,
            scoring_system='3-1-0-0',
            bye_points=1,
            allow_byes=(n_players % 4 != 0),
            seat_scoring=False,
        )
        db.session.add(t)
        db.session.flush()
        for i in range(n_players):
            db.session.add(Player(tournament_id=t.id, name=f'P{i+1:03d}', dropped=False))
        db.session.commit()
        tid = t.id

    round_times = []
    for rd in range(1, n_rounds + 1):
        with app.app_context():
            t0 = time.perf_counter()
            round_obj = generate_swiss_pairings(tid, rd)
            elapsed = time.perf_counter() - t0
            round_times.append(elapsed)

            pods = Pod.query.filter_by(round_id=round_obj.id, is_bye=False).all()
            bye_count = Pod.query.filter_by(round_id=round_obj.id, is_bye=True).count()
            sizes = {}
            for p in pods:
                s = len(list(p.assignments))
                sizes[s] = sizes.get(s, 0) + 1
            print(f"  Round {rd}: {elapsed:.3f}s | {len(pods)} pods {dict(sizes)} | {bye_count} byes")

        # Random results
        with app.app_context():
            t = Tournament.query.get(tid)
            scoring = t.get_scoring_points()
            r = Round.query.filter_by(tournament_id=tid, round_number=rd).first()
            for pod in r.pods:
                if pod.is_bye:
                    continue
                assignments = list(pod.assignments)
                random.shuffle(assignments)
                for place, a in enumerate(assignments, 1):
                    a.placement = place
                    a.points_earned = scoring.get(place, 0)
                pod.status = 'completed'
            r.status = 'completed'
            db.session.commit()

    # Metrics
    with app.app_context():
        records = PairingHistory.query.filter_by(tournament_id=tid).all()
        pair_counts = {}
        for r in records:
            key = (min(r.player1_id, r.player2_id), max(r.player1_id, r.player2_id))
            pair_counts[key] = pair_counts.get(key, 0) + 1
        total_repeats = sum(v - 1 for v in pair_counts.values() if v > 1)

        players = Player.query.filter_by(tournament_id=tid, dropped=False).all()
        seat_violations = 0
        perfect_cycles = 0
        for p in players:
            hist = SeatHistory.get_seat_history(p.id, tid)
            if not hist:
                continue
            used = set()
            for s in hist:
                if len(used) == 4:
                    used = set()
                if s in used:
                    seat_violations += 1
                used.add(s)
            if len(hist) >= 4 and len(set(hist[:4])) == 4:
                perfect_cycles += 1

        # Sample histories
        sample = random.sample(players, min(8, len(players)))

    return {
        'round_times': round_times,
        'total_time': sum(round_times),
        'repeats': total_repeats,
        'seat_violations': seat_violations,
        'perfect_cycles': perfect_cycles,
        'n_players': n_players,
    }


if __name__ == '__main__':
    random.seed(42)

    for n in [100, 200]:
        print(f"\n{'='*60}")
        print(f"  {n} PLAYERS, 6 ROUNDS (SEAT_WEIGHT=100, augmenting-path)")
        print(f"{'='*60}")

        app = create_app('testing')
        r = run_tournament(app, n, 6)

        print(f"\n  Total time:       {r['total_time']:.2f}s")
        print(f"  Avg per round:    {r['total_time']/6:.2f}s")
        print(f"  Repeat pairings:  {r['repeats']}")
        print(f"  Seat violations:  {r['seat_violations']}")
        print(f"  Perfect cycles:   {r['perfect_cycles']}/{n}")
