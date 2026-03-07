from app import db


class Pod(db.Model):
    __tablename__ = 'pods'

    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey('rounds.id'), nullable=False)
    pod_number = db.Column(db.Integer, nullable=False)
    table_number = db.Column(db.Integer)  # Physical table assignment
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed
    is_bye = db.Column(db.Boolean, default=False)

    # Relationships
    assignments = db.relationship('PodAssignment', backref='pod', lazy='dynamic', cascade='all, delete-orphan')

    # Unique constraint: one pod number per round
    __table_args__ = (
        db.UniqueConstraint('round_id', 'pod_number', name='unique_pod_per_round'),
    )

    def __repr__(self):
        return f'<Pod {self.pod_number} in Round {self.round_id}>'

    def get_players(self):
        """Get all players assigned to this pod"""
        return [assignment.player for assignment in self.assignments.all()]

    def get_player_count(self):
        """Get number of players in this pod"""
        return self.assignments.count()

    def is_complete(self):
        return self.status == 'completed'

    def has_results(self):
        return self.status == 'completed'
