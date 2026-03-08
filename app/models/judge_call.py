from datetime import datetime
from app import db


class JudgeCall(db.Model):
    __tablename__ = 'judge_calls'

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    player_name = db.Column(db.String(100), nullable=False)
    table_number = db.Column(db.Integer)
    round_number = db.Column(db.Integer)
    reason = db.Column(db.String(200))
    status = db.Column(db.String(20), default='open')  # open, claimed, resolved
    claimed_by = db.Column(db.String(100))  # judge name
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    claimed_at = db.Column(db.DateTime)
    resolved_at = db.Column(db.DateTime)

    tournament = db.relationship('Tournament', backref=db.backref('judge_calls', lazy='dynamic'))

    def response_time_seconds(self):
        if self.claimed_at and self.created_at:
            return (self.claimed_at - self.created_at).total_seconds()
        return None
