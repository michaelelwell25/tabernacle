from datetime import datetime
from app import db


class LeaguePlayer(db.Model):
    __tablename__ = 'league_players'

    id = db.Column(db.Integer, primary_key=True)
    league_id = db.Column(db.Integer, db.ForeignKey('leagues.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    joined_week = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    player_links = db.relationship('LeaguePlayerLink', backref='league_player', lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('league_id', 'name', name='unique_league_player_name'),
    )

    def __repr__(self):
        return f'<LeaguePlayer {self.name}>'
