from app import db


class SeatHistory(db.Model):
    __tablename__ = 'seat_history'

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)
    seat_position = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('tournament_id', 'player_id', 'round_number', name='unique_seat_per_player_round'),
    )

    def __repr__(self):
        return f'<SeatHistory: Player {self.player_id} Seat {self.seat_position} Round {self.round_number}>'

    @staticmethod
    def get_seat_history(player_id, tournament_id):
        """Return list of seat positions this player has had."""
        rows = SeatHistory.query.filter_by(
            tournament_id=tournament_id,
            player_id=player_id
        ).all()
        return [r.seat_position for r in rows]

    @staticmethod
    def get_available_seats(player_id, tournament_id, pod_size):
        """Return seats the player hasn't had in current cycle. Resets after full cycle."""
        all_seats = set(range(1, pod_size + 1))
        history = SeatHistory.get_seat_history(player_id, tournament_id)
        # Walk history to find current cycle
        used = set()
        for s in history:
            if len(used) == pod_size:
                used = set()
            used.add(s)
        if len(used) == pod_size:
            return all_seats  # just completed cycle — all available
        return all_seats - used if used else all_seats

    @staticmethod
    def record_seat(player_id, tournament_id, round_number, seat_position):
        entry = SeatHistory(
            tournament_id=tournament_id,
            player_id=player_id,
            round_number=round_number,
            seat_position=seat_position
        )
        db.session.add(entry)

    @staticmethod
    def bulk_seat_history(tournament_id, player_ids):
        """Get seat history for multiple players at once. Returns {player_id: [seats]}."""
        rows = SeatHistory.query.filter(
            SeatHistory.tournament_id == tournament_id,
            SeatHistory.player_id.in_(player_ids)
        ).all()
        history = {}
        for r in rows:
            history.setdefault(r.player_id, []).append(r.seat_position)
        return history
