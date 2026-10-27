import re
import sqlite3

import pytest

from app import services as svc
from app.db import connect
from app.security import canonical_json, fingerprint, verify_pin

from .conftest import KAMRAN, LEYLA, PINS, RASHAD


def sign_all(api, doc, upto=3):
    for uid in [LEYLA, KAMRAN, RASHAD][:upto]:
        r = api.sign(uid, doc)
        assert r.status_code == 200, r.text
    return api.detail(doc)


# --------------------------------------------------------------------------- creation & numbering

def test_create_document(api):
    doc = api.create()
    assert doc["status"] == "DRAFT"
    assert doc["recipient"]["full_name"] == "Leyla Aliyeva"
    assert doc["department"]["code"] == "HR"
    assert [i["asset_code"] for i in doc["items"]] == ["FL110", "SPL042"]
    assert [s["role"] for s in doc["signers"]] == ["RECIPIENT", "HR_MANAGER", "WAREHOUSE_OPERATOR"]
    assert [s["user"]["id"] for s in doc["signers"]] == [LEYLA, KAMRAN, RASHAD]
    assert doc["payload_hash"] is None


def test_only_warehouse_operator_creates(api):
    r = api.post(LEYLA, "/api/documents", {
        "recipient_user_id": LEYLA, "purpose": "x", "issue_date": "2026-10-27",
        "expected_return_date": "2026-10-28", "equipment_codes": ["FL110"],
    })
    assert r.status_code == 403


def test_document_number_generation(api):
    numbers = [api.create(codes=[c])["document_number"] for c in ("FL110", "SPL042", "DIR018")]
    year = numbers[0][4:8]
    assert numbers == [f"ANB-{year}-00001", f"ANB-{year}-00002", f"ANB-{year}-00003"]
    assert all(re.fullmatch(r"ANB-\d{4}-\d{5}", n) for n in numbers)


def test_equipment_cannot_be_on_two_active_documents(api):
    api.create(codes=["FL110"])
    r = api.post(RASHAD, "/api/documents", {
        "recipient_user_id": LEYLA, "purpose": "x", "issue_date": "2026-10-27",
        "expected_return_date": "2026-10-28", "equipment_codes": ["FL110"],
    })
    assert r.status_code == 409
    assert "FL110" in r.json()["detail"]


# --------------------------------------------------------------------------- snapshot & hash

def test_snapshot_hash_is_stable_and_content_based(api):
    doc = api.create_submitted()
    conn = connect()
    snap1 = svc.build_snapshot(conn, doc["id"])
    snap2 = svc.build_snapshot(conn, doc["id"])
    conn.close()
    assert canonical_json(snap1) == canonical_json(snap2)
    assert fingerprint(snap1) == doc["payload_hash"]
    assert re.fullmatch(r"[0-9a-f]{64}", doc["payload_hash"])

    # The snapshot carries the meaningful content, not just an ID.
    for key in ("document_number", "recipient", "department", "equipment", "purpose", "issue_date",
                "expected_return_date", "notes", "required_signers"):
        assert key in snap1
    assert [e["asset_code"] for e in snap1["equipment"]] == ["FL110", "SPL042"]
    assert snap1["equipment"][0]["description"] == "Flüoresan · 1000 W"

    # Key order does not matter; content does.
    reordered = dict(reversed(list(snap1.items())))
    assert fingerprint(reordered) == fingerprint(snap1)
    assert fingerprint({**snap1, "purpose": snap1["purpose"] + "!"}) != fingerprint(snap1)


def test_unicode_normalisation_does_not_change_hash():
    composed = {"type": "Flüoresan"}       # ü as one code point
    decomposed = {"type": "Flüoresan"}    # u + combining diaeresis
    assert fingerprint(composed) == fingerprint(decomposed)


# --------------------------------------------------------------------------- signing

def test_wrong_pin_rejected(api):
    doc = api.create_submitted()
    r = api.sign(LEYLA, doc, pin="9999")
    assert r.status_code == 422
    assert r.json()["code"] == "INVALID_PIN"
    assert api.detail(doc)["signed_count"] == 0


def test_correct_pin_signs_and_records_hash(api):
    doc = api.create_submitted()
    r = api.sign(LEYLA, doc)
    assert r.status_code == 200
    detail = r.json()
    assert detail["signed_count"] == 1
    sig = detail["signers"][0]["signature"]
    assert sig["signer_name"] == "Leyla Aliyeva"
    assert sig["signer_role"] == "RECIPIENT"
    assert sig["signer_title"] == "HR Employee"
    assert sig["method"] == "INTERNAL_PIN"
    assert sig["signed_at"]
    assert sig["document_hash"] == doc["payload_hash"]


def test_wrong_user_cannot_sign(api):
    doc = api.create_submitted()
    # Kamran tries to fill Leyla's step using Leyla's PIN: he is not the next signer.
    r = api.sign(KAMRAN, doc, pin=PINS[LEYLA])
    assert r.status_code == 409
    assert r.json()["code"] == "OUT_OF_ORDER"
    # A user's own PIN must be the one presented.
    api.sign(LEYLA, doc)
    r = api.sign(KAMRAN, doc, pin=PINS[LEYLA])
    assert r.status_code == 422
    assert api.detail(doc)["signed_count"] == 1


def test_non_signer_cannot_sign(api):
    doc = api.create_submitted()
    conn = connect()
    with conn:
        conn.execute("INSERT INTO users (id, full_name, role, title, department_code, pin_hash) "
                     "VALUES (9, 'Outsider', 'HR_EMPLOYEE', 'HR Employee', 'HR', 'x')")
    conn.close()
    token = api.client.post("/api/auth/login", json={"user_id": 9}).json()["token"]
    r = api.client.post(f"/api/documents/{doc['id']}/sign",
                        json={"pin": "0000", "document_hash": doc["payload_hash"]},
                        headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert r.json()["code"] == "NOT_A_SIGNER"


def test_signature_order_enforced(api):
    doc = api.create_submitted()
    r = api.sign(RASHAD, doc)
    assert r.status_code == 409
    assert "Leyla Aliyeva" in r.json()["detail"]
    r = api.sign(KAMRAN, doc)
    assert r.status_code == 409
    detail = api.detail(doc, KAMRAN)
    assert detail["actions"]["can_sign"] is False
    assert "Waiting for Leyla Aliyeva" in detail["actions"]["sign_blocked_reason"]


def test_user_cannot_sign_twice(api):
    doc = api.create_submitted()
    assert api.sign(LEYLA, doc).status_code == 200
    r = api.sign(LEYLA, doc)
    assert r.status_code == 409
    assert r.json()["code"] == "ALREADY_SIGNED"


def test_signing_stale_hash_rejected(api):
    doc = api.create_submitted()
    r = api.sign(LEYLA, doc, doc_hash="0" * 64)
    assert r.status_code == 409
    assert r.json()["code"] == "HASH_MISMATCH"


def test_cannot_sign_draft(api):
    doc = api.create()
    r = api.sign(LEYLA, doc, doc_hash="x")
    assert r.status_code == 409


def test_pins_are_hashed_not_plaintext(api):
    conn = connect()
    rows = conn.execute("SELECT id, pin_hash FROM users").fetchall()
    conn.close()
    for row in rows:
        assert row["pin_hash"] != PINS[row["id"]]
        assert row["pin_hash"].startswith("pbkdf2_sha256$")
        assert verify_pin(PINS[row["id"]], row["pin_hash"])
        assert not verify_pin("0000", row["pin_hash"])


def test_api_never_exposes_pin_hashes(api):
    doc = api.create_submitted()
    for body in (api.client.get("/api/users").text, api.get(RASHAD, f"/api/documents/{doc['id']}").text):
        assert "pin_hash" not in body and "pbkdf2" not in body


# --------------------------------------------------------------------------- full flow & status

def test_full_signature_chain_marks_document_signed(api):
    doc = api.create_submitted()
    detail = sign_all(api, doc)
    assert detail["status"] == "SIGNED"
    assert detail["signed_count"] == 3
    assert all(s["signature"]["document_hash"] == doc["payload_hash"] for s in detail["signers"])
    assert detail["actions"]["can_release"] is True


# --------------------------------------------------------------------------- release gate

@pytest.mark.parametrize("signatures", [0, 1, 2])
def test_release_blocked_before_all_signatures(api, signatures):
    doc = api.create_submitted()
    sign_all(api, doc, upto=signatures)
    r = api.post(RASHAD, f"/api/documents/{doc['id']}/release")
    assert r.status_code == 409
    assert r.json()["code"] == "SIGNATURES_INCOMPLETE"
    assert f"{signatures} / 3" in r.json()["detail"]
    detail = api.detail(doc)
    assert detail["status"] == "WAITING_FOR_SIGNATURES"
    assert detail["actions"]["can_release"] is False


def test_release_blocked_for_draft(api):
    doc = api.create()
    r = api.post(RASHAD, f"/api/documents/{doc['id']}/release")
    assert r.status_code == 409


def test_release_allowed_at_three_of_three(api):
    doc = api.create_submitted()
    sign_all(api, doc)
    r = api.post(RASHAD, f"/api/documents/{doc['id']}/release")
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["status"] == "RELEASED"
    assert detail["released_at"]
    assert detail["released_by"]["full_name"] == "Rashad Hasanov"
    equipment = {e["asset_code"]: e for e in api.get(RASHAD, "/api/equipment").json()}
    assert equipment["FL110"]["availability"] == "ISSUED"
    assert equipment["FL110"]["holder_name"] == "Leyla Aliyeva"
    # Released documents are read-only.
    assert api.post(RASHAD, f"/api/documents/{doc['id']}/release").status_code == 409
    assert api.post(RASHAD, f"/api/documents/{doc['id']}/reopen", {"confirm_invalidate": True}).status_code == 409
    assert api.post(RASHAD, f"/api/documents/{doc['id']}/cancel", {"reason": "x"}).status_code == 409


def test_only_warehouse_operator_can_release(api):
    doc = api.create_submitted()
    sign_all(api, doc)
    r = api.post(LEYLA, f"/api/documents/{doc['id']}/release")
    assert r.status_code == 403


# --------------------------------------------------------------------------- modification invalidates signatures

def test_locked_document_cannot_be_edited_silently(api):
    doc = api.create_submitted()
    api.sign(LEYLA, doc)
    body = {
        "recipient_user_id": LEYLA, "purpose": "Changed purpose", "issue_date": "2026-10-27",
        "expected_return_date": "2026-11-03", "notes": "", "equipment_codes": ["FL110"],
    }
    r = api.put(RASHAD, f"/api/documents/{doc['id']}", body)
    assert r.status_code == 409
    assert r.json()["code"] == "DOCUMENT_LOCKED"
    # Reopening without explicit confirmation is refused.
    r = api.post(RASHAD, f"/api/documents/{doc['id']}/reopen", {"confirm_invalidate": False})
    assert r.status_code == 409
    assert r.json()["code"] == "CONFIRMATION_REQUIRED"
    assert api.detail(doc)["signed_count"] == 1


def test_content_modification_invalidates_signatures(api):
    doc = api.create_submitted()
    sign_all(api, doc, upto=2)
    old_hash = doc["payload_hash"]

    r = api.post(RASHAD, f"/api/documents/{doc['id']}/reopen", {"confirm_invalidate": True})
    assert r.status_code == 200
    reopened = r.json()
    assert reopened["status"] == "DRAFT"
    assert reopened["signed_count"] == 0
    assert len(reopened["invalidated_signatures"]) == 2
    assert all(s["document_hash"] == old_hash for s in reopened["invalidated_signatures"])

    body = {
        "recipient_user_id": LEYLA, "purpose": "Changed purpose", "issue_date": "2026-10-27",
        "expected_return_date": "2026-11-05", "notes": "", "equipment_codes": ["FL110"],
    }
    assert api.put(RASHAD, f"/api/documents/{doc['id']}", body).status_code == 200
    resubmitted = api.post(RASHAD, f"/api/documents/{doc['id']}/submit").json()
    assert resubmitted["payload_hash"] != old_hash
    assert resubmitted["revision"] == 2
    assert resubmitted["signed_count"] == 0

    # Old hash can no longer be used; everyone must sign the new version again.
    assert api.sign(LEYLA, resubmitted, doc_hash=old_hash).status_code == 409
    final = sign_all(api, resubmitted)
    assert final["status"] == "SIGNED"
    assert all(s["signature"]["document_hash"] == resubmitted["payload_hash"] for s in final["signers"])


def test_tampered_content_blocks_signing(api):
    doc = api.create_submitted()
    sign_all(api, doc, upto=2)
    conn = connect()
    with conn:
        conn.execute("UPDATE documents SET purpose = 'Silently changed' WHERE id = ?", (doc["id"],))
    conn.close()
    assert api.detail(doc)["integrity"] == "MISMATCH"
    r = api.sign(RASHAD, doc)
    assert r.status_code == 409
    assert r.json()["code"] == "INTEGRITY_ERROR"


# --------------------------------------------------------------------------- immutability

def test_completed_signatures_immutable(api):
    doc = api.create_submitted()
    sign_all(api, doc)
    conn = connect()
    try:
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            with conn:
                conn.execute("UPDATE document_signatures SET signer_name = 'Someone else'")
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            with conn:
                conn.execute("UPDATE document_signatures SET document_hash = 'abc'")
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            with conn:
                conn.execute("DELETE FROM document_signatures")
        assert conn.execute("SELECT COUNT(*) FROM document_signatures").fetchone()[0] == 3
    finally:
        conn.close()
    # There is no API route to edit or delete a signature.
    paths = {getattr(route, "path", "") for route in api.client.app.routes}
    assert not any("signature" in p for p in paths)


def test_invalidated_signature_cannot_be_revived(api):
    doc = api.create_submitted()
    api.sign(LEYLA, doc)
    api.post(RASHAD, f"/api/documents/{doc['id']}/reopen", {"confirm_invalidate": True})
    conn = connect()
    try:
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            with conn:
                conn.execute("UPDATE document_signatures SET invalidated_at = NULL")
    finally:
        conn.close()


# --------------------------------------------------------------------------- audit

def test_audit_events_generated(api):
    doc = api.create_submitted()
    sign_all(api, doc)
    api.post(RASHAD, f"/api/documents/{doc['id']}/release")
    events = api.detail(doc)["events"]
    assert [e["event_type"] for e in events] == [
        "CREATED", "SUBMITTED", "SIGNED", "SIGNED", "SIGNED", "FULLY_SIGNED", "RELEASED",
    ]
    assert events[2]["description"] == "Signed by Leyla Aliyeva"
    assert events[2]["actor_title"] == "HR Employee"
    assert events[-1]["description"] == "Equipment released to Leyla Aliyeva"
    assert "FL110" in events[-1]["detail"]

    conn = connect()
    try:
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            with conn:
                conn.execute("DELETE FROM audit_events")
    finally:
        conn.close()


def test_audit_records_invalidation(api):
    doc = api.create_submitted()
    sign_all(api, doc, upto=1)
    api.post(RASHAD, f"/api/documents/{doc['id']}/reopen", {"confirm_invalidate": True})
    last = api.detail(doc)["events"][-1]
    assert last["event_type"] == "SIGNATURES_INVALIDATED"
    assert "1 signature(s) invalidated" in last["description"]


def test_demo_seed_is_consistent(api):
    api.client.post("/api/demo/reset")
    api.__init__(api.client)
    docs = {d["document_number"]: d for d in api.get(RASHAD, "/api/documents").json()}
    statuses = sorted(d["status"] for d in docs.values())
    assert statuses == sorted(["CANCELLED", "RELEASED", "WAITING_FOR_SIGNATURES", "DRAFT", "WAITING_FOR_SIGNATURES"])
    waiting = [d for d in docs.values() if d["status"] == "WAITING_FOR_SIGNATURES"]
    assert sorted(d["signed_count"] for d in waiting) == [1, 2]
    for d in docs.values():
        assert api.get(RASHAD, f"/api/documents/{d['id']}").json()["integrity"] in ("VERIFIED", "NOT_SUBMITTED")
