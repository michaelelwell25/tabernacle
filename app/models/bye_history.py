from app import db


class ByeHistory(db.Model):
    __tablename__ = 'bye_history'

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('tournament_id', 'player_id', 'round_number', name='unique_bye_per_player_round'),
    )

    def __repr__(self):
        return f'<ByeHistory: Player {self.player_id} Round {self.round_number}>'

    @staticmethod
    def get_bye_count(player_id, tournament_id):
        return ByeHistory.query.filter_by(
            tournament_id=tournament_id,
            player_id=player_id
        ).count()

    @staticmethod
    def has_had_bye(player_id, tournament_id):
        return ByeHistory.query.filter_by(
            tournament_id=tournament_id,
            player_id=player_id
        ).first() is not None

    @staticmethod
    def record_bye(player_id, tournament_id, round_number):
        bye = ByeHistory(
            tournament_id=tournament_id,
            player_id=player_id,
            round_number=round_number
        )
        db.session.add(bye)
