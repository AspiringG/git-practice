import os
import tempfile

# Must be set before the app modules are imported.
os.environ["ESIGN_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="esign-test-"), "test.db")
os.environ["ESIGN_PBKDF2_ITERATIONS"] = "1000"

import pytest
from fastapi.testclient import TestClient

from app.db import connect
from app.main import app
from app.seed import reset_database

LEYLA, KAMRAN, RASHAD = 1, 2, 3
PINS = {LEYLA: "1111", KAMRAN: "2222", RASHAD: "3333"}


class Api:
    def __init__(self, client: TestClient):
        self.client = client
        self.tokens = {
            uid: client.post("/api/auth/login", json={"user_id": uid}).json()["token"] for uid in PINS
        }

    def as_(self, uid):
        return {"Authorization": f"Bearer {self.tokens[uid]}"}

    def get(self, uid, path):
        return self.client.get(path, headers=self.as_(uid))

    def post(self, uid, path, body=None):
        return self.client.post(path, json=body or {}, headers=self.as_(uid))

    def put(self, uid, path, body):
        return self.client.put(path, json=body, headers=self.as_(uid))

    def create(self, codes=("FL110", "SPL042"), **overrides):
        body = {
            "recipient_user_id": LEYLA,
            "purpose": "Studio interview recording",
            "issue_date": "2026-10-27",
            "expected_return_date": "2026-11-03",
            "notes": "Return to Anbar A",
            "equipment_codes": list(codes),
            **overrides,
        }
        r = self.post(RASHAD, "/api/documents", body)
        assert r.status_code == 201, r.text
        return r.json()

    def create_submitted(self, codes=("FL110", "SPL042")):
        doc = self.create(codes)
        r = self.post(RASHAD, f"/api/documents/{doc['id']}/submit")
        assert r.status_code == 200, r.text
        return r.json()

    def sign(self, uid, doc, pin=None, doc_hash=None):
        return self.post(
            uid,
            f"/api/documents/{doc['id']}/sign",
            {"pin": pin or PINS[uid], "document_hash": doc_hash or doc["payload_hash"]},
        )

    def detail(self, doc, uid=RASHAD):
        return self.get(uid, f"/api/documents/{doc['id']}").json()


@pytest.fixture
def api():
    with TestClient(app) as client:
        conn = connect()
        reset_database(conn, with_documents=False)
        conn.close()
        yield Api(client)
