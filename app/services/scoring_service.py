from app.models.tournament import Tournament
from app.models.player import Player
from app.models.pod_assignment import PodAssignment


def get_points_for_placement(tournament, placement):
    scoring = tournament.get_scoring_points()
    return scoring.get(placement, 0)


def calculate_player_total_points(player):
    return player.get_total_points()


def calculate_constructed_mwp(player):
    """MTR Appendix C: match points / (3 x rounds played). Byes count as wins."""
    points = 0.0
    rounds = 0
    for assignment in player.pod_assignments:
        if assignment.points_earned is None:
            continue
        points += assignment.points_earned
        rounds += 1
    if rounds == 0:
        return 0.0
    return min(points / (3 * rounds), 1.0)


def calculate_constructed_gwp(player):
    """MTR Appendix C: game points / (3 x games played). Bye = 2-0."""
    game_points = 0
    games = 0
    for assignment in player.pod_assignments:
        if assignment.points_earned is None:
            continue
        gw = assignment.game_wins or 0
        gl = assignment.game_losses or 0
        gd = assignment.game_draws or 0
        game_points += 3 * gw + gd
        games += gw + gl + gd
    if games == 0:
        return 0.0
    return min(game_points / (3 * games), 1.0)


def calculate_player_match_win_percentage(player):
    """
    Match Win % = Non-bye points / max possible points.
    With seat scoring, max per match is the seat-specific win value.
    Without seat scoring, max per match is the flat win value.
    Bye rounds are excluded.
    """
    tournament = player.tournament
    if tournament.is_constructed():
        return calculate_constructed_mwp(player)
    use_seats = tournament.seat_scoring
    flat_win = tournament.get_scoring_points()[1]

    if use_seats:
        seat_wins = tournament.get_seat_win_points()

    non_bye_points = 0.0
    max_points = 0.0

    for assignment in player.pod_assignments:
        if assignment.points_earned is None:
            continue
        if assignment.pod.is_bye:
            continue
        non_bye_points += assignment.points_earned
        if use_seats:
            max_points += seat_wins.get(assignment.seat_position, flat_win)
        else:
            max_points += flat_win

    if max_points == 0:
        return 0.0

    return min(non_bye_points / max_points, 1.0)


def assign_points_to_pod(pod, tournament):
    from app import db
    scoring = tournament.get_scoring_points()
    for assignment in pod.assignments:
        if assignment.placement is not None:
            assignment.points_earned = scoring.get(assignment.placement, 0)
    db.session.commit()
    return True


def recalculate_pod_points(pod, tournament):
    return assign_points_to_pod(pod, tournament)
