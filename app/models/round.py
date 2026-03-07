from datetime import datetime
from app import db


class Round(db.Model):
    __tablename__ = 'rounds'

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, active, completed
    is_playoff = db.Column(db.Boolean, default=False)
    playoff_stage = db.Column(db.String(20))  # 'semi', 'final'
    timer_end = db.Column(db.DateTime)  # When the round timer expires
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    pods = db.relationship('Pod', backref='round', lazy='dynamic', cascade='all, delete-orphan')

    # Unique constraint: one round number per tournament
    __table_args__ = (
        db.UniqueConstraint('tournament_id', 'round_number', name='unique_round_per_tournament'),
    )

    def __repr__(self):
        return f'<Round {self.round_number} of Tournament {self.tournament_id}>'

    def is_complete(self):
        """Check if all pods in this round have results entered"""
        for pod in self.pods:
            if not pod.is_complete():
                return False
        return True

    def get_pod_count(self):
        """Get number of pods in this round"""
        return self.pods.count()
