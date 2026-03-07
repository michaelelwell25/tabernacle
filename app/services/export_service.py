import pandas as pd
from io import StringIO
from app.services.standings_service import calculate_standings, format_percentage


def export_standings_csv(tournament):
    """
    Export tournament standings to CSV format.

    Args:
        tournament: Tournament object

    Returns:
        String: CSV content
    """
    standings = calculate_standings(tournament)

    # Prepare data for DataFrame
    data = []
    for standing in standings:
        data.append({
            'Rank': standing['rank'],
            'Player': standing['player'].name,
            'Points': standing['points'],
            'Matches': standing['matches_played'],
            'OMW%': format_percentage(standing['omw_percentage']),
            'GW%': format_percentage(standing['gw_percentage']),
            'OGW%': format_percentage(standing['ogw_percentage']),
        })

    df = pd.DataFrame(data)
    return df.to_csv(index=False)


def export_pairings_text(round_obj):
    """
    Export round pairings to text format (printable).

    Args:
        round_obj: Round object

    Returns:
        String: Text content with pairings
    """
    output = StringIO()

    output.write(f"Round {round_obj.round_number} Pairings\n")
    output.write("=" * 50 + "\n\n")

    for pod in round_obj.pods.order_by('pod_number'):
        output.write(f"Pod {pod.pod_number} (Table {pod.table_number or pod.pod_number})\n")
        output.write("-" * 30 + "\n")

        for assignment in pod.assignments.order_by('seat_position'):
            output.write(f"  Seat {assignment.seat_position}: {assignment.player.name}\n")

        output.write("\n")

    return output.getvalue()


def export_pairings_csv(round_obj):
    """
    Export round pairings to CSV format.

    Args:
        round_obj: Round object

    Returns:
        String: CSV content
    """
    data = []

    for pod in round_obj.pods.order_by('pod_number'):
        pod_data = {
            'Pod': pod.pod_number,
            'Table': pod.table_number or pod.pod_number,
        }

        # Add players (up to 6 seats for larger pods)
        assignments = pod.assignments.order_by('seat_position').all()
        for i, assignment in enumerate(assignments, 1):
            pod_data[f'Seat_{i}'] = assignment.player.name

        data.append(pod_data)

    df = pd.DataFrame(data)
    return df.to_csv(index=False)


def export_results_csv(round_obj):
    """
    Export round results to CSV format.

    Args:
        round_obj: Round object

    Returns:
        String: CSV content
    """
    data = []

    for pod in round_obj.pods.order_by('pod_number'):
        for assignment in pod.assignments.all():
            data.append({
                'Pod': pod.pod_number,
                'Player': assignment.player.name,
                'Placement': assignment.placement or 'N/A',
                'Points': assignment.points_earned if assignment.points_earned is not None else 'N/A',
            })

    df = pd.DataFrame(data)
    return df.to_csv(index=False)
