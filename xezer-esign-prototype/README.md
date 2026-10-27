# Xezer TV — Warehouse e-signature prototype (e-İmza)

> **Prototype — internal electronic signature concept. Not a qualified electronic signature.**
> This is a UX / business-process proof of concept. It is **not** production security software and is
> **not** integrated with Xezer ERP in any way.

A standalone demo showing how the paper Warehouse handover (*Təhvil-təslim aktı*) can become an internal
digital signing workflow:

```
Warehouse creates handover → Recipient signs → HR Manager signs → Warehouse Operator signs
→ 3 / 3 complete → equipment released → signed document is read-only
```

## What the prototype demonstrates

| Concept | How it shows up |
|---|---|
| Document lifecycle | `DRAFT → WAITING_FOR_SIGNATURES → SIGNED → RELEASED` (or `CANCELLED`) |
| Unique numbering | `ANB-2026-00001`, `ANB-2026-00002`, … per year (the demo data starts at `00417`) |
| Immutable snapshot | On "send for signatures" all meaningful content is serialised deterministically and hashed with **SHA-256**. The fingerprint is shown on screen, in the signing dialog and on the print-out |
| Hash-bound signatures | Every signature stores the exact hash it signed. The server re-computes the hash before signing and before release, and rejects stale or tampered content |
| Signing order | Recipient → HR Manager → Warehouse Operator. Later signers see a locked button and the reason |
| PIN confirmation | Signing requires the user's own PIN (stored only as a salted PBKDF2-SHA256 hash) |
| Release gate | "Avadanlığı təhvil ver" is locked until 3 / 3, **enforced by the backend** |
| No silent edits | Once signing starts, content changes require **"Edit document and invalidate signatures"**: signatures are invalidated (kept for history), the document returns to Draft, a new fingerprint is generated and everyone signs again |
| Immutability | Signatures and audit events cannot be edited or deleted — enforced by SQLite triggers, not just the UI |
| Audit timeline | Human-readable business events (created, sent, signed by…, released) |
| Print / PDF | A4 print view; use the browser's "Save as PDF". No fake handwritten signatures |

## Architecture

```
xezer-esign-prototype/
├── backend/                FastAPI + SQLite (Python standard library sqlite3, no ORM)
│   ├── app/
│   │   ├── main.py         HTTP routes (thin layer)
│   │   ├── services.py     All workflow rules: create, submit, sign, reopen, release, cancel
│   │   ├── security.py     PIN hashing (PBKDF2), canonical JSON + SHA-256 fingerprint
│   │   ├── db.py           Schema, immutability triggers, unique indexes
│   │   └── seed.py         Demo users, equipment and documents
│   ├── tests/              pytest suite (31 tests)
│   └── data/esign.db       Created automatically on first start (git-ignored)
└── frontend/               React 18 + TypeScript + Vite (no UI framework, plain CSS)
    └── src/
        ├── pages/          Dashboard, DocumentForm, DocumentDetail, PrintView, EquipmentPage
        └── components/     Header (user switcher), SignModal, Timeline, shared UI
```

* The backend computes what the current user is allowed to do (`actions` on each document, including
  the human-readable reason a button is locked). The UI only renders that — every rule is re-checked
  when the action is called.
* In production mode (`start.sh` / `start.bat`) FastAPI also serves the built frontend, so the whole
  demo runs on **one URL: http://localhost:8000**. No cloud services, no external network calls.

### Domain model (simplified)

* `users`, `departments`, `equipment` (permanent asset codes such as `FL110`, `SPL042`, `LID000312`)
* `documents` — number, status, recipient, department, purpose, dates, notes, `revision`,
  `payload_snapshot` (canonical JSON), `payload_hash` (SHA-256), lifecycle timestamps
* `document_items` — asset code + description **copied** into the document (later master-data changes
  cannot alter a signed document)
* `required_signatures` — signer, role and order per document
* `document_signatures` — signer id/name/role/title, `signed_at`, `document_hash`, `document_revision`,
  `method = INTERNAL_PIN`, plus `invalidated_at` (the only field that may ever be set after creation)
* `audit_events` — append-only business timeline

### What exactly is hashed

On submit, this snapshot is built, serialised with sorted keys, no whitespace, UTF-8 and Unicode NFC
normalisation, then hashed with SHA-256:

```
schema, document_number, document_type, revision,
recipient {user_id, full_name, title}, department {code, name},
equipment [{line_no, asset_code, category, description}],
purpose, issue_date, expected_return_date, notes,
required_signers [{order, role, user_id, full_name, title}]
```

The full snapshot can be viewed on the document page ("Show signed snapshot").

## Installation & startup

Requirements: **Python 3.10+** and **Node.js 18+**.

### Option A — one command (recommended for the meeting)

```bash
./start.sh          # macOS / Linux
start.bat           # Windows
```

Then open **http://localhost:8000**.

### Option B — two terminals (development, hot reload)

```bash
# Terminal 1 — backend (http://127.0.0.1:8000)
cd backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Terminal 2 — frontend (http://localhost:5173, proxies /api to the backend)
cd frontend
npm install
npm run dev
```

### Option C — Docker (no Python or Node needed)

```bash
docker compose up --build        # first run builds the image (~1–2 min)
```

Open **http://localhost:8000**. Demo data is kept in the `esign-data` volume between restarts;
`docker compose down -v` deletes it and the next start re-seeds a fresh demo.

### Opening the demo on a phone or tablet

The Docker container (and `uvicorn ... --host 0.0.0.0`) accepts connections from other devices on
the same network:

1. Start the prototype on a laptop with Option C (or Option B with
   `uvicorn app.main:app --host 0.0.0.0 --port 8000` after `npm run build`).
2. Find the laptop's local IP — Windows: `ipconfig` (IPv4 address); macOS: `ipconfig getifaddr en0`.
3. On a phone connected to the **same Wi-Fi**, open `http://<laptop-ip>:8000`, e.g.
   `http://192.168.1.25:8000`. Allow the firewall prompt on the laptop if one appears.

The layout is designed for 1920×1080 / 1366×768 screens; on a phone everything works but tables
scroll horizontally.

The SQLite database is created and seeded automatically on first start.

### Reset demo data

* In the UI: user menu (top right) → **Reset demo data**
* Or from the command line: `cd backend && python -m app.seed`

### Run the tests

```bash
cd backend
pytest
```

## Demo users and PINs

| User | Role | Demo signing PIN |
|---|---|---|
| Leyla Aliyeva | HR Employee (recipient) | `1111` |
| Kamran Mammadov | HR Manager | `2222` |
| Rashad Hasanov | Warehouse Operator | `3333` |

Switch users from the menu in the top-right corner (the app starts as Rashad). Choosing a user is a
**demo-only** login; signing still requires that user's PIN.

> ⚠️ These PINs are demo credentials. Production would need real Xezer authentication and a proper
> PIN / credential policy — see below.

## Seeded documents

| Number | State | Equipment |
|---|---|---|
| ANB-2026-00417 | Cancelled (after 1 / 3) | DIR021, LID000341 |
| ANB-2026-00418 | Released, 3 / 3 | DIR018, SPL047, LID000318 |
| ANB-2026-00419 | 1 / 3 — waiting for HR Manager | FL114, LED031 |
| ANB-2026-00420 | Draft | FRN009, LID000327 |
| ANB-2026-00421 | 2 / 3 — waiting for Warehouse Operator | SPL051, DIR024, LID000329 |

`FL110`, `SPL042` and `LID000312` are left in stock for the live demo.

## Demo script (≈ 5 minutes)

1. Open the dashboard (you are **Rashad Hasanov**, Warehouse Operator). Point out the status
   categories and the "Requires your action" strip.
2. **New handover** → recipient **Leyla Aliyeva** (department fills in automatically) → purpose →
   add **FL110** and **SPL042** → **Save & send for signatures**.
   A number (`ANB-2026-00422`) and a SHA-256 fingerprint are generated; content is now locked.
3. Note that Rashad's **İmzala** button is locked with the reason "Waiting for Leyla Aliyeva…",
   and **Avadanlığı təhvil ver** is locked at 0 / 3.
4. Switch to **Leyla** (user menu, or the "Demo: switch to Leyla Aliyeva" shortcut) → **İmzala**.
   Try a wrong PIN first (e.g. `0000`) → clear error, nothing signed. Then `1111` → 1 / 3.
5. Switch to **Kamran** → **İmzala** → `2222` → 2 / 3.
6. Switch to **Rashad** → **İmzala** → `3333` → **3 / 3 complete**, status *Fully signed*.
7. **Avadanlığı təhvil ver** → confirm. Status *Released*, document is read-only, equipment register
   shows FL110 / SPL042 as issued to Leyla.
8. Walk through the final document: equipment IDs, signatures with timestamps and the fingerprint
   each one signed, the audit timeline.
9. **PDF / Print** → A4 print view → "Print / Save as PDF".
10. *(Optional — immutability)* Open **ANB-2026-00421** (2 / 3) → **Edit document and invalidate
    signatures** → the dialog lists the signatures that will be lost → confirm → change the purpose →
    send again. The new fingerprint differs, the old signatures are shown as invalidated, and everyone
    must sign again.

## Security principles implemented (prototype level)

* PINs are never stored in plaintext (salted PBKDF2-HMAC-SHA256, 210 000 iterations), never logged,
  never returned by the API, and the PIN field is cleared after every attempt.
* The backend decides who may sign: only the required signer whose turn it is, with their own PIN.
* A user cannot sign as someone else, cannot sign twice (also a unique DB index), cannot sign out of
  order, and cannot sign a document whose content no longer matches its fingerprint.
* The client must send the fingerprint it displayed; if the document changed in the meantime the
  signature is refused.
* Release is refused before all required signatures exist and match the current fingerprint.
* Completed signatures and audit events cannot be modified or deleted (SQLite triggers).
* All state-changing endpoints validate the workflow server-side.

## Limitations — what this prototype does NOT solve

Before any production integration the following decisions and work are still required:

* **Real Xezer authentication** (SSO / AD) instead of the demo user switcher
* **PIN enrollment and reset** process (who issues PINs, how they are changed or recovered)
* **Rate limiting / lockout** of repeated wrong PIN attempts
* **Session re-authentication** before signing, session expiry
* **Stronger credential policies** (PIN length, reuse, possibly a second factor)
* **Real department and user records** from HR master data (managers, deputies, absences)
* **Permissions model** (who may create, view, cancel, release; per-department visibility)
* **Document retention** rules and archival format (e.g. PDF/A with embedded fingerprint)
* **Backup** and disaster recovery
* **Legal / internal HR policy** approval of internal electronic signatures for handovers
* **Production database** (PostgreSQL) and migrations
* **Monitoring**, alerting and tamper-evident audit storage
* **Qualified electronic signature** integration (e.g. national e-signature infrastructure) **if ever
  required** — this prototype is explicitly *not* a qualified electronic signature
* Equipment return workflow, partial returns, condition reports, notifications (e-mail / ERP inbox)

The demo database, demo PINs and the "Reset demo data" endpoint exist only for presentation
purposes and must not be carried over to a production system.
