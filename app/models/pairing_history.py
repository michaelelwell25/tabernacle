from app import db


class PairingHistory(db.Model):
    __tablename__ = 'pairing_history'

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    player1_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f'<PairingHistory: Players {self.player1_id} & {self.player2_id} in Round {self.round_number}>'

    @staticmethod
    def have_players_met(player1_id, player2_id, tournament_id):
        """Check if two players have faced each other before"""
        history = PairingHistory.query.filter_by(
            tournament_id=tournament_id
        ).filter(
            db.or_(
                db.and_(
                    PairingHistory.player1_id == player1_id,
                    PairingHistory.player2_id == player2_id
                ),
                db.and_(
                    PairingHistory.player1_id == player2_id,
                    PairingHistory.player2_id == player1_id
                )
            )
        ).first()

        return history is not None

    @staticmethod
    def record_pod_pairings(pod_players, tournament_id, round_number):
        """
        Record all pairwise pairings for a pod.
        For 4 players, this creates 6 pairing history entries.
        """
        n = len(pod_players)

        for i in range(n):
            for j in range(i + 1, n):
                history = PairingHistory(
                    tournament_id=tournament_id,
                    player1_id=pod_players[i].id,
                    player2_id=pod_players[j].id,
                    round_number=round_number
                )
                db.session.add(history)

        db.session.commit()
