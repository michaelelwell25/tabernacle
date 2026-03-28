from datetime import datetime
from app import db


class Player(db.Model):
    __tablename__ = 'players'

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    commander = db.Column(db.String(100))  # Commander name
    decklist_url = db.Column(db.String(500))  # Moxfield or other decklist link
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    dci_number = db.Column(db.String(20))  # Optional DCI/Arena ID
    dropped = db.Column(db.Boolean, default=False)
    drop_round = db.Column(db.Integer)  # Round when player dropped
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    pod_assignments = db.relationship('PodAssignment', backref='player', lazy='dynamic', cascade='all, delete-orphan')

    # Unique constraint: one player name per tournament
    __table_args__ = (
        db.UniqueConstraint('tournament_id', 'name', name='unique_player_per_tournament'),
    )

    def __repr__(self):
        return f'<Player {self.name}>'

    def get_total_points(self):
        """Calculate total points earned across all completed matches"""
        total = 0
        for assignment in self.pod_assignments:
            if assignment.points_earned is not None:
                total += assignment.points_earned
        return total

    def get_matches_played(self):
        """Count number of completed matches"""
        return self.pod_assignments.filter(
            PodAssignment.points_earned.isnot(None)
        ).count()

    def get_opponents(self):
        """Get list of all opponents this player has faced"""
        from app.models.pairing_history import PairingHistory
        from app.models.player import Player

        # Get all pairing history records involving this player
        history = PairingHistory.query.filter(
            db.or_(
                PairingHistory.player1_id == self.id,
                PairingHistory.player2_id == self.id
            ),
            PairingHistory.tournament_id == self.tournament_id
        ).all()

        # Extract opponent IDs
        opponent_ids = set()
        for record in history:
            if record.player1_id == self.id:
                opponent_ids.add(record.player2_id)
            else:
                opponent_ids.add(record.player1_id)

        # Return Player objects
        return Player.query.filter(Player.id.in_(opponent_ids)).all()


# Avoid circular import by importing at the end
from app.models.pod_assignment import PodAssignment
