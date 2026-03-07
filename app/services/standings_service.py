from app.models.tournament import Tournament
from app.models.player import Player
from app.models.round import Round
from app.services.scoring_service import calculate_player_total_points
from app.services.tiebreaker_service import calculate_all_tiebreakers


def _get_playoff_placement(tournament):
    """Return a dict of player_id -> playoff_tier (lower = better).
    Tier 0 = finals winner, 1 = other finalists, 2 = semi losers, 99 = didn't make cut."""
    if tournament.status not in ('playoffs', 'completed') or not tournament.playoff_cut:
        return {}

    placements = {}

    final_round = Round.query.filter_by(
        tournament_id=tournament.id, is_playoff=True, playoff_stage='final'
    ).first()

    semi_round = Round.query.filter_by(
        tournament_id=tournament.id, is_playoff=True, playoff_stage='semi'
    ).first()

    # Finalists
    if final_round:
        for pod in final_round.pods:
            for a in pod.assignments:
                if a.placement == 1:
                    placements[a.player_id] = 0  # champion
                else:
                    placements[a.player_id] = 1  # finalist

    # Semi losers (anyone in semis who isn't in finals)
    if semi_round:
        for pod in semi_round.pods:
            if pod.is_bye:
                continue
            for a in pod.assignments:
                if a.player_id not in placements:
                    placements[a.player_id] = 2  # semi loser

    return placements


def calculate_standings(tournament):
    players = Player.query.filter_by(tournament_id=tournament.id).all()
    playoff_tiers = _get_playoff_placement(tournament)
    standings = []

    for player in players:
        total_points = calculate_player_total_points(player)
        tiebreakers = calculate_all_tiebreakers(player)
        matches_played = player.get_matches_played()
        tier = playoff_tiers.get(player.id, 99)

        standings.append({
            'player': player,
            'points': total_points,
            'omw_percentage': tiebreakers['omw_percentage'],
            'gw_percentage': tiebreakers['gw_percentage'],
            'ogw_percentage': tiebreakers['ogw_percentage'],
            'matches_played': matches_played,
            'playoff_tier': tier,
        })

    # Sort: playoff tier first (lower = better), then swiss tiebreakers
    standings.sort(
        key=lambda x: (
            x['playoff_tier'],
            -x['points'],
            -x['omw_percentage'],
            -x['gw_percentage'],
            -x['ogw_percentage']
        ),
    )

    for rank, standing in enumerate(standings, 1):
        standing['rank'] = rank

    return standings


def get_player_standing(player, tournament):
    """
    Get standing information for a specific player.

    Args:
        player: Player object
        tournament: Tournament object

    Returns:
        Dict: Standing information for the player
    """
    standings = calculate_standings(tournament)

    for standing in standings:
        if standing['player'].id == player.id:
            return standing

    return None


def format_percentage(value):
    """
    Format a percentage value for display.

    Args:
        value: Float (0.0 to 1.0)

    Returns:
        String: Formatted percentage (e.g., "65.4%")
    """
    return f"{value * 100:.1f}%"
