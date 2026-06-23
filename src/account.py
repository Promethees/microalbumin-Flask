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


class LicenseMachine(db.Model):
    """A machine a user's license is activated on (the hardware-lock seat table).

    Each permanent activation token is bound to one machine fingerprint (hwid).
    A user may hold up to MAX_MACHINES_PER_LICENSE distinct machines at once;
    activating on a new machine beyond that limit is refused until an existing one
    is deactivated (license transfer). Created by db.create_all() on startup.
    """
    __tablename__ = 'license_machines'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    hwid = db.Column(db.String(64), nullable=False, index=True)
    label = db.Column(db.String(255), nullable=True)  # optional friendly name
    activated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_seen = db.Column(db.DateTime, nullable=True)
    # Admin kill-switch: when True the seat is disabled. The token stays valid
    # cryptographically (still permanent, still hardware-matched) but the server
    # refuses it — AI proxy + auto-update fail immediately, and the desktop
    # license-check endpoint reports 'revoked'. Set per-account by the admin tool.
    revoked = db.Column(db.Boolean, default=False, nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref=db.backref('machines', lazy=True, cascade='all, delete-orphan'))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'hwid', name='uq_license_user_hwid'),
    )


def run_migrations(engine):
    """Add columns introduced after the initial schema was created."""
    from sqlalchemy import text
    dialect = engine.dialect.name
    ts_type = 'TIMESTAMP' if dialect == 'postgresql' else 'DATETIME'
    # (table, column, type) tuples for columns added after the initial schema.
    cols = [
        ('users', 'reset_token', 'VARCHAR(128)'),
        ('users', 'reset_expires', ts_type),
        # Admin revocation (license kill-switch) — see LicenseMachine.revoked.
        ('license_machines', 'revoked', 'BOOLEAN DEFAULT FALSE NOT NULL'
            if dialect == 'postgresql' else 'BOOLEAN DEFAULT 0 NOT NULL'),
        ('license_machines', 'revoked_at', ts_type),
    ]
    with engine.connect() as conn:
        for table, col, col_type in cols:
            try:
                if dialect == 'postgresql':
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type}'))
                else:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {col_type}'))
                conn.commit()
            except Exception:
                conn.rollback()
