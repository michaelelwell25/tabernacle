from datetime import datetime
from app import db
import secrets


class InviteToken(db.Model):
    __tablename__ = 'invite_tokens'

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(32))
    role = db.Column(db.String(20), nullable=False, default='to')
    used_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    used_by = db.relationship('User', backref='invite_used')

    @property
    def is_used(self):
        return self.used_by_id is not None
