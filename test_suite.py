import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import (
    app,
    db,
    round_half_up,
    compute_late_minutes,
    compute_overtime_minutes,
    compute_work_hours,
    compute_half_day,
    get_attendance_date_for_punch_in,
    create_indexes,
)

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_indexes():
    create_indexes()

def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

def test_rounding_half_up():
    assert round_half_up(4.495, 2) == 4.50
    assert round_half_up(4.494, 2) == 4.49
    assert round_half_up(4.4950, 2) == 4.50
    assert round_half_up(0.12345, 4) == 0.1235
    assert round_half_up(0.12344, 4) == 0.1234
    assert round_half_up(None, 2) is None

def test_r2_late_minutes_boundaries():
    # Shift 09:30: 09:40:00 -> 0; 09:40:01 -> 10; 10:15:59 -> 45
    # 2026-07-06 09:30 IST is 04:00 UTC
    # 09:40:00 IST is 04:10:00 UTC
    # 2026-07-06 04:10:00 UTC = 1783311000000 ms
    # Let's compute epoch ms for 09:40:00 IST
    dt_940 = datetime(2026, 7, 6, 9, 40, 0, tzinfo=timezone.utc).timestamp() # wait, timezone is IST (+5:30)
    # Using timestamp:
    from app.main import IST
    ms_940_00 = int(datetime(2026, 7, 6, 9, 40, 0, tzinfo=IST).timestamp() * 1000)
    ms_940_01 = int(datetime(2026, 7, 6, 9, 40, 1, tzinfo=IST).timestamp() * 1000)
    ms_1015_59 = int(datetime(2026, 7, 6, 10, 15, 59, tzinfo=IST).timestamp() * 1000)

    assert compute_late_minutes(ms_940_00, "09:30", "2026-07-06") == 0
    assert compute_late_minutes(ms_940_01, "09:30", "2026-07-06") == 10
    assert compute_late_minutes(ms_1015_59, "09:30", "2026-07-06") == 45

def test_r1_overnight_shift_date_attribution():
    from app.main import IST
    # Overnight shift: 22:00 to 06:00
    # Punch in at 21:55 on 2026-07-06 belongs to 2026-07-06
    ms_2155 = int(datetime(2026, 7, 6, 21, 55, 0, tzinfo=IST).timestamp() * 1000)
    assert get_attendance_date_for_punch_in(ms_2155, "22:00", "06:00") == "2026-07-06"

    # Punch in at 05:45 on 2026-07-07 (< shift_end 06:00) belongs to shift starting 2026-07-06
    ms_0545 = int(datetime(2026, 7, 7, 5, 45, 0, tzinfo=IST).timestamp() * 1000)
    assert get_attendance_date_for_punch_in(ms_0545, "22:00", "06:00") == "2026-07-06"

def test_r3_overtime_threshold():
    from app.main import IST
    # Shift ends at 18:30.
    # Out at 18:59:59 (29 min) -> 0
    ms_1859 = int(datetime(2026, 7, 6, 18, 59, 59, tzinfo=IST).timestamp() * 1000)
    assert compute_overtime_minutes(ms_1859, "09:30", "18:30", "2026-07-06") == 0

    # Out at 19:00:00 (30 min) -> 30
    ms_1900 = int(datetime(2026, 7, 6, 19, 0, 0, tzinfo=IST).timestamp() * 1000)
    assert compute_overtime_minutes(ms_1900, "09:30", "18:30", "2026-07-06") == 30

    # Out at 19:10:00 (40 min) -> 40
    ms_1910 = int(datetime(2026, 7, 6, 19, 10, 0, tzinfo=IST).timestamp() * 1000)
    assert compute_overtime_minutes(ms_1910, "09:30", "18:30", "2026-07-06") == 40

def test_employees_crud_and_validation():
    # Unique emp_code test
    code = "EMP9991"
    db.employees.delete_one({"emp_code": code})
    payload = {
        "emp_code": code,
        "name": "Test Tester",
        "email": "test@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01"
    }
    r = client.post("/employees", json=payload)
    assert r.status_code == 201
    assert r.json()["emp_code"] == code

    # Duplicate create must return 409
    r_dup = client.post("/employees", json=payload)
    assert r_dup.status_code == 409

    # Same shift_start and shift_end must return 422
    bad_payload = dict(payload, emp_code="EMP9992", shift_end="09:30")
    r_bad = client.post("/employees", json=bad_payload)
    assert r_bad.status_code == 422

def test_punch_in_concurrency_simulation():
    # Attempt duplicate punch in on same day
    # EMP0001 already has 2026-07-06 in sample data
    from app.main import IST
    ms_in = int(datetime(2026, 7, 6, 9, 28, 0, tzinfo=IST).timestamp() * 1000)
    r = client.post("/attendance/punch-in", json={"emp_code": "EMP0001", "punched_at": ms_in})
    assert r.status_code == 409

def test_regularize_and_audit_history():
    from app.main import IST
    # Create isolated record for regularization test
    test_code = "EMP_REG_TEST"
    db.employees.update_one(
        {"emp_code": test_code},
        {"$set": {"emp_code": test_code, "name": "Reg Tester", "email": "reg@test.com", "department": "Engineering", "shift_start": "09:30", "shift_end": "18:30", "joined_on": "2026-01-01"}},
        upsert=True
    )
    db.attendance_logs.delete_many({"emp_code": test_code})

    ms_orig_in = int(datetime(2026, 7, 6, 10, 5, 0, tzinfo=IST).timestamp() * 1000)
    ms_orig_out = int(datetime(2026, 7, 6, 19, 10, 0, tzinfo=IST).timestamp() * 1000)
    client.post("/attendance/punch-in", json={"emp_code": test_code, "punched_at": ms_orig_in})
    client.post("/attendance/punch-out", json={"emp_code": test_code, "punched_at": ms_orig_out})

    # Regularize punch_in to 09:28 (was 10:05, so late_minutes drops from 35 to 0)
    ms_new_in = int(datetime(2026, 7, 6, 9, 28, 0, tzinfo=IST).timestamp() * 1000)
    payload = {
        "punch_in": ms_new_in,
        "reason": "Correcting biometric device delay",
        "regularized_by": "hr_manager"
    }
    r = client.patch(f"/attendance/{test_code}/2026-07-06", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert len(data["history"]) == 1
    latest_hist = data["history"][-1]
    assert latest_hist["by"] == "hr_manager"
    assert "punch_in" in latest_hist["changes"]
    assert "late_minutes" in latest_hist["changes"]
    assert data["late_minutes"] == 0

def test_explain_endpoints():
    endpoints = [
        ("attendance_list", {"date_from": "2026-07-01", "date_to": "2026-07-31"}),
        ("employee_monthly", {"emp_code": "EMP0001", "month": "2026-07"}),
        ("department_summary", {"month": "2026-07"}),
        ("late_leaderboard", {"month": "2026-07"}),
        ("department_trend", {"department": "Engineering", "from": "2026-07-01", "to": "2026-07-07"}),
    ]
    for ep, params in endpoints:
        r = client.get(f"/admin/explain/{ep}", params=params)
        assert r.status_code == 200, f"Explain failed for {ep}: {r.text}"
        data = r.json()
        assert data["endpoint"] == ep
        assert "explain" in data


def test_strict_epoch_millis_and_status_validation():
    # Floats or strings for punched_at must return 422
    r_float = client.post("/attendance/punch-in", json={"emp_code": "EMP0001", "punched_at": 1783312500000.5})
    assert r_float.status_code == 422

    r_str = client.post("/attendance/punch-in", json={"emp_code": "EMP0001", "punched_at": "1783312500000"})
    assert r_str.status_code == 422

    # Seconds-looking value (< 100000000000) must return 422
    r_sec = client.post("/attendance/punch-in", json={"emp_code": "EMP0001", "punched_at": 1783312500})
    assert r_sec.status_code == 422

    # Invalid status in query must return 422
    r_bad_status = client.get("/attendance", params={"status": "INVALID_STATUS"})
    assert r_bad_status.status_code == 422


def test_cors_headers():
    headers = {"Origin": "http://localhost:5173"}
    res = client.get("/health", headers=headers)
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"

