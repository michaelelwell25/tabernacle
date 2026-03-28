from app import db


class LeaguePlayerLink(db.Model):
    __tablename__ = 'league_player_links'

    id = db.Column(db.Integer, primary_key=True)
    league_player_id = db.Column(db.Integer, db.ForeignKey('league_players.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('league_player_id', 'tournament_id', name='unique_league_player_per_tournament'),
        db.UniqueConstraint('player_id', name='unique_player_link'),
    )

    def __repr__(self):
        return f'<LeaguePlayerLink: LP {self.league_player_id} -> Player {self.player_id}>'
