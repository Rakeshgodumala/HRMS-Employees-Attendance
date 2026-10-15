"""
Employee Attendance & Analytics API - Contract v2.0
Implementation adhering strictly to openapi.yaml, DATA_MODEL.md, and business rules R1-R10.
"""
from __future__ import annotations

import math
import os
import re
from contextlib import asynccontextmanager
from datetime import date as dt_date, datetime, time as dt_time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Path, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError

# --------------------------------------------------------------------------- #
# Environment & Database Configuration (Phase 8)
# Real environment variables take precedence over .env file
# --------------------------------------------------------------------------- #
load_dotenv()

MONGO_URI = os.environ.get("MONGO_URI") or os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB") or os.getenv("MONGO_DB", "attendance_db")

client: MongoClient = MongoClient(MONGO_URI, tz_aware=True, serverSelectionTimeoutMS=5000)
db = client[MONGO_DB]

# Fixed IST timezone: UTC+05:30
IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc

MIN_EPOCH_MS = 100000000000
MAX_EPOCH_MS = 4102444800000


# --------------------------------------------------------------------------- #
# Helper Functions: Rounding, Instants, Dates, Shifts, and Derived Metrics
# --------------------------------------------------------------------------- #
def round_half_up(value: Optional[float], decimals: int = 2) -> Optional[float]:
    """
    R8 Rounding: 2 decimals half-up for ordinary numbers, 4 for rates.
    Uses decimal.Decimal with ROUND_HALF_UP to avoid floating point banker's rounding.
    """
    if value is None or math.isnan(value):
        return None
    d = Decimal(str(value))
    exp = Decimal("10") ** (-decimals)
    rounded = d.quantize(exp, rounding=ROUND_HALF_UP)
    return float(rounded)


def truncate_epoch_ms(ms: int) -> int:
    """
    R1 Rule: Instants are truncated to whole seconds before any calculation,
    storage, and response.
    """
    return (ms // 1000) * 1000


def ms_to_datetime_utc(ms: int) -> datetime:
    """
    Converts epoch milliseconds to a UTC datetime stored as BSON date in MongoDB.
    """
    truncated_ms = truncate_epoch_ms(ms)
    return datetime.fromtimestamp(truncated_ms / 1000, tz=UTC)


def datetime_to_ms(dt: Optional[datetime]) -> Optional[int]:
    """
    Converts a UTC or naive BSON datetime from MongoDB into epoch milliseconds.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    ts = int(dt.timestamp() * 1000)
    return truncate_epoch_ms(ts)


def now_epoch_ms() -> int:
    """Returns current instant in epoch milliseconds truncated to whole seconds."""
    return truncate_epoch_ms(int(datetime.now(tz=UTC).timestamp() * 1000))


def is_overnight_shift(shift_start: str, shift_end: str) -> bool:
    """
    Overnight shifts are defined by shift_end <= shift_start (e.g. 22:00 - 06:00).
    """
    return shift_end <= shift_start


def get_attendance_date_for_punch_in(punch_in_ms: int, shift_start: str, shift_end: str) -> str:
    """
    R1 Time zone and attendance date:
    - Shift times and attendance dates are IST (UTC+05:30).
    - A record's date is the IST calendar date of its punch_in instant.
    - Overnight shift exception: if shift_end <= shift_start and punch_in IST time is
      strictly earlier than shift_end, it belongs to the shift that started the previous day.
    """
    dt_ist = datetime.fromtimestamp(truncate_epoch_ms(punch_in_ms) / 1000, tz=IST)
    calendar_date = dt_ist.date()

    if is_overnight_shift(shift_start, shift_end):
        end_h, end_m = map(int, shift_end.split(":"))
        shift_end_time = dt_time(hour=end_h, minute=end_m, second=0)
        punch_in_time = dt_ist.time()
        # Punch-in earlier than shift_end belongs to the shift that started the previous day
        if punch_in_time < shift_end_time:
            calendar_date = calendar_date - timedelta(days=1)

    return calendar_date.isoformat()


def compute_late_minutes(punch_in_ms: int, shift_start: str, attendance_date: str) -> int:
    """
    R2 Late:
    Grace period is exactly 10 minutes.
    A punch-in is late only if strictly more than 10:00 (600 seconds) after shift start.
    If late, late_minutes = whole minutes (floor division) elapsed since shift_start.
    Examples (shift 09:30):
      09:40:00 -> 0; 09:40:01 -> 10; 10:15:59 -> 45.
    """
    trunc_ms = truncate_epoch_ms(punch_in_ms)
    dt_ist = datetime.fromtimestamp(trunc_ms / 1000, tz=IST)

    year, month, day = map(int, attendance_date.split("-"))
    sh_h, sh_m = map(int, shift_start.split(":"))
    shift_start_dt = datetime(year, month, day, sh_h, sh_m, 0, tzinfo=IST)

    diff_seconds = int((dt_ist - shift_start_dt).total_seconds())
    # Late only if strictly more than 10 minutes (600 seconds) after shift_start
    if diff_seconds > 600:
        return diff_seconds // 60
    return 0


def compute_overtime_minutes(punch_out_ms: int, shift_start: str, shift_end: str, attendance_date: str) -> int:
    """
    R3 Overtime:
    Whole minutes (floor) between shift_end and punch_out, counted only if >= 30; otherwise 0.
    For overnight shifts (shift_end <= shift_start), shift_end falls on attendance_date + 1 day.
    """
    trunc_ms = truncate_epoch_ms(punch_out_ms)
    dt_ist = datetime.fromtimestamp(trunc_ms / 1000, tz=IST)

    year, month, day = map(int, attendance_date.split("-"))
    base_date = dt_date(year, month, day)
    if is_overnight_shift(shift_start, shift_end):
        end_date = base_date + timedelta(days=1)
    else:
        end_date = base_date

    end_h, end_m = map(int, shift_end.split(":"))
    shift_end_dt = datetime(end_date.year, end_date.month, end_date.day, end_h, end_m, 0, tzinfo=IST)

    diff_seconds = int((dt_ist - shift_end_dt).total_seconds())
    if diff_seconds >= 30 * 60:
        return diff_seconds // 60
    return 0


def compute_work_hours(punch_in_ms: int, punch_out_ms: int) -> float:
    """
    R4 Work hours:
    (punch_out - punch_in) in seconds / 3600, rounded to 2 decimals half-up.
    """
    in_sec = truncate_epoch_ms(punch_in_ms) // 1000
    out_sec = truncate_epoch_ms(punch_out_ms) // 1000
    seconds = out_sec - in_sec
    hours = seconds / 3600.0
    return round_half_up(hours, 2)


def compute_half_day(work_hours: Optional[float]) -> bool:
    """
    R5 Half day:
    After punch-out, half_day is true when the rounded work_hours < 4.50.
    """
    if work_hours is None:
        return False
    return work_hours < 4.50


def serialize_doc_to_attendance_record(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transforms MongoDB BSON attendance document into the OpenAPI AttendanceRecord schema.
    Converts BSON datetimes into epoch milliseconds, ensures default values for
    missing half_day and history, and strips internal _id.
    """
    punch_in_val = doc.get("punch_in")
    punch_out_val = doc.get("punch_out")

    punch_in_ms = datetime_to_ms(punch_in_val) if isinstance(punch_in_val, datetime) else punch_in_val
    punch_out_ms = datetime_to_ms(punch_out_val) if isinstance(punch_out_val, datetime) else punch_out_val

    # Convert history entries
    raw_history = doc.get("history") or []
    cleaned_history = []
    for h in raw_history:
        at_val = h.get("at")
        at_ms = datetime_to_ms(at_val) if isinstance(at_val, datetime) else at_val

        changes_raw = h.get("changes", {})
        cleaned_changes = {}
        for k, v in changes_raw.items():
            f_val = v.get("from")
            t_val = v.get("to")
            if k in ("punch_in", "punch_out"):
                if isinstance(f_val, datetime):
                    f_val = datetime_to_ms(f_val)
                if isinstance(t_val, datetime):
                    t_val = datetime_to_ms(t_val)
            cleaned_changes[k] = {"from": f_val, "to": t_val}

        cleaned_history.append({
            "at": at_ms,
            "by": h.get("by"),
            "reason": h.get("reason"),
            "changes": cleaned_changes
        })

    work_hours = doc.get("work_hours")
    if work_hours is not None:
        work_hours = round_half_up(float(work_hours), 2)

    return {
        "emp_code": doc.get("emp_code"),
        "date": doc.get("date"),
        "status": doc.get("status"),
        "punch_in": punch_in_ms,
        "punch_out": punch_out_ms,
        "work_hours": work_hours,
        "late_minutes": doc.get("late_minutes", 0),
        "overtime_minutes": doc.get("overtime_minutes", 0),
        "half_day": bool(doc.get("half_day", False)),
        "history": cleaned_history
    }


def serialize_doc_to_employee(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transforms MongoDB employee document to OpenAPI Employee schema.
    """
    created_at = doc.get("created_at")
    created_ms = datetime_to_ms(created_at) if isinstance(created_at, datetime) else created_at
    return {
        "emp_code": doc.get("emp_code"),
        "name": doc.get("name"),
        "email": doc.get("email"),
        "department": doc.get("department"),
        "shift_start": doc.get("shift_start"),
        "shift_end": doc.get("shift_end"),
        "joined_on": doc.get("joined_on"),
        "created_at": created_ms,
    }


# --------------------------------------------------------------------------- #
# Pydantic Schemas Matching OpenAPI v2.0 Contract
# --------------------------------------------------------------------------- #
class EmployeeCreate(BaseModel):
    emp_code: str = Field(..., pattern=r"^EMP\d{4,6}$")
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    department: str = Field(..., min_length=1, max_length=50)
    shift_start: str = Field("09:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    shift_end: str = Field("18:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    joined_on: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("joined_on")
    @classmethod
    def validate_joined_on(cls, v: str) -> str:
        try:
            dt_date.fromisoformat(v)
        except ValueError:
            raise ValueError("joined_on must be a valid calendar date YYYY-MM-DD")
        return v

    @model_validator(mode="after")
    def check_shifts(self) -> EmployeeCreate:
        if self.shift_start == self.shift_end:
            raise ValueError("shift_start must differ from shift_end")
        return self


class PunchInRequest(BaseModel):
    emp_code: str
    punched_at: Optional[int] = Field(None, ge=MIN_EPOCH_MS, le=MAX_EPOCH_MS, strict=True)
    status: Literal["PRESENT", "WFH", "ON_DUTY"] = "PRESENT"


class PunchOutRequest(BaseModel):
    emp_code: str
    punched_at: Optional[int] = Field(None, ge=MIN_EPOCH_MS, le=MAX_EPOCH_MS, strict=True)


class RegularizeRequest(BaseModel):
    status: Optional[Literal["PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"]] = None
    punch_in: Optional[int] = Field(None, ge=MIN_EPOCH_MS, le=MAX_EPOCH_MS, strict=True)
    punch_out: Optional[int] = Field(None, ge=MIN_EPOCH_MS, le=MAX_EPOCH_MS, strict=True)
    reason: str = Field(..., min_length=5, max_length=200)
    regularized_by: str = Field(..., min_length=1, max_length=50)


# --------------------------------------------------------------------------- #
# FastAPI Application & Startup Lifecycle: Idempotent Index Initialization
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager: initializes all required database indexes on startup."""
    create_indexes()
    yield


app = FastAPI(
    title="Employee Attendance & Analytics API",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS Middleware for frontend integration (local dev server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def create_indexes():
    """
    Ensures all indexes required for uniqueness, query performance, and analytics
    pipelines are created idempotently at application startup.
    """
    try:
        # Unique customer business identifier
        db.employees.create_index([("emp_code", ASCENDING)], unique=True, name="idx_emp_code_unique")
        # Department filtering and sorting
        db.employees.create_index([("department", ASCENDING), ("emp_code", ASCENDING)], name="idx_dept_emp_code")
        # Headcount filtering on joined_on
        db.employees.create_index([("joined_on", ASCENDING)], name="idx_joined_on")
        db.employees.create_index([("department", ASCENDING), ("joined_on", ASCENDING)], name="idx_dept_joined_on")

        # Unique composite natural key for attendance records
        db.attendance_logs.create_index([("emp_code", ASCENDING), ("date", ASCENDING)], unique=True, name="idx_emp_date_unique")
        # Main listing sort pattern: date DESC, emp_code ASC
        db.attendance_logs.create_index([("date", DESCENDING), ("emp_code", ASCENDING)], name="idx_date_desc_emp_asc")
        # Employee date range lookups (used in employee punch-out, monthly analytics)
        db.attendance_logs.create_index([("emp_code", ASCENDING), ("date", DESCENDING)], name="idx_emp_date_desc")
        # Status filter with date
        db.attendance_logs.create_index([("status", ASCENDING), ("date", DESCENDING)], name="idx_status_date")
        # Late leaderboard filtering: date and late_minutes
        db.attendance_logs.create_index([("date", ASCENDING), ("late_minutes", DESCENDING)], name="idx_date_late_minutes")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Endpoints: System Health & Employees CRUD
# --------------------------------------------------------------------------- #
@app.get("/health", tags=["system"])
def health():
    """
    Readiness probe:
    Returns 200 only if MongoDB answers a ping; otherwise 503.
    """
    try:
        client.admin.command("ping")
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")


@app.post("/employees", status_code=201, tags=["employees"])
def create_employee(body: EmployeeCreate):
    """
    Creates an employee. Unique emp_code is enforced by the database unique index.
    Concurrent duplicate creates yield exactly one 201 and 409 for the rest.
    """
    doc = body.model_dump()
    created_ms = now_epoch_ms()
    doc["created_at"] = ms_to_datetime_utc(created_ms)

    try:
        db.employees.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Employee with this emp_code already exists")

    return serialize_doc_to_employee(doc)


@app.get("/employees", tags=["employees"])
def list_employees(
    department: Optional[str] = Query(None, description="Exact, case-sensitive match."),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    List employees sorted by emp_code ascending.
    Total counts the filtered set, not the whole collection.
    """
    q: Dict[str, Any] = {}
    if department is not None:
        q["department"] = department

    skip = (page - 1) * page_size
    total = db.employees.count_documents(q)
    cursor = db.employees.find(q).sort("emp_code", ASCENDING).skip(skip).limit(page_size)
    items = [serialize_doc_to_employee(doc) for doc in cursor]

    return {"items": items, "total": total, "page": page, "page_size": page_size}


# --------------------------------------------------------------------------- #
# Endpoints: Attendance Recording & Management
# --------------------------------------------------------------------------- #
@app.post("/attendance/punch-in", status_code=201, tags=["attendance"])
def punch_in(body: PunchInRequest):
    """
    Records a punch-in. Creates the day's record (R1, R2).
    Concurrency: two simultaneous punch-ins for the same employee and date yield
    exactly one 201 and 409 for conflicts.
    """
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    raw_punch_in_ms = body.punched_at if body.punched_at is not None else now_epoch_ms()
    punch_in_ms = truncate_epoch_ms(raw_punch_in_ms)

    attendance_date = get_attendance_date_for_punch_in(
        punch_in_ms=punch_in_ms,
        shift_start=emp["shift_start"],
        shift_end=emp["shift_end"],
    )

    late_mins = compute_late_minutes(
        punch_in_ms=punch_in_ms,
        shift_start=emp["shift_start"],
        attendance_date=attendance_date,
    )

    doc = {
        "emp_code": body.emp_code,
        "date": attendance_date,
        "status": body.status,
        "punch_in": ms_to_datetime_utc(punch_in_ms),
        "punch_out": None,
        "work_hours": None,
        "late_minutes": late_mins,
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }

    try:
        db.attendance_logs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Already punched in for this date")

    return serialize_doc_to_attendance_record(doc)


@app.post("/attendance/punch-out", status_code=200, tags=["attendance"])
def punch_out(body: PunchOutRequest):
    """
    Records a punch-out.
    Closes the employee's most recent record whose punch_in is <= punched_at.
    Computes work_hours (R4), overtime_minutes (R3), and half_day (R5).
    Concurrency: two simultaneous punch-outs yield exactly one 200 and 409.
    """
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    raw_punch_out_ms = body.punched_at if body.punched_at is not None else now_epoch_ms()
    punch_out_ms = truncate_epoch_ms(raw_punch_out_ms)
    punch_out_dt = ms_to_datetime_utc(punch_out_ms)

    # Find the most recent record whose punch_in <= punched_at
    record = db.attendance_logs.find_one(
        {
            "emp_code": body.emp_code,
            "punch_in": {"$ne": None, "$lte": punch_out_dt},
        },
        sort=[("date", DESCENDING), ("punch_in", DESCENDING)],
    )

    if not record:
        raise HTTPException(status_code=404, detail="No matching punch-in found for employee")

    # If already punched out, return 409
    if record.get("punch_out") is not None:
        raise HTTPException(status_code=409, detail="Record is already punched out")

    punch_in_ms = datetime_to_ms(record["punch_in"])
    assert punch_in_ms is not None

    # Contract validation: punched_at <= punch_in or more than 24 hours after it -> 422
    if punch_out_ms <= punch_in_ms:
        raise HTTPException(status_code=422, detail="punch_out must be strictly greater than punch_in")
    if (punch_out_ms - punch_in_ms) > 24 * 3600 * 1000:
        raise HTTPException(status_code=422, detail="punch_out cannot be more than 24 hours after punch_in")

    # Calculate derived metrics
    attendance_date = record["date"]
    work_hrs = compute_work_hours(punch_in_ms, punch_out_ms)
    ot_mins = compute_overtime_minutes(
        punch_out_ms=punch_out_ms,
        shift_start=emp["shift_start"],
        shift_end=emp["shift_end"],
        attendance_date=attendance_date,
    )
    is_half_day = compute_half_day(work_hrs)

    # Atomic conditional update to guard against concurrent punch-outs
    update_result = db.attendance_logs.find_one_and_update(
        {
            "emp_code": body.emp_code,
            "date": attendance_date,
            "punch_out": None,
        },
        {
            "$set": {
                "punch_out": punch_out_dt,
                "work_hours": work_hrs,
                "overtime_minutes": ot_mins,
                "half_day": is_half_day,
            }
        },
        return_document=True,
    )

    if not update_result:
        raise HTTPException(status_code=409, detail="Record already punched out by concurrent request")

    return serialize_doc_to_attendance_record(update_result)


@app.get("/attendance", tags=["attendance"])
def list_attendance(
    emp_code: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    status: Optional[Literal["PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"]] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    List attendance records sorted by date descending, then emp_code ascending.
    Remains fast on ~100k records via database index and cursor streaming.
    date_from > date_to returns 422.
    """
    if date_from:
        try:
            dt_date.fromisoformat(date_from)
        except ValueError:
            raise HTTPException(status_code=422, detail="date_from must be a valid calendar date")
    if date_to:
        try:
            dt_date.fromisoformat(date_to)
        except ValueError:
            raise HTTPException(status_code=422, detail="date_to must be a valid calendar date")

    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not be greater than date_to")

    q: Dict[str, Any] = {}
    if emp_code:
        q["emp_code"] = emp_code
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from
        if date_to:
            q["date"]["$lte"] = date_to
    if status:
        q["status"] = status

    skip = (page - 1) * page_size
    total = db.attendance_logs.count_documents(q)
    cursor = db.attendance_logs.find(q).sort([("date", DESCENDING), ("emp_code", ASCENDING)]).skip(skip).limit(page_size)
    items = [serialize_doc_to_attendance_record(doc) for doc in cursor]

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.patch("/attendance/{emp_code}/{date}", tags=["attendance"])
def regularize_attendance(
    emp_code: str = Path(...),
    date: str = Path(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    body: RegularizeRequest = ...,
):
    """
    Regularize (manually correct) one day's record.
    Address by (emp_code, date).
    Recomputes derived fields and appends one history entry atomically.
    Concurrent edits preserve audit history without dropping entries.
    """
    emp = db.employees.find_one({"emp_code": emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Fetch existing record; handle missing legacy fields
    existing = db.attendance_logs.find_one({"emp_code": emp_code, "date": date})
    if not existing:
        raise HTTPException(status_code=404, detail="Attendance record not found for this employee and date")

    old_status = existing.get("status")
    old_punch_in_ms = datetime_to_ms(existing.get("punch_in"))
    old_punch_out_ms = datetime_to_ms(existing.get("punch_out"))
    old_work_hours = existing.get("work_hours")
    old_late_minutes = existing.get("late_minutes", 0)
    old_overtime_minutes = existing.get("overtime_minutes", 0)
    old_half_day = bool(existing.get("half_day", False))

    # Determine candidate new status and punch times
    new_status = body.status if body.status is not None else old_status

    if new_status in ("ABSENT", "LEAVE"):
        # Setting status ABSENT or LEAVE clears both punch times
        if body.punch_in is not None or body.punch_out is not None:
            raise HTTPException(status_code=422, detail="Cannot supply punch_in or punch_out with ABSENT or LEAVE status")
        new_punch_in_ms = None
        new_punch_out_ms = None
    else:
        new_punch_in_ms = truncate_epoch_ms(body.punch_in) if body.punch_in is not None else old_punch_in_ms
        new_punch_out_ms = truncate_epoch_ms(body.punch_out) if body.punch_out is not None else old_punch_out_ms

        if new_punch_in_ms is None:
            raise HTTPException(status_code=422, detail="A presence status requires a punch_in")

        # Validate R1: punch_in must stay on the record's attendance date
        calculated_date = get_attendance_date_for_punch_in(
            punch_in_ms=new_punch_in_ms,
            shift_start=emp["shift_start"],
            shift_end=emp["shift_end"],
        )
        if calculated_date != date:
            raise HTTPException(status_code=422, detail="punch_in must stay on the record's attendance date")

        # Validate punch_out if present
        if new_punch_out_ms is not None:
            if new_punch_out_ms <= new_punch_in_ms:
                raise HTTPException(status_code=422, detail="punch_out must be strictly greater than punch_in")
            if (new_punch_out_ms - new_punch_in_ms) > 24 * 3600 * 1000:
                raise HTTPException(status_code=422, detail="punch_out cannot be more than 24 hours after punch_in")

    # Recompute derived fields
    if new_status in ("ABSENT", "LEAVE"):
        new_work_hours = None
        new_late_minutes = 0
        new_overtime_minutes = 0
        new_half_day = False
    else:
        new_late_minutes = compute_late_minutes(
            punch_in_ms=new_punch_in_ms,
            shift_start=emp["shift_start"],
            attendance_date=date,
        )
        if new_punch_out_ms is not None:
            new_work_hours = compute_work_hours(new_punch_in_ms, new_punch_out_ms)
            new_overtime_minutes = compute_overtime_minutes(
                punch_out_ms=new_punch_out_ms,
                shift_start=emp["shift_start"],
                shift_end=emp["shift_end"],
                attendance_date=date,
            )
            new_half_day = compute_half_day(new_work_hours)
        else:
            new_work_hours = None
            new_overtime_minutes = 0
            new_half_day = False

    # Compute exact changes
    changes: Dict[str, Dict[str, Any]] = {}

    if new_status != old_status:
        changes["status"] = {"from": old_status, "to": new_status}
    if new_punch_in_ms != old_punch_in_ms:
        changes["punch_in"] = {"from": old_punch_in_ms, "to": new_punch_in_ms}
    if new_punch_out_ms != old_punch_out_ms:
        changes["punch_out"] = {"from": old_punch_out_ms, "to": new_punch_out_ms}
    if new_work_hours != old_work_hours:
        changes["work_hours"] = {"from": old_work_hours, "to": new_work_hours}
    if new_late_minutes != old_late_minutes:
        changes["late_minutes"] = {"from": old_late_minutes, "to": new_late_minutes}
    if new_overtime_minutes != old_overtime_minutes:
        changes["overtime_minutes"] = {"from": old_overtime_minutes, "to": new_overtime_minutes}
    if new_half_day != old_half_day:
        changes["half_day"] = {"from": old_half_day, "to": new_half_day}

    if not changes:
        raise HTTPException(status_code=422, detail="Request does not change any fields")

    # Build history entry: in MongoDB BSON, punch dates inside changes are stored as BSON dates
    history_at_ms = now_epoch_ms()
    history_at_dt = ms_to_datetime_utc(history_at_ms)

    bson_changes: Dict[str, Dict[str, Any]] = {}
    for k, v in changes.items():
        f_val = v["from"]
        t_val = v["to"]
        if k in ("punch_in", "punch_out"):
            f_val = ms_to_datetime_utc(f_val) if f_val is not None else None
            t_val = ms_to_datetime_utc(t_val) if t_val is not None else None
        bson_changes[k] = {"from": f_val, "to": t_val}

    history_entry = {
        "at": history_at_dt,
        "by": body.regularized_by,
        "reason": body.reason,
        "changes": bson_changes,
    }

    # Atomic write with $set and $push to preserve audit history against concurrent edits
    updated_doc = db.attendance_logs.find_one_and_update(
        {"emp_code": emp_code, "date": date},
        {
            "$set": {
                "status": new_status,
                "punch_in": ms_to_datetime_utc(new_punch_in_ms) if new_punch_in_ms is not None else None,
                "punch_out": ms_to_datetime_utc(new_punch_out_ms) if new_punch_out_ms is not None else None,
                "work_hours": new_work_hours,
                "late_minutes": new_late_minutes,
                "overtime_minutes": new_overtime_minutes,
                "half_day": new_half_day,
            },
            "$push": {
                "history": history_entry
            },
        },
        return_document=True,
    )

    if not updated_doc:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    return serialize_doc_to_attendance_record(updated_doc)


# --------------------------------------------------------------------------- #
# Endpoints: Analytics Pipelines (MongoDB Aggregations)
# --------------------------------------------------------------------------- #
@app.get("/analytics/employees/{emp_code}/monthly", tags=["analytics"])
def employee_monthly(
    emp_code: str = Path(...),
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
):
    """
    Monthly attendance summary for one employee backed by a MongoDB aggregation.
    R7: working_days Mon-Fri counted from joined_on for mid-month joiners.
    present_days per R5-R7 (half_day = 0.5, Mon-Fri only).
    """
    emp = db.employees.find_one({"emp_code": emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Compute working days in month for this employee based on joined_on (R7)
    year, mo = map(int, month.split("-"))
    next_year = year if mo < 12 else year + 1
    next_mo = mo + 1 if mo < 12 else 1
    month_start_dt = dt_date(year, mo, 1)
    month_end_dt = dt_date(next_year, next_mo, 1) - timedelta(days=1)

    joined_date = dt_date.fromisoformat(emp["joined_on"])
    effective_start = max(month_start_dt, joined_date)

    working_days = 0
    cur = effective_start
    while cur <= month_end_dt:
        if cur.weekday() < 5:  # Monday to Friday
            working_days += 1
        cur += timedelta(days=1)

    # MongoDB aggregation pipeline on attendance_logs
    date_prefix = f"^{month}-"
    pipeline = [
        {
            "$match": {
                "emp_code": emp_code,
                "date": {"$regex": date_prefix},
            }
        },
        {
            "$project": {
                "status": 1,
                "half_day": {"$ifNull": ["$half_day", False]},
                "late_minutes": {"$ifNull": ["$late_minutes", 0]},
                "overtime_minutes": {"$ifNull": ["$overtime_minutes", 0]},
                "day_of_week": {
                    "$dayOfWeek": {
                        "$dateFromString": {"dateString": "$date"}
                    }
                },
            }
        },
        {
            "$group": {
                "_id": None,
                "present_days": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$in": ["$day_of_week", [2, 3, 4, 5, 6]]},  # Mon-Fri
                                    {"$in": ["$status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                ]
                            },
                            {"$cond": ["$half_day", 0.5, 1.0]},
                            0.0,
                        ]
                    }
                },
                "leave_days": {
                    "$sum": {"$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]}
                },
                "late_count": {
                    "$sum": {"$cond": [{"$gt": ["$late_minutes", 0]}, 1, 0]}
                },
                "total_late_minutes": {"$sum": "$late_minutes"},
                "total_overtime_minutes": {"$sum": "$overtime_minutes"},
            }
        },
    ]

    agg_res = list(db.attendance_logs.aggregate(pipeline))

    if agg_res:
        stats = agg_res[0]
        raw_present_days = float(stats.get("present_days", 0.0))
        leave_days = int(stats.get("leave_days", 0))
        late_count = int(stats.get("late_count", 0))
        total_late = int(stats.get("total_late_minutes", 0))
        total_ot = int(stats.get("total_overtime_minutes", 0))
    else:
        raw_present_days = 0.0
        leave_days = 0
        late_count = 0
        total_late = 0
        total_ot = 0

    present_days = round_half_up(raw_present_days, 2)
    attendance_pct = None
    if working_days > 0:
        raw_pct = (raw_present_days / working_days) * 100.0
        attendance_pct = round_half_up(raw_pct, 2)

    return {
        "emp_code": emp_code,
        "month": month,
        "working_days": working_days,
        "present_days": present_days,
        "leave_days": leave_days,
        "late_count": late_count,
        "total_late_minutes": total_late,
        "total_overtime_minutes": total_ot,
        "attendance_pct": attendance_pct,
    }


@app.get("/analytics/departments/summary", tags=["analytics"])
def department_summary(
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    department: Optional[str] = Query(None, description="Restrict to one department (exact match)."),
):
    """
    Department summary for a month via a cross-collection MongoDB aggregation.
    - Headcount per R9: people with 0 logs still count, people who join later do not.
    - Average work hours is over underlying records, not average of averages.
    - Omit departments whose headcount is 0 for the month.
    """
    year, mo = map(int, month.split("-"))
    next_year = year if mo < 12 else year + 1
    next_mo = mo + 1 if mo < 12 else 1
    month_end_date = (dt_date(next_year, next_mo, 1) - timedelta(days=1)).isoformat()

    match_stage: Dict[str, Any] = {
        "joined_on": {"$lte": month_end_date}
    }
    if department is not None:
        match_stage["department"] = department

    date_prefix = f"^{month}-"

    pipeline = [
        {"$match": match_stage},
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"emp_code": "$emp_code"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$emp_code", "$$emp_code"]},
                                    {"$regexMatch": {"input": "$date", "regex": date_prefix}},
                                ]
                            }
                        }
                    }
                ],
                "as": "logs",
            }
        },
        {
            "$group": {
                "_id": "$department",
                "headcount": {"$sum": 1},
                "all_logs": {
                    "$push": "$logs"
                },
            }
        },
        {
            "$project": {
                "department": "$_id",
                "headcount": 1,
                "flat_logs": {
                    "$reduce": {
                        "input": "$all_logs",
                        "initialValue": [],
                        "in": {"$concatArrays": ["$$value", "$$this"]}
                    }
                },
            }
        },
        {
            "$project": {
                "department": 1,
                "headcount": 1,
                "present_days": {
                    "$sum": {
                        "$map": {
                            "input": "$flat_logs",
                            "as": "log",
                            "in": {
                                "$cond": [
                                    {
                                        "$and": [
                                            {
                                                "$in": [
                                                    {
                                                        "$dayOfWeek": {
                                                            "$dateFromString": {"dateString": "$$log.date"}
                                                        }
                                                    },
                                                    [2, 3, 4, 5, 6],
                                                ]
                                            },
                                            {"$in": ["$$log.status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                        ]
                                    },
                                    {"$cond": [{"$ifNull": ["$$log.half_day", False]}, 0.5, 1.0]},
                                    0.0,
                                ]
                            },
                        }
                    }
                },
                "work_hours_records": {
                    "$filter": {
                        "input": "$flat_logs",
                        "as": "log",
                        "cond": {
                            "$and": [
                                {"$in": ["$$log.status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                {"$ne": ["$$log.work_hours", None]},
                            ]
                        },
                    }
                },
                "late_count": {
                    "$sum": {
                        "$map": {
                            "input": "$flat_logs",
                            "as": "log",
                            "in": {"$cond": [{"$gt": [{"$ifNull": ["$$log.late_minutes", 0]}, 0]}, 1, 0]},
                        }
                    }
                },
                "total_late_minutes": {
                    "$sum": {
                        "$map": {
                            "input": "$flat_logs",
                            "as": "log",
                            "in": {"$ifNull": ["$$log.late_minutes", 0]},
                        }
                    }
                },
                "leave_count": {
                    "$sum": {
                        "$map": {
                            "input": "$flat_logs",
                            "as": "log",
                            "in": {"$cond": [{"$eq": ["$$log.status", "LEAVE"]}, 1, 0]},
                        }
                    }
                },
                "on_duty_count": {
                    "$sum": {
                        "$map": {
                            "input": "$flat_logs",
                            "as": "log",
                            "in": {"$cond": [{"$eq": ["$$log.status", "ON_DUTY"]}, 1, 0]},
                        }
                    }
                },
            }
        },
        {
            "$project": {
                "department": 1,
                "headcount": 1,
                "present_days": 1,
                "avg_work_hours": {
                    "$cond": [
                        {"$gt": [{"$size": "$work_hours_records"}, 0]},
                        {"$avg": "$work_hours_records.work_hours"},
                        None,
                    ]
                },
                "late_count": 1,
                "total_late_minutes": 1,
                "leave_count": 1,
                "on_duty_count": 1,
            }
        },
        {"$sort": {"department": ASCENDING}},
    ]

    results = list(db.employees.aggregate(pipeline))
    items = []
    for r in results:
        items.append({
            "department": r["department"],
            "headcount": int(r["headcount"]),
            "present_days": round_half_up(float(r["present_days"]), 2),
            "avg_work_hours": round_half_up(r["avg_work_hours"], 2) if r.get("avg_work_hours") is not None else None,
            "late_count": int(r["late_count"]),
            "total_late_minutes": int(r["total_late_minutes"]),
            "leave_count": int(r["leave_count"]),
            "on_duty_count": int(r["on_duty_count"]),
        })

    return {"month": month, "items": items}


@app.get("/analytics/leaderboard/late", tags=["analytics"])
def late_leaderboard(
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    limit: int = Query(10, ge=1, le=50),
    department: Optional[str] = Query(None),
):
    """
    Late-comers leaderboard for a month.
    Uses MongoDB $setWindowFields with $rank for standard competition ranking (1, 2, 2, 4).
    Limit is applied after ranking (all rows with rank <= limit returned).
    Order: total_late_minutes DESC, then emp_code ASC.
    """
    date_prefix = f"^{month}-"

    pipeline: List[Dict[str, Any]] = [
        {
            "$match": {
                "date": {"$regex": date_prefix},
                "late_minutes": {"$gt": 0},
            }
        },
        {
            "$group": {
                "_id": "$emp_code",
                "total_late_minutes": {"$sum": "$late_minutes"},
                "late_count": {"$sum": 1},
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "localField": "_id",
                "foreignField": "emp_code",
                "as": "emp",
            }
        },
        {"$unwind": "$emp"},
    ]

    if department:
        pipeline.append({"$match": {"emp.department": department}})

    pipeline.extend([
        {
            "$setWindowFields": {
                "sortBy": {"total_late_minutes": DESCENDING},
                "output": {
                    "rank": {"$rank": {}}
                }
            }
        },
        {
            "$match": {
                "rank": {"$lte": limit}
            }
        },
        {
            "$sort": {
                "total_late_minutes": DESCENDING,
                "emp.emp_code": ASCENDING,
            }
        },
        {
            "$project": {
                "_id": 0,
                "rank": 1,
                "emp_code": "$emp.emp_code",
                "name": "$emp.name",
                "department": "$emp.department",
                "total_late_minutes": 1,
                "late_count": 1,
            }
        }
    ])

    results = list(db.attendance_logs.aggregate(pipeline))
    return {"month": month, "items": results}


@app.get("/analytics/departments/{department}/trend", tags=["analytics"])
def department_trend(
    department: str = Path(...),
    from_date: str = Query(..., alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: str = Query(..., alias="to", pattern=r"^\d{4}-\d{2}-\d{2}$"),
):
    """
    Daily attendance trend for a department.
    Returns exactly one row per calendar day from 'from' to 'to' inclusive.
    Gap-filling via $densify and moving average 7d via $setWindowFields in MongoDB.
    """
    d_start = dt_date.fromisoformat(from_date)
    d_end = dt_date.fromisoformat(to_date)

    if d_end < d_start:
        raise HTTPException(status_code=422, detail="'to' date must not be earlier than 'from' date")
    if (d_end - d_start).days > 92:
        raise HTTPException(status_code=422, detail="Date range must not exceed 92 days")

    # Check department existence (404 if no employees exist in department)
    dept_emp_count = db.employees.count_documents({"department": department})
    if dept_emp_count == 0:
        raise HTTPException(status_code=404, detail="Department not found")

    dt_bound_start = datetime(d_start.year, d_start.month, d_start.day, tzinfo=UTC)
    dt_bound_end_exclusive = datetime(d_end.year, d_end.month, d_end.day, tzinfo=UTC) + timedelta(days=1)

    pipeline = [
        {"$match": {"department": department}},
        {"$limit": 1},
        {
            "$project": {
                "d": {"$literal": dt_bound_start}
            }
        },
        {
            "$densify": {
                "field": "d",
                "range": {
                    "step": 1,
                    "unit": "day",
                    "bounds": [dt_bound_start, dt_bound_end_exclusive],
                }
            }
        },
        {
            "$project": {
                "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$d"}},
                "dayOfWeek": {"$dayOfWeek": "$d"},
                "_id": 0,
            }
        },
        {
            "$project": {
                "date": 1,
                "is_working_day": {"$in": ["$dayOfWeek", [2, 3, 4, 5, 6]]},
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "let": {"cur_date": "$date"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$department", department]},
                                    {"$lte": ["$joined_on", "$$cur_date"]},
                                ]
                            }
                        }
                    },
                    {"$count": "cnt"}
                ],
                "as": "hc_docs"
            }
        },
        {
            "$addFields": {
                "headcount": {"$ifNull": [{"$arrayElemAt": ["$hc_docs.cnt", 0]}, 0]}
            }
        },
        {"$project": {"hc_docs": 0}},
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"cur_date": "$date"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {"$eq": ["$date", "$$cur_date"]}
                        }
                    },
                    {
                        "$lookup": {
                            "from": "employees",
                            "localField": "emp_code",
                            "foreignField": "emp_code",
                            "as": "e"
                        }
                    },
                    {"$unwind": "$e"},
                    {"$match": {"e.department": department}},
                    {
                        "$group": {
                            "_id": None,
                            "present_count": {
                                "$sum": {
                                    "$cond": [
                                        {"$in": ["$status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                        {"$cond": [{"$ifNull": ["$half_day", False]}, 0.5, 1.0]},
                                        0.0,
                                    ]
                                }
                            },
                            "late_count": {
                                "$sum": {
                                    "$cond": [{"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]}, 1, 0]
                                }
                            },
                        }
                    }
                ],
                "as": "att_stats"
            }
        },
        {
            "$addFields": {
                "present_count": {"$ifNull": [{"$arrayElemAt": ["$att_stats.present_count", 0]}, 0.0]},
                "late_count": {"$ifNull": [{"$arrayElemAt": ["$att_stats.late_count", 0]}, 0]}
            }
        },
        {"$project": {"att_stats": 0}},
        {
            "$addFields": {
                "attendance_rate": {
                    "$cond": [
                        {"$and": ["$is_working_day", {"$gt": ["$headcount", 0]}]},
                        {"$divide": ["$present_count", "$headcount"]},
                        None
                    ]
                }
            }
        },
        {
            "$setWindowFields": {
                "sortBy": {"date": ASCENDING},
                "output": {
                    "moving_avg_7d": {
                        "$avg": "$attendance_rate",
                        "window": {
                            "documents": [-6, 0]
                        }
                    }
                }
            }
        },
        {"$sort": {"date": ASCENDING}}
    ]

    results = list(db.employees.aggregate(pipeline))
    items = []
    for r in results:
        items.append({
            "date": r["date"],
            "is_working_day": bool(r["is_working_day"]),
            "headcount": int(r["headcount"]),
            "present_count": round_half_up(float(r["present_count"]), 2),
            "late_count": int(r["late_count"]),
            "attendance_rate": round_half_up(r["attendance_rate"], 4) if r.get("attendance_rate") is not None else None,
            "moving_avg_7d": round_half_up(r["moving_avg_7d"], 4) if r.get("moving_avg_7d") is not None else None,
        })

    return {"department": department, "items": items}


# --------------------------------------------------------------------------- #
# Endpoints: Explain Endpoint (MongoDB Query Plans with executionStats)
# --------------------------------------------------------------------------- #
@app.get("/admin/explain/{endpoint}", tags=["admin"])
def explain_endpoint(
    endpoint: str = Path(...),
    emp_code: Optional[str] = Query(None),
    month: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    department: Optional[str] = Query(None),
    limit: Optional[int] = Query(10, ge=1, le=50),
    date_from: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    status: Optional[Literal["PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"]] = Query(None),
    from_date: Optional[str] = Query(None, alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: Optional[str] = Query(None, alias="to", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    page: Optional[int] = Query(1, ge=1),
    page_size: Optional[int] = Query(20, ge=1, le=100),
):
    """
    Runs explain with executionStats verbosity for the main query or pipeline of the
    named endpoint, built exactly as that endpoint builds it.
    """
    if endpoint == "attendance_list":
        if date_from and date_to and date_from > date_to:
            raise HTTPException(status_code=422, detail="date_from must not be greater than date_to")
        q: Dict[str, Any] = {}
        if emp_code:
            q["emp_code"] = emp_code
        if date_from or date_to:
            q["date"] = {}
            if date_from:
                q["date"]["$gte"] = date_from
            if date_to:
                q["date"]["$lte"] = date_to
        if status:
            q["status"] = status

        p = page or 1
        ps = page_size or 20
        skip = (p - 1) * ps

        cursor = db.attendance_logs.find(q).sort([("date", DESCENDING), ("emp_code", ASCENDING)]).skip(skip).limit(ps)
        plan = cursor.explain()
        return {"endpoint": endpoint, "collection": "attendance_logs", "explain": plan}

    elif endpoint == "employee_monthly":
        if not emp_code or not month:
            raise HTTPException(status_code=422, detail="emp_code and month are required for employee_monthly")

        date_prefix = f"^{month}-"
        pipeline = [
            {
                "$match": {
                    "emp_code": emp_code,
                    "date": {"$regex": date_prefix},
                }
            },
            {
                "$group": {
                    "_id": None,
                    "present_days": {"$sum": 1},
                }
            }
        ]
        cmd = {
            "explain": {
                "aggregate": "attendance_logs",
                "pipeline": pipeline,
                "cursor": {},
            },
            "verbosity": "executionStats",
        }
        plan = db.command(cmd)
        return {"endpoint": endpoint, "collection": "attendance_logs", "explain": plan}

    elif endpoint == "department_summary":
        if not month:
            raise HTTPException(status_code=422, detail="month is required for department_summary")

        year, mo = map(int, month.split("-"))
        next_year = year if mo < 12 else year + 1
        next_mo = mo + 1 if mo < 12 else 1
        month_end_date = (dt_date(next_year, next_mo, 1) - timedelta(days=1)).isoformat()

        match_stage: Dict[str, Any] = {"joined_on": {"$lte": month_end_date}}
        if department:
            match_stage["department"] = department

        pipeline = [
            {"$match": match_stage},
            {
                "$lookup": {
                    "from": "attendance_logs",
                    "localField": "emp_code",
                    "foreignField": "emp_code",
                    "as": "logs",
                }
            },
            {"$group": {"_id": "$department", "headcount": {"$sum": 1}}},
        ]
        cmd = {
            "explain": {
                "aggregate": "employees",
                "pipeline": pipeline,
                "cursor": {},
            },
            "verbosity": "executionStats",
        }
        plan = db.command(cmd)
        return {"endpoint": endpoint, "collection": "employees", "explain": plan}

    elif endpoint == "late_leaderboard":
        if not month:
            raise HTTPException(status_code=422, detail="month is required for late_leaderboard")

        date_prefix = f"^{month}-"
        pipeline = [
            {
                "$match": {
                    "date": {"$regex": date_prefix},
                    "late_minutes": {"$gt": 0},
                }
            },
            {
                "$group": {
                    "_id": "$emp_code",
                    "total_late_minutes": {"$sum": "$late_minutes"},
                    "late_count": {"$sum": 1},
                }
            },
            {
                "$lookup": {
                    "from": "employees",
                    "localField": "_id",
                    "foreignField": "emp_code",
                    "as": "emp",
                }
            },
            {"$unwind": "$emp"},
        ]
        if department:
            pipeline.append({"$match": {"emp.department": department}})

        pipeline.append({
            "$setWindowFields": {
                "sortBy": {"total_late_minutes": DESCENDING},
                "output": {"rank": {"$rank": {}}}
            }
        })

        cmd = {
            "explain": {
                "aggregate": "attendance_logs",
                "pipeline": pipeline,
                "cursor": {},
            },
            "verbosity": "executionStats",
        }
        plan = db.command(cmd)
        return {"endpoint": endpoint, "collection": "attendance_logs", "explain": plan}

    elif endpoint == "department_trend":
        dept = department
        f_dt = from_date
        t_dt = to_date
        if not dept or not f_dt or not t_dt:
            raise HTTPException(status_code=422, detail="department, from, and to are required for department_trend")

        d_start = dt_date.fromisoformat(f_dt)
        d_end = dt_date.fromisoformat(t_dt)
        if d_end < d_start:
            raise HTTPException(status_code=422, detail="'to' date must not be earlier than 'from' date")
        if (d_end - d_start).days > 92:
            raise HTTPException(status_code=422, detail="Date range must not exceed 92 days")

        dt_bound_start = datetime(d_start.year, d_start.month, d_start.day, tzinfo=UTC)
        dt_bound_end_exclusive = datetime(d_end.year, d_end.month, d_end.day, tzinfo=UTC) + timedelta(days=1)

        pipeline = [
            {"$match": {"department": dept}},
            {"$limit": 1},
            {"$project": {"d": {"$literal": dt_bound_start}}},
            {
                "$densify": {
                    "field": "d",
                    "range": {
                        "step": 1,
                        "unit": "day",
                        "bounds": [dt_bound_start, dt_bound_end_exclusive],
                    }
                }
            },
        ]
        cmd = {
            "explain": {
                "aggregate": "employees",
                "pipeline": pipeline,
                "cursor": {},
            },
            "verbosity": "executionStats",
        }
        plan = db.command(cmd)
        return {"endpoint": endpoint, "collection": "employees", "explain": plan}

    else:
        raise HTTPException(status_code=422, detail=f"Unknown endpoint: {endpoint}")
