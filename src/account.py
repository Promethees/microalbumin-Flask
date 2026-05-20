import os
import secrets
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
import bcrypt

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    verification_token = db.Column(db.String(128), nullable=True)
    verification_expires = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_download = db.Column(db.DateTime, nullable=True)

    def set_password(self, password: str):
        self.password_hash = bcrypt.hashpw(
            password.encode('utf-8'), bcrypt.gensalt()
        ).decode('utf-8')

    def check_password(self, password: str) -> bool:
        return bcrypt.checkpw(
            password.encode('utf-8'),
            self.password_hash.encode('utf-8')
        )

    reset_token = db.Column(db.String(128), nullable=True)
    reset_expires = db.Column(db.DateTime, nullable=True)

    def generate_verification_token(self):
        self.verification_token = secrets.token_urlsafe(32)
        self.verification_expires = datetime.utcnow() + timedelta(hours=24)
        return self.verification_token

    def is_verification_token_valid(self, token: str) -> bool:
        return (
            self.verification_token == token
            and self.verification_expires is not None
            and datetime.utcnow() < self.verification_expires
        )

    def generate_reset_token(self):
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_expires = datetime.utcnow() + timedelta(hours=1)
        return self.reset_token

    def is_reset_token_valid(self, token: str) -> bool:
        return (
            self.reset_token == token
            and self.reset_expires is not None
            and datetime.utcnow() < self.reset_expires
        )


class OAuthConnection(db.Model):
    __tablename__ = 'oauth_connections'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    provider = db.Column(db.String(32), nullable=False)
    provider_user_id = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User', backref=db.backref('oauth_connections', lazy=True))

    __table_args__ = (
        db.UniqueConstraint('provider', 'provider_user_id', name='uq_oauth_provider_uid'),
    )


def run_migrations(engine):
    """Add columns introduced after the initial schema was created."""
    from sqlalchemy import text
    dialect = engine.dialect.name
    cols = [('reset_token', 'VARCHAR(128)'), ('reset_expires', 'TIMESTAMP' if dialect == 'postgresql' else 'DATETIME')]
    with engine.connect() as conn:
        for col, col_type in cols:
            try:
                if dialect == 'postgresql':
                    conn.execute(text(f'ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {col_type}'))
                else:
                    conn.execute(text(f'ALTER TABLE users ADD COLUMN {col} {col_type}'))
                conn.commit()
            except Exception:
                conn.rollback()
