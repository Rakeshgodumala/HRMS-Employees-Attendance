import concurrent.futures
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import app, db, IST, create_indexes

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup():
    create_indexes()

def test_concurrent_punch_ins():
    """
    Two simultaneous punch-ins for the same employee and date
    must produce exactly one 201 and the conflicting request must return 409.
    """
    emp_code = "EMP_RACE_1"
    db.employees.delete_one({"emp_code": emp_code})
    db.employees.insert_one({
        "emp_code": emp_code,
        "name": "Race Tester",
        "email": "race@test.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01"
    })
    db.attendance_logs.delete_many({"emp_code": emp_code})

    ms_in = int(datetime(2026, 7, 20, 9, 30, 0, tzinfo=IST).timestamp() * 1000)

    def do_punch():
        with TestClient(app) as tc:
            return tc.post("/attendance/punch-in", json={"emp_code": emp_code, "punched_at": ms_in})

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(do_punch)
        f2 = executor.submit(do_punch)
        res1 = f1.result()
        res2 = f2.result()

    statuses = [res1.status_code, res2.status_code]
    assert 201 in statuses, f"Expected 201 in statuses: {statuses}"
    assert 409 in statuses, f"Expected 409 in statuses: {statuses}"

def test_concurrent_punch_outs():
    """
    Two simultaneous punch-outs must produce exactly one 200, conflicting one 409.
    """
    emp_code = "EMP_RACE_2"
    db.employees.delete_one({"emp_code": emp_code})
    db.employees.insert_one({
        "emp_code": emp_code,
        "name": "Race Tester 2",
        "email": "race2@test.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01"
    })
    db.attendance_logs.delete_many({"emp_code": emp_code})

    ms_in = int(datetime(2026, 7, 20, 9, 30, 0, tzinfo=IST).timestamp() * 1000)
    ms_out = int(datetime(2026, 7, 20, 18, 30, 0, tzinfo=IST).timestamp() * 1000)

    # First punch in
    r_in = client.post("/attendance/punch-in", json={"emp_code": emp_code, "punched_at": ms_in})
    assert r_in.status_code == 201

    def do_punch_out():
        with TestClient(app) as tc:
            return tc.post("/attendance/punch-out", json={"emp_code": emp_code, "punched_at": ms_out})

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(do_punch_out)
        f2 = executor.submit(do_punch_out)
        res1 = f1.result()
        res2 = f2.result()

    statuses = [res1.status_code, res2.status_code]
    assert 200 in statuses, f"Expected 200 in statuses: {statuses}"
    assert 409 in statuses, f"Expected 409 in statuses: {statuses}"

def test_concurrent_regularizations_preserve_history():
    """
    Concurrent regularizations must not lose history entries ($push atomic array update).
    """
    emp_code = "EMP_RACE_3"
    db.employees.delete_one({"emp_code": emp_code})
    db.employees.insert_one({
        "emp_code": emp_code,
        "name": "Race Tester 3",
        "email": "race3@test.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01"
    })
    db.attendance_logs.delete_many({"emp_code": emp_code})

    ms_in = int(datetime(2026, 7, 21, 9, 30, 0, tzinfo=IST).timestamp() * 1000)
    client.post("/attendance/punch-in", json={"emp_code": emp_code, "punched_at": ms_in})

    ms_edit1 = int(datetime(2026, 7, 21, 9, 35, 0, tzinfo=IST).timestamp() * 1000)
    ms_edit2 = int(datetime(2026, 7, 21, 9, 40, 0, tzinfo=IST).timestamp() * 1000)

    def do_reg(ms, who):
        with TestClient(app) as tc:
            return tc.patch(f"/attendance/{emp_code}/2026-07-21", json={
                "punch_in": ms,
                "reason": f"Correction by {who}",
                "regularized_by": who
            })

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(do_reg, ms_edit1, "admin1")
        f2 = executor.submit(do_reg, ms_edit2, "admin2")
        r1 = f1.result()
        r2 = f2.result()

    doc = db.attendance_logs.find_one({"emp_code": emp_code, "date": "2026-07-21"})
    assert doc is not None
    # If both succeeded, history must have length 2
    successful_count = sum(1 for r in [r1, r2] if r.status_code == 200)
    assert len(doc.get("history", [])) == successful_count

def test_leaderboard_competition_ranking_and_cutoff_ties():
    """
    Ranks employees by total late_minutes in the month (highest first).
    Ties share ranks and the next rank is skipped (1, 2, 2, 4).
    Limit applies after ranking: return every employee whose rank <= limit.
    """
    # Create test data in attendance_logs for 2026-08
    db.attendance_logs.delete_many({"date": {"$regex": "^2026-08-"}})
    # E1: 60 mins late
    # E2: 40 mins late
    # E3: 40 mins late (tied for rank 2)
    # E4: 20 mins late (rank 4)
    # E5: 10 mins late (rank 5)
    test_emps = [
        ("EMP_L1", "Alice", "Sales", 60),
        ("EMP_L2", "Bob", "Sales", 40),
        ("EMP_L3", "Charlie", "Sales", 40),
        ("EMP_L4", "David", "Sales", 20),
        ("EMP_L5", "Eve", "Sales", 10),
    ]
    for code, name, dept, late in test_emps:
        db.employees.update_one(
            {"emp_code": code},
            {"$set": {"emp_code": code, "name": name, "department": dept, "joined_on": "2026-01-01", "shift_start": "09:30", "shift_end": "18:30"}},
            upsert=True
        )
        db.attendance_logs.insert_one({
            "emp_code": code,
            "date": "2026-08-01",
            "status": "PRESENT",
            "late_minutes": late,
            "history": []
        })

    # Test limit=2: Ranks are E1 (1), E2 (2), E3 (2). Both E2 and E3 have rank <= 2!
    # So limit=2 returns 3 items!
    r = client.get("/analytics/leaderboard/late", params={"month": "2026-08", "limit": 2})
    assert r.status_code == 200
    data = r.json()
    items = data["items"]
    assert len(items) == 3
    assert items[0]["rank"] == 1
    assert items[0]["emp_code"] == "EMP_L1"
    assert items[1]["rank"] == 2
    assert items[1]["emp_code"] == "EMP_L2"
    assert items[2]["rank"] == 2
    assert items[2]["emp_code"] == "EMP_L3"

    # Test limit=4: E1 (1), E2 (2), E3 (2), E4 (4) -> next rank after 2 is 4!
    r4 = client.get("/analytics/leaderboard/late", params={"month": "2026-08", "limit": 4})
    items4 = r4.json()["items"]
    assert len(items4) == 4
    assert items4[3]["rank"] == 4
    assert items4[3]["emp_code"] == "EMP_L4"

def test_department_summary_employees_without_logs():
    """
    R9 Headcount: employees whose joined_on <= end of month must be included
    in headcount even with zero logs.
    """
    # Create department 'Finance' with 2 employees, only 1 has attendance
    db.employees.delete_many({"department": "Finance"})
    db.attendance_logs.delete_many({"emp_code": {"$in": ["EMP_F1", "EMP_F2"]}})

    db.employees.insert_many([
        {"emp_code": "EMP_F1", "name": "Fin 1", "email": "f1@test.com", "department": "Finance", "joined_on": "2026-05-01", "shift_start": "09:30", "shift_end": "18:30"},
        {"emp_code": "EMP_F2", "name": "Fin 2", "email": "f2@test.com", "department": "Finance", "joined_on": "2026-05-15", "shift_start": "09:30", "shift_end": "18:30"},
    ])
    # EMP_F1 has 1 log in 2026-05 (Monday 2026-05-04)
    db.attendance_logs.insert_one({
        "emp_code": "EMP_F1",
        "date": "2026-05-04",
        "status": "PRESENT",
        "work_hours": 8.0,
        "late_minutes": 0,
        "half_day": False,
        "history": []
    })

    r = client.get("/analytics/departments/summary", params={"month": "2026-05", "department": "Finance"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    fin = items[0]
    assert fin["department"] == "Finance"
    assert fin["headcount"] == 2  # Both counted!
    assert fin["present_days"] == 1.0
    assert fin["avg_work_hours"] == 8.0

def test_department_trend_gap_filling_and_moving_average():
    """
    Department trend: exactly one row per calendar day, gaps filled, 7d moving average.
    """
    # Let's test with HR department
    db.employees.delete_many({"department": "HR"})
    db.employees.insert_one({
        "emp_code": "EMP_HR1",
        "name": "HR Person",
        "email": "hr@test.com",
        "department": "HR",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-06-01"
    })
    # Range 2026-06-01 to 2026-06-05 (5 days)
    # Log only on 2026-06-01
    db.attendance_logs.delete_many({"emp_code": "EMP_HR1"})
    db.attendance_logs.insert_one({
        "emp_code": "EMP_HR1",
        "date": "2026-06-01",
        "status": "PRESENT",
        "half_day": False,
        "late_minutes": 0
    })

    r = client.get("/analytics/departments/HR/trend", params={"from": "2026-06-01", "to": "2026-06-05"})
    assert r.status_code == 200
    data = r.json()
    items = data["items"]
    assert len(items) == 5
    # Day 1: 2026-06-01 is Monday (working day). Headcount 1, present 1 -> rate 1.0, mov_avg 1.0
    assert items[0]["date"] == "2026-06-01"
    assert items[0]["attendance_rate"] == 1.0
    assert items[0]["moving_avg_7d"] == 1.0

    # Day 2: 2026-06-02 is Tuesday. Present 0 -> rate 0.0, mov_avg = (1.0 + 0.0) / 2 = 0.5
    assert items[1]["date"] == "2026-06-02"
    assert items[1]["attendance_rate"] == 0.0
    assert items[1]["moving_avg_7d"] == 0.5
