from datetime import datetime
from app import db


class Tournament(db.Model):
    __tablename__ = 'tournaments'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='registration')  # registration, active, playoffs, completed
    playoff_cut = db.Column(db.Integer)  # None, 4, 10, 13, 16
    current_round = db.Column(db.Integer, default=0)
    scoring_system = db.Column(db.String(50), default='3-1-0-0')  # 1st-2nd-3rd-4th points
    bye_points = db.Column(db.Integer, default=1)
    draw_points = db.Column(db.Integer, default=1)
    allow_byes = db.Column(db.Boolean, default=True)
    round_timer_minutes = db.Column(db.Integer, default=80)
    seat_scoring = db.Column(db.Boolean, default=False)
    seat_win_points = db.Column(db.String(50), default='5.2-5.4-5.6-5.8')  # seat 1-2-3-4 win
    seat_draw_points = db.Column(db.String(50), default='0.2-0.4-0.6-0.8')  # seat 1-2-3-4 draw
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    players = db.relationship('Player', backref='tournament', lazy='dynamic', cascade='all, delete-orphan')
    rounds = db.relationship('Round', backref='tournament', lazy='dynamic', cascade='all, delete-orphan')
    pairing_history = db.relationship('PairingHistory', backref='tournament', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Tournament {self.name}>'

    def get_scoring_points(self):
        """Parse scoring system string and return points for each placement"""
        points = list(map(int, self.scoring_system.split('-')))
        return {
            1: points[0] if len(points) > 0 else 3,
            2: points[1] if len(points) > 1 else 1,
            3: points[2] if len(points) > 2 else 0,
            4: points[3] if len(points) > 3 else 0,
        }

    def get_seat_win_points(self):
        """Parse seat win points string. Returns dict {seat: points}."""
        vals = list(map(float, self.seat_win_points.split('-')))
        return {i+1: vals[i] for i in range(len(vals))}

    def get_seat_draw_points(self):
        """Parse seat draw points string. Returns dict {seat: points}."""
        vals = list(map(float, self.seat_draw_points.split('-')))
        return {i+1: vals[i] for i in range(len(vals))}

    def get_active_players(self):
        """Get all players who haven't dropped"""
        return self.players.filter_by(dropped=False).all()

    def get_current_round(self):
        """Get the current round object"""
        return self.rounds.filter_by(round_number=self.current_round).first()
