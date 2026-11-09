from datetime import UTC, datetime
from decimal import Decimal

from . import db


def utcnow():
    return datetime.now(UTC)


class Account(db.Model):
    __tablename__ = "accounts"
    __table_args__ = (
        db.UniqueConstraint("region", "identifier"),
        db.CheckConstraint("region in ('cn', 'global')"),
        db.ForeignKeyConstraint(["group_id", "region"], ["account_groups.id", "account_groups.region"], name="fk_accounts_group_region"),
    )
    id = db.Column(db.Integer, primary_key=True)
    region = db.Column(db.String(10), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    identifier = db.Column(db.String(255), nullable=False)
    credential_encrypted = db.Column(db.LargeBinary, nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    health = db.Column(db.String(20), nullable=False, default="unknown")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    group_id = db.Column(db.Integer, nullable=True, index=True)
    real_user_id = db.Column(db.String(255), nullable=True)
    note = db.Column(db.Text, nullable=False, default="")
    health_reason = db.Column(db.String(255), nullable=True)
    last_active_at = db.Column(db.DateTime(timezone=True), nullable=True)
    verified_at = db.Column(db.DateTime(timezone=True), nullable=True)
    session_id = db.Column(db.String(36), nullable=False)


class ApiKey(db.Model):
    __tablename__ = "api_keys"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    prefix = db.Column(db.String(30), nullable=False)
    key_hash = db.Column(db.String(64), nullable=False, unique=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    note = db.Column(db.Text, nullable=False, default="")
    last_used_at = db.Column(db.DateTime(timezone=True), nullable=True)
    request_count = db.Column(db.Integer, nullable=False, default=0)


class AccountGroup(db.Model):
    __tablename__ = "account_groups"
    __table_args__ = (
        db.UniqueConstraint("region", "name"), db.UniqueConstraint("id", "region"),
        db.CheckConstraint("region in ('cn', 'global')"),
    )
    id = db.Column(db.Integer, primary_key=True)
    region = db.Column(db.String(10), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class CheckinRecord(db.Model):
    __tablename__ = "checkin_records"
    __table_args__ = (db.UniqueConstraint("account_id", "day"),)
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    day = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    trigger = db.Column(db.String(20), nullable=False)
    reward = db.Column(db.Numeric(24, 6), nullable=True)
    claim_id = db.Column(db.String(255), nullable=True)
    arrival = db.Column(db.String(20), nullable=True)
    message = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class BalanceSnapshot(db.Model):
    __tablename__ = "balance_snapshots"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    # A plan snapshot is deliberately not a wallet or an accounting transaction.
    amount = db.Column(db.Numeric(24, 6), nullable=False)
    unit = db.Column(db.String(80), nullable=False)
    provider_field = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class CreditEntry(db.Model):
    __tablename__ = "credit_entries"
    __table_args__ = (db.CheckConstraint("balance_after = balance_before + delta"),)
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    kind = db.Column(db.String(40), nullable=False)
    delta = db.Column(db.Numeric(24, 6), nullable=False, default=Decimal(0))
    balance_before = db.Column(db.Numeric(24, 6), nullable=False)
    balance_after = db.Column(db.Numeric(24, 6), nullable=False)
    upstream_id = db.Column(db.String(255), nullable=False, unique=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class RequestLog(db.Model):
    __tablename__ = "request_logs"
    id = db.Column(db.String(36), primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True, index=True)
    api_key_id = db.Column(db.Integer, db.ForeignKey("api_keys.id"), nullable=True, index=True)
    region = db.Column(db.String(10), nullable=False, index=True)
    protocol = db.Column(db.String(30), nullable=False)
    endpoint = db.Column(db.String(80), nullable=False)
    model = db.Column(db.String(255), nullable=False)
    http_status = db.Column(db.Integer, nullable=False)
    latency_ms = db.Column(db.Integer, nullable=False)
    stream = db.Column(db.Boolean, nullable=False)
    input_tokens = db.Column(db.Integer, nullable=True)
    output_tokens = db.Column(db.Integer, nullable=True)
    error_message = db.Column(db.String(255), nullable=True)
    headers = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)


class Setting(db.Model):
    __tablename__ = "settings"
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.JSON, nullable=False)


class CheckinJob(db.Model):
    __tablename__ = "checkin_jobs"
    id = db.Column(db.String(36), primary_key=True)
    region = db.Column(db.String(10), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="queued", index=True)
    trigger = db.Column(db.String(20), nullable=False, default="batch")
    schedule_key = db.Column(db.String(80), nullable=True, unique=True)
    lease_token = db.Column(db.String(36), nullable=True)
    lease_until = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)


class CheckinTask(db.Model):
    __tablename__ = "checkin_tasks"
    __table_args__ = (db.UniqueConstraint("job_id", "account_id"),)
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(36), db.ForeignKey("checkin_jobs.id"), nullable=False, index=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="queued")
    message = db.Column(db.String(255), nullable=False, default="")
