"""Demo data: users, equipment and five documents at different workflow stages.

Run `python -m app.seed` to reset the database to this state.
Demo history is created through the real workflow functions (so hashes and
signatures are genuine), only back-dated with `frozen_time`.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from . import services as svc
from .db import connect, drop_all, init_schema
from .security import hash_pin

BAKU = timezone(timedelta(hours=4))

DEMO_USERS = [
    # id, full name, role, title, department, demo PIN
    (1, "Leyla Aliyeva", "HR_EMPLOYEE", "HR Employee", "HR", "1111"),
    (2, "Kamran Mammadov", "HR_MANAGER", "HR Manager", "HR", "2222"),
    (3, "Rashad Hasanov", "WAREHOUSE_OPERATOR", "Warehouse Operator", "WH", "3333"),
]
DEMO_PINS = {u[0]: u[5] for u in DEMO_USERS}

DEMO_EQUIPMENT = [
    # asset code, category, type, power, location
    ("FL110", "PRIBOR", "Flüoresan", "1000 W", "Anbar A · Rəf 2"),
    ("FL114", "PRIBOR", "Flüoresan", "1000 W", "Anbar A · Rəf 2"),
    ("FL117", "PRIBOR", "Flüoresan", "1000 W", "Anbar A · Rəf 2"),
    ("SPL042", "PRIBOR", "SPL", "2000 W", "Anbar A · Rəf 4"),
    ("SPL047", "PRIBOR", "SPL", "2000 W", "Anbar A · Rəf 4"),
    ("SPL051", "PRIBOR", "SPL", "2000 W", "Anbar A · Rəf 4"),
    ("DIR018", "PRIBOR", "İstiqamətli", "650 W", "Anbar A · Rəf 5"),
    ("DIR021", "PRIBOR", "İstiqamətli", "650 W", "Anbar A · Rəf 5"),
    ("DIR024", "PRIBOR", "İstiqamətli", "650 W", "Anbar A · Rəf 5"),
    ("FRN009", "PRIBOR", "Fresnel", "2000 W", "Anbar B · Rəf 1"),
    ("LED031", "PRIBOR", "LED panel", "200 W", "Anbar B · Rəf 3"),
    ("LID000312", "LAMP", "HPL-575", "1000 W", "Anbar B · Lampa şkafı"),
    ("LID000318", "LAMP", "HPL-575", "1000 W", "Anbar B · Lampa şkafı"),
    ("LID000327", "LAMP", "HMI-1200", "1200 W", "Anbar B · Lampa şkafı"),
    ("LID000329", "LAMP", "HPL-575", "1000 W", "Anbar B · Lampa şkafı"),
    ("LID000341", "LAMP", "CP89", "650 W", "Anbar B · Lampa şkafı"),
]


def _at(days_ago: int, hh: int, mm: int, plus_minutes: int = 0) -> datetime:
    today = datetime.now(BAKU).replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=days_ago) + timedelta(hours=hh, minutes=mm + plus_minutes)


def seed_reference_data(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("INSERT INTO departments (code, name, manager_user_id) VALUES ('HR', 'Human Resources', 2)")
        conn.execute("INSERT INTO departments (code, name, manager_user_id) VALUES ('WH', 'Warehouse', 3)")
        for uid, name, role, title, dept, pin in DEMO_USERS:
            conn.execute(
                "INSERT INTO users (id, full_name, role, title, department_code, pin_hash) VALUES (?, ?, ?, ?, ?, ?)",
                (uid, name, role, title, dept, hash_pin(pin)),
            )
        for code, category, type_name, power, location in DEMO_EQUIPMENT:
            conn.execute(
                "INSERT INTO equipment (asset_code, category, type_name, power, location) VALUES (?, ?, ?, ?, ?)",
                (code, category, type_name, power, location),
            )


def _sign(conn: sqlite3.Connection, doc_id: int, user_id: int, when: datetime) -> None:
    user = svc.get_user(conn, user_id)
    doc_hash = conn.execute("SELECT payload_hash FROM documents WHERE id = ?", (doc_id,)).fetchone()[0]
    with svc.frozen_time(when):
        svc.sign_document(conn, user, doc_id, DEMO_PINS[user_id], doc_hash)


def seed_documents(conn: sqlite3.Connection) -> None:
    rashad = svc.get_user(conn, 3)
    first = _at(9, 10, 12)
    with conn:
        conn.execute("INSERT INTO document_sequences (year, last_value) VALUES (?, 416)", (first.year,))

    def create(when: datetime, codes: list[str], purpose: str, issue: datetime, ret_days: int, notes: str) -> int:
        with svc.frozen_time(when):
            return svc.create_document(conn, rashad, {
                "recipient_user_id": 1,
                "purpose": purpose,
                "issue_date": issue.date().isoformat(),
                "expected_return_date": (issue + timedelta(days=ret_days)).date().isoformat(),
                "notes": notes,
                "equipment_codes": codes,
            })

    def submit(doc_id: int, when: datetime) -> None:
        with svc.frozen_time(when):
            svc.submit_document(conn, rashad, doc_id)

    # ANB-…-00417 — cancelled after the recipient had signed
    d = create(first, ["DIR021", "LID000341"], "Training room lighting test for HR workshop",
               first, 3, "Request withdrawn by HR.")
    submit(d, _at(9, 10, 15))
    _sign(conn, d, 1, _at(9, 11, 2))
    with svc.frozen_time(_at(8, 9, 40)):
        svc.cancel_document(conn, rashad, d, "Workshop postponed — HR withdrew the request.")

    # ANB-…-00418 — fully signed and released (3 / 3)
    d = create(_at(6, 9, 3), ["DIR018", "SPL047", "LID000318"],
               "Corporate interview recording — HR studio corner", _at(6, 9, 0), 14,
               "Return to Anbar A after the recording block. Lamp LID000318 checked before issue.")
    submit(d, _at(6, 9, 5))
    _sign(conn, d, 1, _at(6, 9, 14))
    _sign(conn, d, 2, _at(6, 9, 18))
    _sign(conn, d, 3, _at(6, 9, 23))
    with svc.frozen_time(_at(6, 9, 24)):
        svc.release_document(conn, rashad, d)

    # ANB-…-00419 — 1 / 3, waiting for the HR Manager
    d = create(_at(2, 14, 20), ["FL114", "LED031"], "Onboarding video shoot — new employee orientation",
               _at(0, 0, 0), 5, "")
    submit(d, _at(2, 14, 23))
    _sign(conn, d, 1, _at(2, 15, 1))

    # ANB-…-00420 — draft, not yet sent
    create(_at(1, 11, 30), ["FRN009", "LID000327"], "Employer branding photo session",
           _at(-2, 0, 0), 2, "Photographer arrives 10:00. Confirm power supply in meeting room 3.")

    # ANB-…-00421 — 2 / 3, waiting for the Warehouse Operator
    d = create(_at(1, 15, 3), ["SPL051", "DIR024", "LID000329"],
               "HR town-hall meeting — conference hall lighting", _at(0, 0, 0), 7,
               "Set up in the main conference hall. Spare lamp included.")
    submit(d, _at(1, 15, 5))
    _sign(conn, d, 1, _at(1, 15, 14))
    _sign(conn, d, 2, _at(1, 15, 18))


def reset_database(conn: sqlite3.Connection, with_documents: bool = True) -> None:
    drop_all(conn)
    init_schema(conn)
    seed_reference_data(conn)
    if with_documents:
        seed_documents(conn)


def ensure_database() -> None:
    conn = connect()
    try:
        init_schema(conn)
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            seed_reference_data(conn)
            seed_documents(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    c = connect()
    reset_database(c)
    c.close()
    print("Demo database reset.")
