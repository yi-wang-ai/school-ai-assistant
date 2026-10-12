import os

os.environ.setdefault("SERVICE_TOKEN", "test-token")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)  # no context manager: skips startup, so no database needed
H = {"X-Service-Token": "test-token"}


def post(body):
    return client.post("/tool/calculate", json=body, headers=H)


def test_requires_service_token():
    assert client.post("/tool/calculate", json={}, headers={"X-Service-Token": "wrong"}).status_code == 401


def test_not_a_calculation_is_skipped():
    assert post({"is_calculation": "no"}).json() == {"ok": False, "skipped": True}


def test_c05_flat_strings():
    r = post({"is_calculation": "yes", "city": "广州", "start": "2026-08-30", "end": "2026-09-02",
              "nights": "2026-08-30:540;2026-08-31:540;2026-09-01:540"}).json()
    assert r["ok"] and r["result"]["total"] == 2300


def test_policy_gap_reported_not_raised():
    r = post({"is_calculation": "yes", "city": "重庆", "start": "2026-10-10", "end": "2026-10-11"})
    assert r.status_code == 200 and "policy_gap" in r.json()


def test_bad_input_reported_not_raised():
    r = post({"is_calculation": "yes", "city": "北京", "start": "2026-10-12", "end": "2026-10-10"})
    assert r.status_code == 200 and "input_error" in r.json()
