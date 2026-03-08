import itertools
import sys
from app import db
from app.models.tournament import Tournament
from app.models.player import Player
from app.models.round import Round
from app.models.pod import Pod
from app.models.pod_assignment import PodAssignment
from app.models.pairing_history import PairingHistory
from app.models.bye_history import ByeHistory
from app.services.standings_service import calculate_standings

try:
    import pulp
    HAS_PULP = True
except ImportError:
    HAS_PULP = False


def _log(msg):
    print(f"[PAIRING] {msg}", file=sys.stderr, flush=True)


def _count_repeats(pod_assignments, history):
    repeats = 0
    for pod in pod_assignments:
        ids = [p.id for p in pod]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                key = (min(ids[i], ids[j]), max(ids[i], ids[j]))
                repeats += history.get(key, 0)
    return repeats

MAX_BRACKET_SPREAD = 3
CANDIDATE_CAP = 50000
ILP_PLAYER_CAP = 56  # Above this, use greedy (ILP too slow on shared CPU)


def generate_swiss_pairings(tournament_id, round_number):
    tournament = Tournament.query.get(tournament_id)
    if not tournament:
        raise ValueError(f"Tournament {tournament_id} not found")

    players = tournament.get_active_players()
    if len(players) < 3:
        raise ValueError("Need at least 3 players to generate pairings")

    standings = calculate_standings(tournament)
    active_standings = [s for s in standings if not s['player'].dropped]
    sorted_players = [s['player'] for s in active_standings]
    rank_map = {s['player'].id: s['rank'] for s in active_standings}
    points_map = {s['player'].id: s['points'] for s in active_standings}

    # Assign byes or prepare for 3-player pods
    if tournament.allow_byes:
        bye_players, pool = assign_byes(sorted_players, tournament, round_number, points_map)
    else:
        bye_players = []
        pool = list(sorted_players)

    # Build pairing history for O(1) lookups
    history = build_pairing_history_map(tournament_id)
    _log(f"Round {round_number}: {len(pool)} players in pool, {len(history)} pair-history entries, HAS_PULP={HAS_PULP}")

    # Generate candidate pods and solve
    method = 'none'
    if len(pool) == 0:
        pod_assignments = []
    elif len(pool) < 4:
        pod_assignments = [pool]
    else:
        if not tournament.allow_byes and len(pool) % 4 != 0:
            pod_assignments = _solve_with_short_pods(pool, tournament, points_map, rank_map, history)
            method = 'short-pods'
        else:
            if HAS_PULP and len(pool) <= ILP_PLAYER_CAP:
                candidates = generate_candidate_pods(pool, points_map, rank_map, history)
                _log(f"  Generated {len(candidates)} candidates (cap={CANDIDATE_CAP})")
                if len(candidates) <= CANDIDATE_CAP:
                    pod_assignments = solve_ilp(candidates, pool, points_map, rank_map, history)
                    if pod_assignments is None:
                        _log("  ILP returned None, falling back to greedy")
                        pod_assignments = greedy_fallback(pool, points_map, rank_map, history)
                        method = 'greedy (ILP failed)'
                    else:
                        method = 'ILP'
                else:
                    pod_assignments = greedy_fallback(pool, points_map, rank_map, history)
                    method = 'greedy (too many candidates)'
            else:
                pod_assignments = greedy_fallback(pool, points_map, rank_map, history)
                method = 'greedy (no PuLP or too many players)'

    repeats = _count_repeats(pod_assignments, history)
    _log(f"  Method: {method}, pods: {len(pod_assignments)}, repeat pairings: {repeats}")

    return create_round_and_pods(
        tournament, round_number, pod_assignments, bye_players, points_map, rank_map, history
    )


def _get_short_pod_players(tournament_id):
    """Return set of player IDs who have already been in a 3-player pod this tournament."""
    short_pod_players = set()
    rounds = Round.query.filter_by(tournament_id=tournament_id, is_playoff=False).all()
    for r in rounds:
        for pod in r.pods:
            if not pod.is_bye and pod.get_player_count() == 3:
                for a in pod.assignments:
                    short_pod_players.add(a.player_id)
    return short_pod_players


def _solve_with_short_pods(pool, tournament, points_map, rank_map, history):
    """Handle odd player counts with unified ILP over both 3-player and 4-player pods."""
    remainder = len(pool) % 4
    num_3pods = {3: 1, 2: 2, 1: 3, 0: 0}[remainder]
    had_short = _get_short_pod_players(tournament.id)

    sorted_pool = sorted(pool, key=lambda p: rank_map[p.id])
    NEIGHBOR_WINDOW = max(11, len(sorted_pool))  # for small pools, consider everyone

    # Generate 4-player candidates
    cand_4_ids = generate_candidate_pods(pool, points_map, rank_map, history)

    # Generate 3-player candidates
    cand_3_set = set()
    for i, player in enumerate(sorted_pool):
        start = max(0, i - 2)
        end = min(len(sorted_pool), start + NEIGHBOR_WINDOW)
        window = sorted_pool[start:end]
        if len(window) < 3:
            continue
        for combo in itertools.combinations(window, 3):
            if player in combo:
                ids = tuple(sorted(p.id for p in combo))
                cand_3_set.add(ids)

    # Score all candidates
    all_candidates = []
    for cand_ids in cand_4_ids:
        cost = score_candidate_pod(cand_ids, points_map, rank_map, history)
        all_candidates.append((cand_ids, cost, 4))
    for cand_ids in cand_3_set:
        cost = score_candidate_pod(cand_ids, points_map, rank_map, history)
        # Small penalty for players who've already been in short pods
        cost += sum(50 for pid in cand_ids if pid in had_short)
        all_candidates.append((cand_ids, cost, 3))

    n4 = sum(1 for c in all_candidates if c[2] == 4)
    n3 = sum(1 for c in all_candidates if c[2] == 3)
    _log(f"  Unified ILP: {len(all_candidates)} candidates ({n4} 4-player, {n3} 3-player), need {num_3pods} short pod(s)")

    # Try unified ILP
    if HAS_PULP and len(all_candidates) <= CANDIDATE_CAP:
        result = _solve_unified_ilp(all_candidates, pool, num_3pods)
        if result is not None:
            _log(f"  Unified ILP solved successfully")
            return result
        _log(f"  Unified ILP failed, trying combo fallback")

    # Fallback: try multiple short pod compositions with greedy
    return _short_pod_combo_fallback(pool, points_map, rank_map, history, had_short, num_3pods)


def _solve_unified_ilp(all_candidates, pool, num_3pods):
    """ILP with mixed 3-player and 4-player candidates."""
    player_ids = {p.id for p in pool}

    prob = pulp.LpProblem("SwissPairing", pulp.LpMinimize)

    x = {}
    for idx in range(len(all_candidates)):
        x[idx] = pulp.LpVariable(f"x_{idx}", cat='Binary')

    # Objective: minimize total cost
    prob += pulp.lpSum(all_candidates[idx][1] * x[idx] for idx in range(len(all_candidates)))

    # Each player in exactly one pod
    for pid in player_ids:
        prob += pulp.lpSum(
            x[idx] for idx in range(len(all_candidates)) if pid in all_candidates[idx][0]
        ) == 1

    # Exactly num_3pods 3-player pods selected
    prob += pulp.lpSum(
        x[idx] for idx in range(len(all_candidates)) if all_candidates[idx][2] == 3
    ) == num_3pods

    solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=10)
    status = prob.solve(solver)

    if pulp.LpStatus[status] != 'Optimal':
        return None

    result = []
    player_lookup = {p.id: p for p in pool}
    for idx in range(len(all_candidates)):
        if pulp.value(x[idx]) > 0.5:
            result.append([player_lookup[pid] for pid in all_candidates[idx][0]])

    return result


def _short_pod_combo_fallback(pool, points_map, rank_map, history, had_short, num_3pods):
    """Try multiple short pod compositions, pick the best total."""
    # Consider bottom half of standings as short pod candidates
    bottom_n = min(len(pool), max(6, len(pool) // 2))
    bottom_players = list(reversed(pool))[:bottom_n]

    best_assignment = None
    best_cost = float('inf')

    for short_combo in itertools.combinations(bottom_players, 3 * num_3pods):
        short_set = set(p.id for p in short_combo)
        main = [p for p in pool if p.id not in short_set]
        if len(main) % 4 != 0:
            continue

        short_pods = [list(short_combo[i:i + 3]) for i in range(0, len(short_combo), 3)]
        main_pods = greedy_fallback(main, points_map, rank_map, history) if main else []

        all_pods = main_pods + short_pods
        total = sum(
            score_candidate_pod(tuple(sorted(p.id for p in pod)), points_map, rank_map, history)
            for pod in all_pods
        )
        total += sum(50 for pid in short_set if pid in had_short)

        if total < best_cost:
            best_cost = total
            best_assignment = all_pods

    _log(f"  Combo fallback: tried {bottom_n}C{3*num_3pods} combos, best cost={best_cost:.1f}")
    return best_assignment if best_assignment else greedy_fallback(pool, points_map, rank_map, history)


def assign_byes(sorted_players, tournament, round_number, points_map):
    total = len(sorted_players)
    remainder = total % 4

    # Special case: fewer than 4 players total, no byes needed
    if total < 4:
        return [], list(sorted_players)

    if remainder == 0:
        return [], list(sorted_players)

    num_byes = remainder  # 1, 2, or 3 byes to make divisible by 4

    # Sort candidates: fewest byes first, then lowest points first
    candidates = sorted(
        sorted_players,
        key=lambda p: (
            ByeHistory.get_bye_count(p.id, tournament.id),
            points_map[p.id],
        )
    )

    bye_players = candidates[:num_byes]
    pool = [p for p in sorted_players if p not in bye_players]

    # Record byes
    for player in bye_players:
        ByeHistory.record_bye(player.id, tournament.id, round_number)

    return bye_players, pool


def build_pairing_history_map(tournament_id):
    records = PairingHistory.query.filter_by(tournament_id=tournament_id).all()
    history = {}
    for r in records:
        key = (min(r.player1_id, r.player2_id), max(r.player1_id, r.player2_id))
        history[key] = history.get(key, 0) + 1
    _log(f"  History: {len(records)} records -> {len(history)} unique pairs")
    return history


def generate_candidate_pods(pool, points_map, rank_map, history, max_spread=MAX_BRACKET_SPREAD):
    unique_points = sorted(set(points_map[p.id] for p in pool), reverse=True)

    if len(unique_points) == 0:
        return []

    # Sort pool by rank for neighbor-based generation
    sorted_pool = sorted(pool, key=lambda p: rank_map[p.id])
    candidates = set()

    # Strategy 1: Neighbor windows (always fast — O(n * C(w,3)))
    # For each player, consider combos with their nearest 11 neighbors by rank
    NEIGHBOR_WINDOW = 11
    for i, player in enumerate(sorted_pool):
        start = max(0, i - 2)
        end = min(len(sorted_pool), start + NEIGHBOR_WINDOW)
        if end - start < 4:
            continue
        window = sorted_pool[start:end]
        for combo in itertools.combinations(window, 4):
            if player in combo:
                ids = tuple(sorted(p.id for p in combo))
                candidates.add(ids)
                if len(candidates) > CANDIDATE_CAP:
                    return list(candidates)

    # Strategy 2: Point bracket windows (only for small brackets)
    MAX_BRACKET_PLAYERS = 16
    for i in range(len(unique_points)):
        window_end = min(i + max_spread, len(unique_points))
        window_points = set(unique_points[i:window_end])
        window_players = [p for p in pool if points_map[p.id] in window_points]

        if len(window_players) < 4 or len(window_players) > MAX_BRACKET_PLAYERS:
            continue

        for combo in itertools.combinations(window_players, 4):
            ids = tuple(sorted(p.id for p in combo))
            candidates.add(ids)
            if len(candidates) > CANDIDATE_CAP:
                return list(candidates)

    # Ensure every player is covered
    covered = set()
    for c in candidates:
        covered.update(c)

    for pid in ({p.id for p in pool} - covered):
        neighbors = sorted(pool, key=lambda p: abs(rank_map[p.id] - rank_map.get(pid, 0)))[:NEIGHBOR_WINDOW]
        if len(neighbors) >= 4:
            for combo in itertools.combinations(neighbors, 4):
                if pid in [p.id for p in combo]:
                    ids = tuple(sorted(p.id for p in combo))
                    candidates.add(ids)
                    if len(candidates) > CANDIDATE_CAP:
                        return list(candidates)

    return list(candidates)


def score_candidate_pod(player_ids, points_map, rank_map, history):
    cost = 0.0
    n = len(player_ids)

    # Repeat cost: 10000 per pair that has played together (dominant — must avoid repeats)
    for i in range(n):
        for j in range(i + 1, n):
            key = (min(player_ids[i], player_ids[j]), max(player_ids[i], player_ids[j]))
            if key in history:
                cost += 10000 * history[key]

    # Point spread cost
    pts = [points_map[pid] for pid in player_ids]
    cost += 10 * (max(pts) - min(pts))

    # Standing gap cost
    ranks = [rank_map[pid] for pid in player_ids]
    cost += 0.1 * (max(ranks) - min(ranks))

    return cost


def solve_ilp(candidates, pool, points_map, rank_map, history):
    player_ids = {p.id for p in pool}

    scored = []
    for cand in candidates:
        cost = score_candidate_pod(cand, points_map, rank_map, history)
        scored.append((cand, cost))

    prob = pulp.LpProblem("SwissPairing", pulp.LpMinimize)

    x = {}
    for idx in range(len(scored)):
        x[idx] = pulp.LpVariable(f"x_{idx}", cat='Binary')

    # Objective: minimize total cost
    prob += pulp.lpSum(scored[idx][1] * x[idx] for idx in range(len(scored)))

    # Constraint: each player in exactly one selected pod
    for pid in player_ids:
        prob += pulp.lpSum(
            x[idx] for idx in range(len(scored)) if pid in scored[idx][0]
        ) == 1

    solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=10)
    status = prob.solve(solver)

    if pulp.LpStatus[status] != 'Optimal':
        return None

    result = []
    player_lookup = {p.id: p for p in pool}
    for idx in range(len(scored)):
        if pulp.value(x[idx]) > 0.5:
            result.append([player_lookup[pid] for pid in scored[idx][0]])

    return result


def greedy_fallback(pool, points_map, rank_map, history):
    # For small pools, try multiple starting orders to avoid greedy traps
    if len(pool) <= 32:
        return _multi_start_greedy(pool, points_map, rank_map, history)
    return _single_greedy(pool, points_map, rank_map, history)


def _single_greedy(pool, points_map, rank_map, history):
    remaining = list(pool)
    pods = []

    while len(remaining) >= 4:
        anchor = remaining[0]
        # Get next 15 candidates (or all remaining)
        candidates = remaining[1:min(16, len(remaining))]

        best_pod = None
        best_cost = float('inf')

        if len(candidates) >= 3:
            for combo in itertools.combinations(candidates, 3):
                pod_ids = tuple(sorted([anchor.id] + [p.id for p in combo]))
                cost = score_candidate_pod(pod_ids, points_map, rank_map, history)
                if cost < best_cost:
                    best_cost = cost
                    best_pod = [anchor] + list(combo)
        else:
            best_pod = [anchor] + candidates
            while len(best_pod) < 4 and len(remaining) > len(best_pod):
                for p in remaining:
                    if p not in best_pod:
                        best_pod.append(p)
                        break

        if best_pod and len(best_pod) == 4:
            pods.append(best_pod)
            for p in best_pod:
                remaining.remove(p)
        else:
            break

    return pods


def _multi_start_greedy(pool, points_map, rank_map, history):
    """Try each player as first anchor, pick the assignment with lowest total cost."""
    best_pods = None
    best_total = float('inf')

    for start in range(len(pool)):
        # Reorder: put start player first, rest in original order
        reordered = [pool[start]] + [p for i, p in enumerate(pool) if i != start]
        pods = _single_greedy(reordered, points_map, rank_map, history)

        # Score the entire assignment
        total = 0.0
        for pod in pods:
            pod_ids = tuple(sorted(p.id for p in pod))
            total += score_candidate_pod(pod_ids, points_map, rank_map, history)

        if total < best_total:
            best_total = total
            best_pods = pods

    _log(f"  Multi-start greedy: tried {len(pool)} starts, best cost={best_total:.1f}")
    return best_pods


def create_round_and_pods(tournament, round_number, pod_assignments, bye_players, points_map, rank_map, history):
    round_obj = Round(
        tournament_id=tournament.id,
        round_number=round_number,
        status='pending'
    )
    db.session.add(round_obj)
    db.session.flush()

    pod_number = 1

    # Create regular pods
    for pod_players in pod_assignments:
        pod = Pod(
            round_id=round_obj.id,
            pod_number=pod_number,
            table_number=pod_number,
            status='pending',
            is_bye=False
        )
        db.session.add(pod)
        db.session.flush()

        for seat, player in enumerate(pod_players, 1):
            assignment = PodAssignment(
                pod_id=pod.id,
                player_id=player.id,
                seat_position=seat
            )
            db.session.add(assignment)

        PairingHistory.record_pod_pairings(pod_players, tournament.id, round_number)
        pod_number += 1

    # Create bye pods
    for player in bye_players:
        pod = Pod(
            round_id=round_obj.id,
            pod_number=pod_number,
            table_number=pod_number,
            status='completed',
            is_bye=True
        )
        db.session.add(pod)
        db.session.flush()

        assignment = PodAssignment(
            pod_id=pod.id,
            player_id=player.id,
            seat_position=1,
            placement=1,
            points_earned=tournament.bye_points
        )
        db.session.add(assignment)
        pod_number += 1

    db.session.commit()
    return round_obj
