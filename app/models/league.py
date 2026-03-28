from datetime import datetime
from app import db


class League(db.Model):
    __tablename__ = 'leagues'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    num_weeks = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='active')  # active, completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    league_players = db.relationship('LeaguePlayer', backref='league', lazy='dynamic', cascade='all, delete-orphan')
    tournaments = db.relationship('Tournament', backref='league', lazy='dynamic', order_by='Tournament.week_number')

    def __repr__(self):
        return f'<League {self.name}>'

    def get_current_week(self):
        return self.tournaments.count()

    def get_completed_weeks(self):
        return self.tournaments.filter_by(status='completed').count()
