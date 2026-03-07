from app import db


class PodAssignment(db.Model):
    __tablename__ = 'pod_assignments'

    id = db.Column(db.Integer, primary_key=True)
    pod_id = db.Column(db.Integer, db.ForeignKey('pods.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    seat_position = db.Column(db.Integer)  # 1-4, can be randomized
    placement = db.Column(db.Integer)  # 1st, 2nd, 3rd, 4th (result)
    points_earned = db.Column(db.Float, default=0)

    # Unique constraint: one player per pod
    __table_args__ = (
        db.UniqueConstraint('pod_id', 'player_id', name='unique_player_per_pod'),
    )

    def __repr__(self):
        return f'<PodAssignment: Player {self.player_id} in Pod {self.pod_id}>'
