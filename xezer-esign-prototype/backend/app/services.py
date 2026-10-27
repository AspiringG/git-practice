"""Handover-document workflow.

Every state-changing rule lives here and is enforced server-side; the
frontend only mirrors the `actions` block returned by `document_detail`.

Lifecycle:  DRAFT → WAITING_FOR_SIGNATURES → SIGNED → RELEASED
            (any non-final state) → CANCELLED
            WAITING_FOR_SIGNATURES / SIGNED → DRAFT  (explicit, invalidates signatures)
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Iterator

from .security import canonical_json, fingerprint, new_session_token, verify_pin

DRAFT = "DRAFT"
WAITING = "WAITING_FOR_SIGNATURES"
SIGNED = "SIGNED"
RELEASED = "RELEASED"
CANCELLED = "CANCELLED"
ACTIVE_STATUSES = (DRAFT, WAITING, SIGNED)

DOC_TYPE = "WAREHOUSE_HANDOVER"
DOC_TYPE_LABEL = "Warehouse equipment handover"
DOC_TYPE_LABEL_AZ = "Təhvil-təslim aktı"
DOC_PREFIX = "ANB"
SNAPSHOT_SCHEMA = "xezer.esign.warehouse-handover/v1"

STEP_LABELS = {
    "RECIPIENT": "Recipient",
    "HR_MANAGER": "HR Manager",
    "WAREHOUSE_OPERATOR": "Warehouse Operator",
}
STEP_ORDER = ["RECIPIENT", "HR_MANAGER", "WAREHOUSE_OPERATOR"]

MAX_ITEMS = 20


class WorkflowError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


# --------------------------------------------------------------------------- clock

_frozen_now: datetime | None = None


def now() -> str:
    dt = _frozen_now or datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@contextmanager
def frozen_time(dt: datetime) -> Iterator[None]:
    """Used by the seed script to back-date demo history."""
    global _frozen_now
    previous, _frozen_now = _frozen_now, dt
    try:
        yield
    finally:
        _frozen_now = previous


def short_hash(value: str | None) -> str:
    return f"{value[:4]}…{value[-4:]}".upper() if value else ""


# --------------------------------------------------------------------------- users & sessions

def get_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def public_user(user: sqlite3.Row | None) -> dict | None:
    if user is None:
        return None
    return {
        "id": user["id"],
        "full_name": user["full_name"],
        "role": user["role"],
        "title": user["title"],
        "department_code": user["department_code"],
    }


def list_users(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    return [public_user(r) for r in rows]


def login(conn: sqlite3.Connection, user_id: int) -> str:
    """Demo login: choosing a user opens a session. Signing still needs that user's PIN."""
    if get_user(conn, user_id) is None:
        raise WorkflowError(404, "USER_NOT_FOUND", "Unknown user.")
    token = new_session_token()
    with conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)", (token, user_id, now())
        )
    return token


def user_for_token(conn: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?", (token,)
    ).fetchone()


def _require_operator(user: sqlite3.Row, action: str) -> None:
    if user["role"] != "WAREHOUSE_OPERATOR":
        raise WorkflowError(403, "NOT_PERMITTED", f"Only the Warehouse Operator can {action}.")


# --------------------------------------------------------------------------- equipment

def equipment_description(row: sqlite3.Row) -> str:
    if row["category"] == "LAMP":
        return f"{row['type_name']} lamp · {row['power']}"
    return f"{row['type_name']} · {row['power']}"


def _reservations(conn: sqlite3.Connection, exclude_doc_id: int | None = None) -> dict[int, sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT di.equipment_id, d.id AS document_id, d.document_number
          FROM document_items di JOIN documents d ON d.id = di.document_id
         WHERE d.status IN (?, ?, ?) AND d.id IS NOT ?
        """,
        (*ACTIVE_STATUSES, exclude_doc_id),
    ).fetchall()
    return {r["equipment_id"]: r for r in rows}


def list_equipment(conn: sqlite3.Connection, for_document_id: int | None = None) -> list[dict]:
    reservations = _reservations(conn, for_document_id)
    rows = conn.execute(
        """
        SELECT e.*, u.full_name AS holder_name, d.document_number AS issued_document_number
          FROM equipment e
          LEFT JOIN users u ON u.id = e.holder_user_id
          LEFT JOIN documents d ON d.id = e.issued_document_id
         ORDER BY e.category DESC, e.asset_code
        """
    ).fetchall()
    result = []
    for r in rows:
        reserved = reservations.get(r["id"])
        if r["status"] == "ISSUED":
            availability = "ISSUED"
        elif reserved is not None:
            availability = "RESERVED"
        else:
            availability = "AVAILABLE"
        result.append(
            {
                "asset_code": r["asset_code"],
                "category": r["category"],
                "type_name": r["type_name"],
                "power": r["power"],
                "location": r["location"],
                "description": equipment_description(r),
                "availability": availability,
                "holder_name": r["holder_name"],
                "issued_document_number": r["issued_document_number"],
                "reserved_document_number": reserved["document_number"] if reserved else None,
            }
        )
    return result


# --------------------------------------------------------------------------- numbering

def next_document_number(conn: sqlite3.Connection, year: int) -> str:
    row = conn.execute(
        """
        INSERT INTO document_sequences (year, last_value) VALUES (?, 1)
        ON CONFLICT(year) DO UPDATE SET last_value = last_value + 1
        RETURNING last_value
        """,
        (year,),
    ).fetchone()
    return f"{DOC_PREFIX}-{year}-{row['last_value']:05d}"


# --------------------------------------------------------------------------- validation

def _validated_payload(conn: sqlite3.Connection, payload: dict, doc_id: int | None) -> dict:
    recipient = get_user(conn, int(payload.get("recipient_user_id") or 0))
    if recipient is None:
        raise WorkflowError(422, "INVALID_RECIPIENT", "Select a recipient.")
    if recipient["role"] != "HR_EMPLOYEE":
        raise WorkflowError(
            422,
            "INVALID_RECIPIENT",
            f"{recipient['full_name']} is an approver in this workflow and cannot be the recipient.",
        )
    department = conn.execute(
        "SELECT * FROM departments WHERE code = ?", (recipient["department_code"],)
    ).fetchone()
    if department is None or department["manager_user_id"] is None:
        raise WorkflowError(422, "NO_MANAGER", "The recipient's department has no manager to approve.")

    purpose = (payload.get("purpose") or "").strip()
    if not purpose:
        raise WorkflowError(422, "PURPOSE_REQUIRED", "Purpose is required.")
    if len(purpose) > 500:
        raise WorkflowError(422, "PURPOSE_TOO_LONG", "Purpose must be at most 500 characters.")
    notes = (payload.get("notes") or "").strip()
    if len(notes) > 2000:
        raise WorkflowError(422, "NOTES_TOO_LONG", "Notes must be at most 2000 characters.")

    try:
        issue_date = date.fromisoformat(str(payload.get("issue_date")))
        return_date = date.fromisoformat(str(payload.get("expected_return_date")))
    except ValueError:
        raise WorkflowError(422, "INVALID_DATE", "Issue date and expected return date are required.")
    if return_date < issue_date:
        raise WorkflowError(422, "INVALID_DATE", "Expected return date cannot be before the issue date.")

    codes = [str(c).strip().upper() for c in payload.get("equipment_codes") or []]
    if not codes:
        raise WorkflowError(422, "NO_EQUIPMENT", "Add at least one equipment item.")
    if len(codes) > MAX_ITEMS:
        raise WorkflowError(422, "TOO_MANY_ITEMS", f"A handover can contain at most {MAX_ITEMS} items.")
    if len(set(codes)) != len(codes):
        raise WorkflowError(422, "DUPLICATE_EQUIPMENT", "Each equipment item can be added only once.")

    reservations = _reservations(conn, doc_id)
    equipment = []
    for code in codes:
        row = conn.execute("SELECT * FROM equipment WHERE asset_code = ?", (code,)).fetchone()
        if row is None:
            raise WorkflowError(422, "UNKNOWN_EQUIPMENT", f"Equipment {code} does not exist.")
        if row["status"] == "ISSUED":
            raise WorkflowError(409, "EQUIPMENT_UNAVAILABLE", f"{code} is already issued to someone.")
        if row["id"] in reservations:
            raise WorkflowError(
                409,
                "EQUIPMENT_UNAVAILABLE",
                f"{code} is already on document {reservations[row['id']]['document_number']}.",
            )
        equipment.append(row)

    return {
        "recipient": recipient,
        "department": department,
        "purpose": purpose,
        "notes": notes,
        "issue_date": issue_date.isoformat(),
        "expected_return_date": return_date.isoformat(),
        "equipment": equipment,
    }


def _warehouse_signer(conn: sqlite3.Connection, creator: sqlite3.Row) -> sqlite3.Row:
    if creator["role"] == "WAREHOUSE_OPERATOR":
        return creator
    return conn.execute("SELECT * FROM users WHERE role = 'WAREHOUSE_OPERATOR' ORDER BY id").fetchone()


def _write_lines_and_signers(conn: sqlite3.Connection, doc_id: int, data: dict, creator: sqlite3.Row) -> None:
    conn.execute("DELETE FROM document_items WHERE document_id = ?", (doc_id,))
    conn.execute("DELETE FROM required_signatures WHERE document_id = ?", (doc_id,))
    for line_no, eq in enumerate(data["equipment"], start=1):
        conn.execute(
            """INSERT INTO document_items (document_id, line_no, equipment_id, asset_code, category, description)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (doc_id, line_no, eq["id"], eq["asset_code"], eq["category"], equipment_description(eq)),
        )
    signers = {
        "RECIPIENT": data["recipient"]["id"],
        "HR_MANAGER": data["department"]["manager_user_id"],
        "WAREHOUSE_OPERATOR": _warehouse_signer(conn, creator)["id"],
    }
    for order, role in enumerate(STEP_ORDER, start=1):
        conn.execute(
            "INSERT INTO required_signatures (document_id, signing_order, signer_role, signer_user_id) VALUES (?, ?, ?, ?)",
            (doc_id, order, role, signers[role]),
        )


def _audit(
    conn: sqlite3.Connection,
    doc_id: int,
    event_type: str,
    description: str,
    actor: sqlite3.Row | None = None,
    detail: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO audit_events (document_id, event_type, actor_user_id, actor_name, actor_title,
                                     occurred_at, description, detail)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            doc_id,
            event_type,
            actor["id"] if actor else None,
            actor["full_name"] if actor else None,
            actor["title"] if actor else None,
            now(),
            description,
            detail,
        ),
    )


def _get_doc(conn: sqlite3.Connection, doc_id: int) -> sqlite3.Row:
    doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if doc is None:
        raise WorkflowError(404, "DOCUMENT_NOT_FOUND", "Document not found.")
    return doc


# --------------------------------------------------------------------------- create / edit

def create_document(conn: sqlite3.Connection, user: sqlite3.Row, payload: dict) -> int:
    _require_operator(user, "create handover documents")
    data = _validated_payload(conn, payload, None)
    ts = now()
    with conn:
        number = next_document_number(conn, int(ts[:4]))
        cur = conn.execute(
            """INSERT INTO documents (document_number, doc_type, status, recipient_user_id, department_code,
                                      purpose, issue_date, expected_return_date, notes, created_by,
                                      created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                number, DOC_TYPE, DRAFT, data["recipient"]["id"], data["department"]["code"],
                data["purpose"], data["issue_date"], data["expected_return_date"], data["notes"],
                user["id"], ts, ts,
            ),
        )
        doc_id = cur.lastrowid
        _write_lines_and_signers(conn, doc_id, data, user)
        codes = ", ".join(e["asset_code"] for e in data["equipment"])
        _audit(conn, doc_id, "CREATED", "Document created", user,
               f"For {data['recipient']['full_name']} · {codes}")
    return doc_id


def _item_codes(conn: sqlite3.Connection, doc_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT asset_code FROM document_items WHERE document_id = ? ORDER BY line_no", (doc_id,)
    ).fetchall()
    return [r["asset_code"] for r in rows]


def update_document(conn: sqlite3.Connection, user: sqlite3.Row, doc_id: int, payload: dict) -> None:
    _require_operator(user, "edit handover documents")
    doc = _get_doc(conn, doc_id)
    if doc["status"] != DRAFT:
        raise WorkflowError(
            409,
            "DOCUMENT_LOCKED",
            "The document is locked while it is being signed. "
            "Use 'Edit document and invalidate signatures' to change it.",
        )
    data = _validated_payload(conn, payload, doc_id)

    old_codes = _item_codes(conn, doc_id)
    new_codes = [e["asset_code"] for e in data["equipment"]]
    changes = []
    if doc["recipient_user_id"] != data["recipient"]["id"]:
        changes.append("recipient")
    if old_codes != new_codes:
        added = [c for c in new_codes if c not in old_codes]
        removed = [c for c in old_codes if c not in new_codes]
        parts = [f"+{c}" for c in added] + [f"−{c}" for c in removed]
        changes.append(f"equipment ({', '.join(parts)})" if parts else "equipment order")
    for field, label in (
        ("purpose", "purpose"),
        ("issue_date", "issue date"),
        ("expected_return_date", "return date"),
        ("notes", "notes"),
    ):
        if doc[field] != data[field]:
            changes.append(label)

    with conn:
        conn.execute(
            """UPDATE documents SET recipient_user_id = ?, department_code = ?, purpose = ?, issue_date = ?,
                                    expected_return_date = ?, notes = ?, updated_at = ?
               WHERE id = ?""",
            (
                data["recipient"]["id"], data["department"]["code"], data["purpose"], data["issue_date"],
                data["expected_return_date"], data["notes"], now(), doc_id,
            ),
        )
        _write_lines_and_signers(conn, doc_id, data, user)
        if changes:
            _audit(conn, doc_id, "UPDATED", "Document details updated", user,
                   "Changed: " + ", ".join(changes))


# --------------------------------------------------------------------------- snapshot

def build_snapshot(conn: sqlite3.Connection, doc_id: int) -> dict:
    """Canonical content of the document — exactly what the signers sign."""
    doc = _get_doc(conn, doc_id)
    recipient = get_user(conn, doc["recipient_user_id"])
    department = conn.execute("SELECT * FROM departments WHERE code = ?", (doc["department_code"],)).fetchone()
    items = conn.execute(
        "SELECT * FROM document_items WHERE document_id = ? ORDER BY line_no", (doc_id,)
    ).fetchall()
    signers = conn.execute(
        """SELECT rs.*, u.full_name, u.title FROM required_signatures rs JOIN users u ON u.id = rs.signer_user_id
            WHERE rs.document_id = ? ORDER BY rs.signing_order""",
        (doc_id,),
    ).fetchall()
    return {
        "schema": SNAPSHOT_SCHEMA,
        "document_number": doc["document_number"],
        "document_type": doc["doc_type"],
        "revision": doc["revision"],
        "recipient": {"user_id": recipient["id"], "full_name": recipient["full_name"], "title": recipient["title"]},
        "department": {"code": department["code"], "name": department["name"]},
        "equipment": [
            {
                "line_no": i["line_no"],
                "asset_code": i["asset_code"],
                "category": i["category"],
                "description": i["description"],
            }
            for i in items
        ],
        "purpose": doc["purpose"],
        "issue_date": doc["issue_date"],
        "expected_return_date": doc["expected_return_date"],
        "notes": doc["notes"],
        "required_signers": [
            {
                "order": s["signing_order"],
                "role": s["signer_role"],
                "user_id": s["signer_user_id"],
                "full_name": s["full_name"],
                "title": s["title"],
            }
            for s in signers
        ],
    }


def submit_document(conn: sqlite3.Connection, user: sqlite3.Row, doc_id: int) -> None:
    _require_operator(user, "send documents for signature")
    doc = _get_doc(conn, doc_id)
    if doc["status"] != DRAFT:
        raise WorkflowError(409, "INVALID_STATE", "Only draft documents can be sent for signatures.")
    # Equipment may have been taken by another document since the draft was saved.
    reservations = _reservations(conn, doc_id)
    for item in conn.execute(
        """SELECT di.asset_code, di.equipment_id, e.status FROM document_items di
             JOIN equipment e ON e.id = di.equipment_id WHERE di.document_id = ?""",
        (doc_id,),
    ):
        if item["status"] == "ISSUED" or item["equipment_id"] in reservations:
            raise WorkflowError(409, "EQUIPMENT_UNAVAILABLE", f"{item['asset_code']} is no longer available.")

    with conn:
        conn.execute("UPDATE documents SET revision = revision + 1 WHERE id = ?", (doc_id,))
        snapshot = build_snapshot(conn, doc_id)
        digest = fingerprint(snapshot)
        ts = now()
        conn.execute(
            """UPDATE documents SET status = ?, payload_snapshot = ?, payload_hash = ?, submitted_at = ?,
                                    updated_at = ? WHERE id = ?""",
            (WAITING, canonical_json(snapshot), digest, ts, ts, doc_id),
        )
        first = snapshot["required_signers"][0]
        _audit(conn, doc_id, "SUBMITTED", "Sent for signatures", user,
               f"Fingerprint {short_hash(digest)} · first signer: {first['full_name']}")


def reopen_document(conn: sqlite3.Connection, user: sqlite3.Row, doc_id: int, confirm_invalidate: bool) -> int:
    """Return a document to DRAFT for editing. Any existing signatures are invalidated."""
    _require_operator(user, "edit handover documents")
    doc = _get_doc(conn, doc_id)
    if doc["status"] not in (WAITING, SIGNED):
        raise WorkflowError(409, "INVALID_STATE", "Only documents awaiting signatures or signed (not yet released) can be reopened.")
    active = _active_signatures(conn, doc_id)
    if active and not confirm_invalidate:
        raise WorkflowError(
            409,
            "CONFIRMATION_REQUIRED",
            f"Editing will invalidate {len(active)} existing signature(s). Confirm to continue.",
        )
    ts = now()
    with conn:
        conn.execute(
            """UPDATE document_signatures SET invalidated_at = ?, invalidated_by = ?, invalidation_reason = ?
                WHERE document_id = ? AND invalidated_at IS NULL""",
            (ts, user["id"], "Document returned to draft for editing", doc_id),
        )
        conn.execute(
            """UPDATE documents SET status = ?, payload_snapshot = NULL, payload_hash = NULL, signed_at = NULL,
                                    submitted_at = NULL, updated_at = ? WHERE id = ?""",
            (DRAFT, ts, doc_id),
        )
        if active:
            names = ", ".join(s["signer_name"] for s in active)
            _audit(conn, doc_id, "SIGNATURES_INVALIDATED",
                   f"Returned to draft — {len(active)} signature(s) invalidated", user,
                   f"Invalidated: {names}. Previous fingerprint {short_hash(doc['payload_hash'])}. "
                   "Everyone must sign again.")
        else:
            _audit(conn, doc_id, "REOPENED", "Returned to draft for editing", user,
                   f"No signatures existed. Previous fingerprint {short_hash(doc['payload_hash'])}.")
    return len(active)


def cancel_document(conn: sqlite3.Connection, user: sqlite3.Row, doc_id: int, reason: str) -> None:
    _require_operator(user, "cancel handover documents")
    doc = _get_doc(conn, doc_id)
    if doc["status"] not in ACTIVE_STATUSES:
        raise WorkflowError(409, "INVALID_STATE", "Released or cancelled documents cannot be cancelled.")
    reason = (reason or "").strip()
    if not reason:
        raise WorkflowError(422, "REASON_REQUIRED", "Give a reason for cancelling.")
    ts = now()
    with conn:
        conn.execute(
            """UPDATE documents SET status = ?, cancelled_at = ?, cancelled_by = ?, cancel_reason = ?, updated_at = ?
                WHERE id = ?""",
            (CANCELLED, ts, user["id"], reason, ts, doc_id),
        )
        _audit(conn, doc_id, "CANCELLED", "Document cancelled", user, reason)


# --------------------------------------------------------------------------- signing

def _active_signatures(conn: sqlite3.Connection, doc_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM document_signatures WHERE document_id = ? AND invalidated_at IS NULL ORDER BY signing_order",
        (doc_id,),
    ).fetchall()


def _signers_with_state(conn: sqlite3.Connection, doc_id: int) -> list[dict]:
    required = conn.execute(
        """SELECT rs.*, u.full_name, u.title FROM required_signatures rs JOIN users u ON u.id = rs.signer_user_id
            WHERE rs.document_id = ? ORDER BY rs.signing_order""",
        (doc_id,),
    ).fetchall()
    by_order = {s["signing_order"]: s for s in _active_signatures(conn, doc_id)}
    result = []
    next_found = False
    for r in required:
        sig = by_order.get(r["signing_order"])
        if sig is not None and sig["signer_user_id"] == r["signer_user_id"]:
            state = "SIGNED"
        elif not next_found:
            state, next_found = "NEXT", True
        else:
            state = "PENDING"
        result.append({"required": r, "signature": sig if state == "SIGNED" else None, "state": state})
    return result


def _sign_blocker(doc: sqlite3.Row, signers: list[dict], user: sqlite3.Row) -> WorkflowError | None:
    status = doc["status"]
    if status == DRAFT:
        return WorkflowError(409, "INVALID_STATE", "The document has not been sent for signatures yet.")
    if status in (SIGNED, RELEASED):
        return WorkflowError(409, "INVALID_STATE", "All required signatures are already complete.")
    if status == CANCELLED:
        return WorkflowError(409, "INVALID_STATE", "The document has been cancelled.")
    mine = [s for s in signers if s["required"]["signer_user_id"] == user["id"]]
    if not mine:
        return WorkflowError(403, "NOT_A_SIGNER", "You are not a required signer on this document.")
    step = mine[0]
    if step["state"] == "SIGNED":
        return WorkflowError(409, "ALREADY_SIGNED", "You have already signed this document.")
    if step["state"] == "PENDING":
        nxt = next(s for s in signers if s["state"] == "NEXT")["required"]
        return WorkflowError(
            409,
            "OUT_OF_ORDER",
            f"Waiting for {nxt['full_name']} ({STEP_LABELS[nxt['signer_role']]}) to sign first. "
            f"Your signature is step {step['required']['signing_order']} of {len(signers)}.",
        )
    return None


def _check_integrity(conn: sqlite3.Connection, doc: sqlite3.Row) -> None:
    if not doc["payload_hash"] or fingerprint(build_snapshot(conn, doc["id"])) != doc["payload_hash"]:
        raise WorkflowError(
            409,
            "INTEGRITY_ERROR",
            "Document content no longer matches its fingerprint. It must be reopened and signed again.",
        )


def sign_document(
    conn: sqlite3.Connection, user: sqlite3.Row, doc_id: int, pin: str, presented_hash: str
) -> dict:
    doc = _get_doc(conn, doc_id)
    signers = _signers_with_state(conn, doc_id)
    blocker = _sign_blocker(doc, signers, user)
    if blocker:
        raise blocker
    if not verify_pin(pin or "", user["pin_hash"]):
        raise WorkflowError(422, "INVALID_PIN", "Incorrect signing PIN. The document was not signed.")
    _check_integrity(conn, doc)
    if (presented_hash or "").lower() != doc["payload_hash"]:
        raise WorkflowError(
            409,
            "HASH_MISMATCH",
            "The document changed after you opened it. Review the current version and sign again.",
        )

    step = next(s for s in signers if s["required"]["signer_user_id"] == user["id"])["required"]
    ts = now()
    with conn:
        try:
            conn.execute(
                """INSERT INTO document_signatures (document_id, document_revision, signing_order, signer_user_id,
                                                   signer_name, signer_role, signer_title, signed_at,
                                                   document_hash, method)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'INTERNAL_PIN')""",
                (
                    doc_id, doc["revision"], step["signing_order"], user["id"], user["full_name"],
                    step["signer_role"], user["title"], ts, doc["payload_hash"],
                ),
            )
        except sqlite3.IntegrityError:
            raise WorkflowError(409, "ALREADY_SIGNED", "This signature has already been recorded.")
        _audit(conn, doc_id, "SIGNED", f"Signed by {user['full_name']}", user,
               f"{STEP_LABELS[step['signer_role']]} · step {step['signing_order']} of {len(signers)} · "
               f"fingerprint {short_hash(doc['payload_hash'])}")
        signed_count = len(_active_signatures(conn, doc_id))
        if signed_count == len(signers):
            conn.execute(
                "UPDATE documents SET status = ?, signed_at = ?, updated_at = ? WHERE id = ?",
                (SIGNED, ts, ts, doc_id),
            )
            _audit(conn, doc_id, "FULLY_SIGNED",
                   f"All required signatures complete ({signed_count} / {len(signers)})",
                   detail="Equipment can now be released by the Warehouse Operator.")
        else:
            conn.execute("UPDATE documents SET updated_at = ? WHERE id = ?", (ts, doc_id))
    return {"signed_count": signed_count, "required_count": len(signers)}


# --------------------------------------------------------------------------- release

def _release_blocker(conn: sqlite3.Connection, doc: sqlite3.Row, user: sqlite3.Row) -> WorkflowError | None:
    signed = len(_active_signatures(conn, doc["id"]))
    total = conn.execute(
        "SELECT COUNT(*) FROM required_signatures WHERE document_id = ?", (doc["id"],)
    ).fetchone()[0]
    status = doc["status"]
    if status == RELEASED:
        return WorkflowError(409, "INVALID_STATE", "The equipment has already been released.")
    if status == CANCELLED:
        return WorkflowError(409, "INVALID_STATE", "The document has been cancelled.")
    if status == DRAFT:
        return WorkflowError(
            409, "SIGNATURES_INCOMPLETE",
            f"The document has not been sent for signatures yet ({signed} / {total}).",
        )
    if status != SIGNED or signed < total:
        return WorkflowError(
            409, "SIGNATURES_INCOMPLETE",
            f"Release is locked until all required signatures are complete — currently {signed} / {total}.",
        )
    if user["role"] != "WAREHOUSE_OPERATOR":
        return WorkflowError(403, "NOT_PERMITTED", "Only the Warehouse Operator can release equipment.")
    return None


def release_document(conn: sqlite3.Connection, user: sqlite3.Row, doc_id: int) -> None:
    doc = _get_doc(conn, doc_id)
    blocker = _release_blocker(conn, doc, user)
    if blocker:
        raise blocker
    _check_integrity(conn, doc)
    if any(s["document_hash"] != doc["payload_hash"] for s in _active_signatures(conn, doc_id)):
        raise WorkflowError(409, "INTEGRITY_ERROR", "A signature does not match the current document fingerprint.")

    items = conn.execute(
        """SELECT di.asset_code, e.id, e.status FROM document_items di JOIN equipment e ON e.id = di.equipment_id
            WHERE di.document_id = ? ORDER BY di.line_no""",
        (doc_id,),
    ).fetchall()
    for item in items:
        if item["status"] != "IN_STOCK":
            raise WorkflowError(409, "EQUIPMENT_UNAVAILABLE", f"{item['asset_code']} is not in stock.")
    recipient = get_user(conn, doc["recipient_user_id"])
    ts = now()
    with conn:
        for item in items:
            conn.execute(
                "UPDATE equipment SET status = 'ISSUED', holder_user_id = ?, issued_document_id = ? WHERE id = ?",
                (recipient["id"], doc_id, item["id"]),
            )
        conn.execute(
            "UPDATE documents SET status = ?, released_at = ?, released_by = ?, updated_at = ? WHERE id = ?",
            (RELEASED, ts, user["id"], ts, doc_id),
        )
        _audit(conn, doc_id, "RELEASED", f"Equipment released to {recipient['full_name']}", user,
               ", ".join(i["asset_code"] for i in items) + " · document is now read-only")


# --------------------------------------------------------------------------- read models

def _signature_dict(s: sqlite3.Row) -> dict:
    return {
        "id": s["id"],
        "signing_order": s["signing_order"],
        "signer_user_id": s["signer_user_id"],
        "signer_name": s["signer_name"],
        "signer_role": s["signer_role"],
        "signer_role_label": STEP_LABELS[s["signer_role"]],
        "signer_title": s["signer_title"],
        "signed_at": s["signed_at"],
        "document_hash": s["document_hash"],
        "document_revision": s["document_revision"],
        "method": s["method"],
        "invalidated_at": s["invalidated_at"],
        "invalidation_reason": s["invalidation_reason"],
    }


def document_detail(conn: sqlite3.Connection, doc_id: int, viewer: sqlite3.Row) -> dict:
    doc = _get_doc(conn, doc_id)
    recipient = get_user(conn, doc["recipient_user_id"])
    department = conn.execute("SELECT * FROM departments WHERE code = ?", (doc["department_code"],)).fetchone()
    items = conn.execute(
        """SELECT di.*, e.type_name, e.power FROM document_items di JOIN equipment e ON e.id = di.equipment_id
            WHERE di.document_id = ? ORDER BY di.line_no""",
        (doc_id,),
    ).fetchall()
    signers = _signers_with_state(conn, doc_id)
    signed_count = sum(1 for s in signers if s["state"] == "SIGNED")
    invalidated = conn.execute(
        """SELECT * FROM document_signatures WHERE document_id = ? AND invalidated_at IS NOT NULL
            ORDER BY signed_at""",
        (doc_id,),
    ).fetchall()
    events = conn.execute(
        "SELECT * FROM audit_events WHERE document_id = ? ORDER BY occurred_at, id", (doc_id,)
    ).fetchall()

    recomputed = fingerprint(build_snapshot(conn, doc_id)) if doc["payload_hash"] else None
    if not doc["payload_hash"]:
        integrity = "NOT_SUBMITTED"
    elif recomputed == doc["payload_hash"]:
        integrity = "VERIFIED"
    else:
        integrity = "MISMATCH"

    is_operator = viewer["role"] == "WAREHOUSE_OPERATOR"
    sign_blocker = _sign_blocker(doc, signers, viewer)
    release_blocker = _release_blocker(conn, doc, viewer)
    my_step = next((s for s in signers if s["required"]["signer_user_id"] == viewer["id"]), None)
    next_step = next((s for s in signers if s["state"] == "NEXT"), None)

    return {
        "id": doc["id"],
        "document_number": doc["document_number"],
        "doc_type": doc["doc_type"],
        "type_label": DOC_TYPE_LABEL,
        "type_label_az": DOC_TYPE_LABEL_AZ,
        "status": doc["status"],
        "revision": doc["revision"],
        "recipient": public_user(recipient),
        "department": {"code": department["code"], "name": department["name"]},
        "purpose": doc["purpose"],
        "issue_date": doc["issue_date"],
        "expected_return_date": doc["expected_return_date"],
        "notes": doc["notes"],
        "created_by": public_user(get_user(conn, doc["created_by"])),
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
        "submitted_at": doc["submitted_at"],
        "signed_at": doc["signed_at"],
        "released_at": doc["released_at"],
        "released_by": public_user(get_user(conn, doc["released_by"])) if doc["released_by"] else None,
        "cancelled_at": doc["cancelled_at"],
        "cancelled_by": public_user(get_user(conn, doc["cancelled_by"])) if doc["cancelled_by"] else None,
        "cancel_reason": doc["cancel_reason"],
        "payload_hash": doc["payload_hash"],
        "payload_snapshot": doc["payload_snapshot"],
        "integrity": integrity,
        "items": [
            {
                "line_no": i["line_no"],
                "asset_code": i["asset_code"],
                "category": i["category"],
                "description": i["description"],
                "type_name": i["type_name"],
                "power": i["power"],
            }
            for i in items
        ],
        "signers": [
            {
                "signing_order": s["required"]["signing_order"],
                "role": s["required"]["signer_role"],
                "role_label": STEP_LABELS[s["required"]["signer_role"]],
                "user": {
                    "id": s["required"]["signer_user_id"],
                    "full_name": s["required"]["full_name"],
                    "title": s["required"]["title"],
                },
                "state": s["state"],
                "signature": _signature_dict(s["signature"]) if s["signature"] else None,
            }
            for s in signers
        ],
        "signed_count": signed_count,
        "required_count": len(signers),
        "invalidated_signatures": [_signature_dict(s) for s in invalidated],
        "events": [
            {
                "id": e["id"],
                "event_type": e["event_type"],
                "occurred_at": e["occurred_at"],
                "description": e["description"],
                "actor_name": e["actor_name"],
                "actor_title": e["actor_title"],
                "detail": e["detail"],
            }
            for e in events
        ],
        "actions": {
            "can_edit": is_operator and doc["status"] == DRAFT,
            "can_submit": is_operator and doc["status"] == DRAFT,
            "can_reopen": is_operator and doc["status"] in (WAITING, SIGNED),
            "reopen_invalidates": signed_count,
            "can_cancel": is_operator and doc["status"] in ACTIVE_STATUSES,
            "is_signer": my_step is not None,
            "my_step_state": my_step["state"] if my_step else None,
            "can_sign": sign_blocker is None,
            "sign_blocked_reason": sign_blocker.message if sign_blocker else None,
            "can_release": release_blocker is None,
            "release_blocked_reason": release_blocker.message if release_blocker else None,
            "next_signer": (
                {
                    "user_id": next_step["required"]["signer_user_id"],
                    "full_name": next_step["required"]["full_name"],
                    "role_label": STEP_LABELS[next_step["required"]["signer_role"]],
                }
                if next_step and doc["status"] == WAITING
                else None
            ),
        },
    }


def list_documents(conn: sqlite3.Connection, viewer: sqlite3.Row) -> list[dict]:
    docs = conn.execute(
        """SELECT d.*, u.full_name AS recipient_name, u.title AS recipient_title, dep.name AS department_name
             FROM documents d
             JOIN users u ON u.id = d.recipient_user_id
             JOIN departments dep ON dep.code = d.department_code
            ORDER BY d.created_at DESC, d.id DESC"""
    ).fetchall()
    result = []
    for d in docs:
        signers = _signers_with_state(conn, d["id"])
        signed_count = sum(1 for s in signers if s["state"] == "SIGNED")
        nxt = next((s for s in signers if s["state"] == "NEXT"), None) if d["status"] == WAITING else None
        result.append(
            {
                "id": d["id"],
                "document_number": d["document_number"],
                "status": d["status"],
                "recipient_name": d["recipient_name"],
                "recipient_title": d["recipient_title"],
                "department_code": d["department_code"],
                "department_name": d["department_name"],
                "purpose": d["purpose"],
                "asset_codes": _item_codes(conn, d["id"]),
                "signed_count": signed_count,
                "required_count": len(signers),
                "next_signer_name": nxt["required"]["full_name"] if nxt else None,
                "next_signer_role": STEP_LABELS[nxt["required"]["signer_role"]] if nxt else None,
                "awaiting_me": bool(nxt and nxt["required"]["signer_user_id"] == viewer["id"]),
                "created_at": d["created_at"],
                "updated_at": d["updated_at"],
                "issue_date": d["issue_date"],
                "released_at": d["released_at"],
            }
        )
    return result
