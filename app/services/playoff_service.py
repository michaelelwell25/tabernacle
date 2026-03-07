from app import db
from app.models.tournament import Tournament
from app.models.round import Round
from app.models.pod import Pod
from app.models.pod_assignment import PodAssignment
from app.services.standings_service import calculate_standings

# cut_size -> (num_semi_pods, num_byes_to_final)
BRACKET_STRUCTURE = {
    4:  (0, 4),   # no semis, straight to finals
    10: (2, 2),   # 2 semi pods (seeds 3-10), seeds 1-2 bye to finals
    13: (3, 1),   # 3 semi pods (seeds 2-13), seed 1 bye to finals
    16: (4, 0),   # 4 semi pods (seeds 1-16), no byes
}


def start_playoffs(tournament_id, cut_size):
    tournament = Tournament.query.get(tournament_id)
    if not tournament:
        raise ValueError("Tournament not found")
    if cut_size not in BRACKET_STRUCTURE:
        raise ValueError(f"Invalid cut size: {cut_size}. Must be 4, 10, 13, or 16")

    standings = calculate_standings(tournament)
    active_standings = [s for s in standings if not s['player'].dropped]

    if len(active_standings) < cut_size:
        raise ValueError(f"Only {len(active_standings)} active players, need {cut_size} for top {cut_size} cut")

    top_players = [s['player'] for s in active_standings[:cut_size]]
    num_semi_pods, num_byes = BRACKET_STRUCTURE[cut_size]

    tournament.status = 'playoffs'
    tournament.playoff_cut = cut_size

    if num_semi_pods == 0:
        # Top 4: go straight to finals
        round_obj = _create_playoff_round(tournament, 'final', top_players, [])
    else:
        bye_players = top_players[:num_byes]
        semi_players = top_players[num_byes:]
        round_obj = _create_playoff_round(tournament, 'semi', semi_players, bye_players)

    db.session.commit()
    return round_obj


def advance_to_finals(tournament_id):
    tournament = Tournament.query.get(tournament_id)
    if not tournament or tournament.status != 'playoffs':
        raise ValueError("Tournament not in playoffs")

    semi_round = Round.query.filter_by(
        tournament_id=tournament_id, is_playoff=True, playoff_stage='semi'
    ).first()

    if not semi_round:
        raise ValueError("No semifinal round found")
    if not semi_round.is_complete():
        raise ValueError("Semifinal round is not complete")

    # Collect bye players (higher seeds) and semi winners separately
    bye_players = []
    winners = []
    for pod in semi_round.pods.order_by('pod_number'):
        if pod.is_bye:
            bye_players.append(pod.assignments.first().player)
        else:
            winner_assignment = pod.assignments.filter_by(placement=1).first()
            if not winner_assignment:
                raise ValueError(f"No winner found for pod {pod.pod_number}")
            winners.append(winner_assignment.player)

    # Finals = bye players (higher seeds) + semi winners
    finalists = bye_players + winners

    if len(finalists) != 4:
        raise ValueError(f"Expected 4 finalists, got {len(finalists)}")

    round_obj = _create_playoff_round(tournament, 'final', finalists, [])
    db.session.commit()
    return round_obj


def _create_playoff_round(tournament, stage, pod_players, bye_players):
    round_number = tournament.current_round + 1
    tournament.current_round = round_number

    round_obj = Round(
        tournament_id=tournament.id,
        round_number=round_number,
        status='pending',
        is_playoff=True,
        playoff_stage=stage
    )
    db.session.add(round_obj)
    db.session.flush()

    pod_number = 1

    if stage == 'final':
        # One pod of 4
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
            db.session.add(PodAssignment(
                pod_id=pod.id, player_id=player.id, seat_position=seat
            ))
    else:
        # Semi pods: groups of 4 from the non-bye players
        for i in range(0, len(pod_players), 4):
            group = pod_players[i:i+4]
            pod = Pod(
                round_id=round_obj.id,
                pod_number=pod_number,
                table_number=pod_number,
                status='pending',
                is_bye=False
            )
            db.session.add(pod)
            db.session.flush()
            for seat, player in enumerate(group, 1):
                db.session.add(PodAssignment(
                    pod_id=pod.id, player_id=player.id, seat_position=seat
                ))
            pod_number += 1

        # Bye pods for top seeds
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
            db.session.add(PodAssignment(
                pod_id=pod.id, player_id=player.id, seat_position=1,
                placement=1, points_earned=0
            ))
            pod_number += 1

    return round_obj
