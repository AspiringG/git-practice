"""SQLite storage: connection handling and schema.

The schema itself enforces the most important invariants so that they hold
even if application code is wrong:

* signatures and audit events can never be deleted;
* the signed content of a signature (who, when, which hash) can never change —
  the only permitted update is marking a still-valid signature as invalidated;
* a person can hold at most one valid signature per document, and each
  signing step can be filled at most once.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "esign.db"


def db_path() -> Path:
    return Path(os.environ.get("ESIGN_DB_PATH", DEFAULT_DB_PATH))


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # One connection per request; FastAPI may run a dependency's setup and teardown on
    # different worker threads, so the same-thread guard is disabled.
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS departments (
    code            TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    manager_user_id INTEGER
);

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY,
    full_name       TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('HR_EMPLOYEE', 'HR_MANAGER', 'WAREHOUSE_OPERATOR')),
    title           TEXT NOT NULL,
    department_code TEXT NOT NULL REFERENCES departments(code),
    pin_hash        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS equipment (
    id                 INTEGER PRIMARY KEY,
    asset_code         TEXT NOT NULL UNIQUE,
    category           TEXT NOT NULL CHECK (category IN ('PRIBOR', 'LAMP')),
    type_name          TEXT NOT NULL,
    power              TEXT NOT NULL,
    location           TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'IN_STOCK' CHECK (status IN ('IN_STOCK', 'ISSUED')),
    holder_user_id     INTEGER REFERENCES users(id),
    issued_document_id INTEGER
);

CREATE TABLE IF NOT EXISTS document_sequences (
    year       INTEGER PRIMARY KEY,
    last_value INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id                   INTEGER PRIMARY KEY,
    document_number      TEXT NOT NULL UNIQUE,
    doc_type             TEXT NOT NULL DEFAULT 'WAREHOUSE_HANDOVER',
    status               TEXT NOT NULL CHECK (status IN
                             ('DRAFT', 'WAITING_FOR_SIGNATURES', 'SIGNED', 'RELEASED', 'CANCELLED')),
    recipient_user_id    INTEGER NOT NULL REFERENCES users(id),
    department_code      TEXT NOT NULL REFERENCES departments(code),
    purpose              TEXT NOT NULL,
    issue_date           TEXT NOT NULL,
    expected_return_date TEXT NOT NULL,
    notes                TEXT NOT NULL DEFAULT '',
    revision             INTEGER NOT NULL DEFAULT 0,
    payload_snapshot     TEXT,
    payload_hash         TEXT,
    created_by           INTEGER NOT NULL REFERENCES users(id),
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    submitted_at         TEXT,
    signed_at            TEXT,
    released_at          TEXT,
    released_by          INTEGER REFERENCES users(id),
    cancelled_at         TEXT,
    cancelled_by         INTEGER REFERENCES users(id),
    cancel_reason        TEXT
);

CREATE TABLE IF NOT EXISTS document_items (
    id           INTEGER PRIMARY KEY,
    document_id  INTEGER NOT NULL REFERENCES documents(id),
    line_no      INTEGER NOT NULL,
    equipment_id INTEGER NOT NULL REFERENCES equipment(id),
    asset_code   TEXT NOT NULL,
    category     TEXT NOT NULL,
    description  TEXT NOT NULL,
    UNIQUE (document_id, equipment_id),
    UNIQUE (document_id, line_no)
);

CREATE TABLE IF NOT EXISTS required_signatures (
    id             INTEGER PRIMARY KEY,
    document_id    INTEGER NOT NULL REFERENCES documents(id),
    signing_order  INTEGER NOT NULL,
    signer_role    TEXT NOT NULL CHECK (signer_role IN ('RECIPIENT', 'HR_MANAGER', 'WAREHOUSE_OPERATOR')),
    signer_user_id INTEGER NOT NULL REFERENCES users(id),
    UNIQUE (document_id, signing_order)
);

CREATE TABLE IF NOT EXISTS document_signatures (
    id                  INTEGER PRIMARY KEY,
    document_id         INTEGER NOT NULL REFERENCES documents(id),
    document_revision   INTEGER NOT NULL,
    signing_order       INTEGER NOT NULL,
    signer_user_id      INTEGER NOT NULL REFERENCES users(id),
    signer_name         TEXT NOT NULL,
    signer_role         TEXT NOT NULL,
    signer_title        TEXT NOT NULL,
    signed_at           TEXT NOT NULL,
    document_hash       TEXT NOT NULL,
    method              TEXT NOT NULL DEFAULT 'INTERNAL_PIN' CHECK (method = 'INTERNAL_PIN'),
    invalidated_at      TEXT,
    invalidated_by      INTEGER REFERENCES users(id),
    invalidation_reason TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_signature_active_signer
    ON document_signatures (document_id, signer_user_id) WHERE invalidated_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_signature_active_step
    ON document_signatures (document_id, signing_order) WHERE invalidated_at IS NULL;

CREATE TRIGGER IF NOT EXISTS trg_signature_no_delete
BEFORE DELETE ON document_signatures
BEGIN
    SELECT RAISE(ABORT, 'Signatures are immutable and cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS trg_signature_immutable
BEFORE UPDATE ON document_signatures
WHEN OLD.invalidated_at IS NOT NULL
  OR NEW.document_id       IS NOT OLD.document_id
  OR NEW.document_revision IS NOT OLD.document_revision
  OR NEW.signing_order     IS NOT OLD.signing_order
  OR NEW.signer_user_id    IS NOT OLD.signer_user_id
  OR NEW.signer_name       IS NOT OLD.signer_name
  OR NEW.signer_role       IS NOT OLD.signer_role
  OR NEW.signer_title      IS NOT OLD.signer_title
  OR NEW.signed_at         IS NOT OLD.signed_at
  OR NEW.document_hash     IS NOT OLD.document_hash
  OR NEW.method            IS NOT OLD.method
BEGIN
    SELECT RAISE(ABORT, 'Signatures are immutable');
END;

CREATE TABLE IF NOT EXISTS audit_events (
    id           INTEGER PRIMARY KEY,
    document_id  INTEGER NOT NULL REFERENCES documents(id),
    event_type   TEXT NOT NULL,
    actor_user_id INTEGER REFERENCES users(id),
    actor_name   TEXT,
    actor_title  TEXT,
    occurred_at  TEXT NOT NULL,
    description  TEXT NOT NULL,
    detail       TEXT
);

CREATE TRIGGER IF NOT EXISTS trg_audit_no_update
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'Audit events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_audit_no_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'Audit events are append-only');
END;
"""

TABLES = [
    "audit_events",
    "document_signatures",
    "required_signatures",
    "document_items",
    "documents",
    "document_sequences",
    "equipment",
    "sessions",
    "users",
    "departments",
]


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def drop_all(conn: sqlite3.Connection) -> None:
    """Demo reset only: dropping tables bypasses the row-level delete triggers."""
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")
