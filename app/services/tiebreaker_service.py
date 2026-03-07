from app.models.player import Player
from app.models.bye_history import ByeHistory
from app.services.scoring_service import calculate_player_match_win_percentage

BYE_PHANTOM_MWP = 0.2
OPPONENT_MWP_FLOOR = 0.2


def calculate_opponent_match_win_percentage(player):
    """
    OMW% = Average match win percentage of all opponents faced.
    Each opponent's MWP has a floor of 0.2.
    Bye rounds add 3 phantom opponents at 0.2 MWP each.
    """
    opponents = player.get_opponents()

    omw_values = []
    for opponent in opponents:
        opponent_mw = calculate_player_match_win_percentage(opponent)
        opponent_mw = max(opponent_mw, OPPONENT_MWP_FLOOR)
        omw_values.append(opponent_mw)

    # Add phantom opponents for each bye received
    bye_count = ByeHistory.get_bye_count(player.id, player.tournament_id)
    for _ in range(bye_count * 3):
        omw_values.append(BYE_PHANTOM_MWP)

    if not omw_values:
        return 0.0

    return sum(omw_values) / len(omw_values)


def calculate_game_win_percentage(player):
    """GW% — same as MWP in EDH (one game per match)."""
    return calculate_player_match_win_percentage(player)


def calculate_opponent_game_win_percentage(player):
    """
    OGW% = Average GW% of all opponents faced.
    Bye rounds add 3 phantom opponents at 0.2 each.
    """
    opponents = player.get_opponents()

    ogw_values = []
    for opponent in opponents:
        opponent_gw = calculate_game_win_percentage(opponent)
        ogw_values.append(opponent_gw)

    bye_count = ByeHistory.get_bye_count(player.id, player.tournament_id)
    for _ in range(bye_count * 3):
        ogw_values.append(BYE_PHANTOM_MWP)

    if not ogw_values:
        return 0.0

    return sum(ogw_values) / len(ogw_values)


def calculate_all_tiebreakers(player):
    return {
        'omw_percentage': calculate_opponent_match_win_percentage(player),
        'gw_percentage': calculate_game_win_percentage(player),
        'ogw_percentage': calculate_opponent_game_win_percentage(player),
    }
