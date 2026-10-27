"""FastAPI application: thin HTTP layer over `services`."""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Iterator

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import services as svc
from .db import connect
from .seed import ensure_database, reset_database

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_database()
    yield


app = FastAPI(title="Xezer TV — e-signature prototype", lifespan=lifespan)


@app.exception_handler(svc.WorkflowError)
async def workflow_error_handler(_: Request, exc: svc.WorkflowError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "code": exc.code})


def get_conn() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def current_user(
    authorization: str | None = Header(default=None), conn: sqlite3.Connection = Depends(get_conn)
) -> sqlite3.Row:
    token = (authorization or "").removeprefix("Bearer ").strip()
    user = svc.user_for_token(conn, token) if token else None
    if user is None:
        raise svc.WorkflowError(401, "NOT_AUTHENTICATED", "Choose a demo user to continue.")
    return user


class LoginIn(BaseModel):
    user_id: int


class DocumentIn(BaseModel):
    recipient_user_id: int
    purpose: str = Field(max_length=500)
    issue_date: str
    expected_return_date: str
    notes: str = Field(default="", max_length=2000)
    equipment_codes: list[str]


class SignIn(BaseModel):
    # The PIN is only ever compared against its stored hash; it is never logged or stored.
    pin: str = Field(min_length=1, max_length=32)
    document_hash: str


class ReopenIn(BaseModel):
    confirm_invalidate: bool = False


class CancelIn(BaseModel):
    reason: str = ""


# --------------------------------------------------------------------------- auth

@app.get("/api/users")
def users(conn: sqlite3.Connection = Depends(get_conn)) -> list[dict]:
    return svc.list_users(conn)


@app.post("/api/auth/login")
def login(body: LoginIn, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    token = svc.login(conn, body.user_id)
    return {"token": token, "user": svc.public_user(svc.get_user(conn, body.user_id))}


@app.get("/api/me")
def me(user: sqlite3.Row = Depends(current_user)) -> dict:
    return svc.public_user(user)


# --------------------------------------------------------------------------- reference data

@app.get("/api/equipment")
def equipment(
    for_document_id: int | None = None,
    _: sqlite3.Row = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[dict]:
    return svc.list_equipment(conn, for_document_id)


@app.get("/api/recipients")
def recipients(_: sqlite3.Row = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> list[dict]:
    rows = conn.execute(
        """SELECT u.*, d.name AS department_name FROM users u JOIN departments d ON d.code = u.department_code
            WHERE u.role = 'HR_EMPLOYEE' ORDER BY u.full_name"""
    ).fetchall()
    return [{**svc.public_user(r), "department_name": r["department_name"]} for r in rows]


# --------------------------------------------------------------------------- documents

@app.get("/api/documents")
def documents(user: sqlite3.Row = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> list[dict]:
    return svc.list_documents(conn, user)


@app.post("/api/documents", status_code=201)
def create_document(
    body: DocumentIn, user: sqlite3.Row = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    doc_id = svc.create_document(conn, user, body.model_dump())
    return svc.document_detail(conn, doc_id, user)


@app.get("/api/documents/{doc_id}")
def document(doc_id: int, user: sqlite3.Row = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.document_detail(conn, doc_id, user)


@app.put("/api/documents/{doc_id}")
def update_document(
    doc_id: int,
    body: DocumentIn,
    user: sqlite3.Row = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    svc.update_document(conn, user, doc_id, body.model_dump())
    return svc.document_detail(conn, doc_id, user)


@app.post("/api/documents/{doc_id}/submit")
def submit(doc_id: int, user: sqlite3.Row = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    svc.submit_document(conn, user, doc_id)
    return svc.document_detail(conn, doc_id, user)


@app.post("/api/documents/{doc_id}/sign")
def sign(
    doc_id: int, body: SignIn, user: sqlite3.Row = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    svc.sign_document(conn, user, doc_id, body.pin, body.document_hash)
    return svc.document_detail(conn, doc_id, user)


@app.post("/api/documents/{doc_id}/reopen")
def reopen(
    doc_id: int, body: ReopenIn, user: sqlite3.Row = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    svc.reopen_document(conn, user, doc_id, body.confirm_invalidate)
    return svc.document_detail(conn, doc_id, user)


@app.post("/api/documents/{doc_id}/release")
def release(doc_id: int, user: sqlite3.Row = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    svc.release_document(conn, user, doc_id)
    return svc.document_detail(conn, doc_id, user)


@app.post("/api/documents/{doc_id}/cancel")
def cancel(
    doc_id: int, body: CancelIn, user: sqlite3.Row = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    svc.cancel_document(conn, user, doc_id, body.reason)
    return svc.document_detail(conn, doc_id, user)


# --------------------------------------------------------------------------- demo

@app.post("/api/demo/reset")
def demo_reset(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    """Restore the seeded demo state (prototype convenience — not for production)."""
    reset_database(conn)
    return {"ok": True}


# Serve the built frontend (npm run build) from the same origin, if present.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
