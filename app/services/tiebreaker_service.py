from app.models.player import Player
from app.models.bye_history import ByeHistory
from app.services.scoring_service import (
    calculate_player_match_win_percentage,
    calculate_constructed_mwp,
    calculate_constructed_gwp,
)

BYE_PHANTOM_MWP = 0.2
OPPONENT_MWP_FLOOR = 0.2
CONSTRUCTED_FLOOR = 0.33  # MTR Appendix C minimum for opponents' percentages


def calculate_opponent_match_win_percentage(player):
    """
    OMW% = Average match win percentage of all opponents faced.
    Commander: opponent MWP floor 0.2, byes add 3 phantom opponents at 0.2.
    Constructed (MTR): opponent MWP floor 0.33, byes ignored (not opponents).
    """
    constructed = player.tournament.is_constructed()
    opponents = player.get_opponents()

    omw_values = []
    for opponent in opponents:
        if constructed:
            omw_values.append(max(calculate_constructed_mwp(opponent), CONSTRUCTED_FLOOR))
        else:
            opponent_mw = calculate_player_match_win_percentage(opponent)
            omw_values.append(max(opponent_mw, OPPONENT_MWP_FLOOR))

    # Add phantom opponents for each bye received (commander only)
    if not constructed:
        bye_count = ByeHistory.get_bye_count(player.id, player.tournament_id)
        for _ in range(bye_count * 3):
            omw_values.append(BYE_PHANTOM_MWP)

    if not omw_values:
        return 0.0

    return sum(omw_values) / len(omw_values)


def calculate_game_win_percentage(player):
    """GW% — real game stats for constructed; same as MWP in EDH (one game per match)."""
    if player.tournament.is_constructed():
        return calculate_constructed_gwp(player)
    return calculate_player_match_win_percentage(player)


def calculate_opponent_game_win_percentage(player):
    """
    OGW% = Average GW% of all opponents faced.
    Commander: byes add 3 phantom opponents at 0.2.
    Constructed (MTR): opponent GWP floor 0.33, byes ignored.
    """
    constructed = player.tournament.is_constructed()
    opponents = player.get_opponents()

    ogw_values = []
    for opponent in opponents:
        if constructed:
            ogw_values.append(max(calculate_constructed_gwp(opponent), CONSTRUCTED_FLOOR))
        else:
            ogw_values.append(calculate_game_win_percentage(opponent))

    if not constructed:
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
