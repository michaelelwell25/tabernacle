from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='player')  # 'admin', 'to', or 'player'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tournaments = db.relationship('Tournament', backref='owner', lazy='dynamic')
    leagues = db.relationship('League', backref='owner', lazy='dynamic')
    player_records = db.relationship('Player', backref='user', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == 'admin'

    def is_to(self):
        return self.role in ('admin', 'to')

    def is_player(self):
        return self.role == 'player'

    def __repr__(self):
        return f'<User {self.email}>'
