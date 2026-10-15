# Part A: Starter Code Review (`app/main.py`)

I reviewed `app/main.py` as a pull request review on the starter codebase. While the happy path works under light manual testing, I identified **11 genuine defects** across helper functions, schema models, and endpoints. Several of these cause subtle calculation bugs, unhandled 500 crashes, or critical race conditions under concurrent load.

Below is the structured breakdown of each defect with concrete reproducing inputs, symptoms, and applied fixes, followed by items examined and confirmed correct.

---

## Summary of Identified Defects

| # | Location | Defect Summary | Severity / Impact |
|---|---|---|---|
| **1** | `health` (lines 72–74) | Always returns HTTP 200 without checking MongoDB | High (Readiness probe failure) |
| **2** | `compute_late_minutes` (lines 33–37) | Incorrect grace period boundary check & timezone mismatch | Critical (Faulty payroll penalty) |
| **3** | `compute_work_hours` (lines 40–41) | Uses Python banker's rounding instead of half-up | Medium (Precision discrepancy) |
| **4** | `compute_overtime` (lines 44–47) | Missing 30-min threshold & broken overnight shifts | High (Overtime calculation error) |
| **5** | `create_employee` (lines 77–85) | Non-atomic check-then-insert allows duplicate codes | Critical (Data corruption / race) |
| **6** | `list_employees` (lines 88–96) | Broken pagination skip formula & global count | High (Omits page 1 records) |
| **7** | `punch_in` (lines 99–121) | Check-then-insert race, leaky `id`, 500 on missing employee | Critical (Duplicate punches / 500 crash) |
| **8** | `list_attendance` (lines 124–150) | In-memory sorting and filtering on full dataset | Critical (Memory crash at 100k docs) |
| **9** | Input Schemas | Missing validation for millisecond epoch timestamps & status | Medium (Contract validation failure) |
| **10** | Timestamp handling | Sub-second milliseconds stored without truncation | Medium (Calculation drift) |
| **11** | Database client initialization | PyMongo client created without `tz_aware=True` | High (Offset-naive vs aware errors) |

---

## Detailed Defect Breakdown

### 1. `health` (lines 72–74) — False Positive Readiness Status
* **Where:** `GET /health` endpoint
* **What is wrong:** The endpoint returned a hardcoded `{"status": "ok"}` with status 200 without actually verifying if MongoDB was reachable. If the database was stopped or network severed, it still reported healthy.
* **How you'd notice it:** Stop the MongoDB service and call `curl http://localhost:8000/health`. The starter still returns `200 OK` instead of the expected `503 Service Unavailable`.
* **How you fixed it:** Added an explicit admin ping command `client.admin.command("ping")` wrapped in a `try/except` block. If the ping fails or times out, it raises `HTTPException(status_code=503, detail="Database unavailable")`.

---

### 2. `compute_late_minutes` (lines 33–37) — Grace Period Boundary & Timezone Mismatch
* **Where:** `compute_late_minutes` helper function
* **What is wrong:**
  1. It used naive `.replace(tzinfo=...)` on UTC timestamps, causing offset errors against IST shift timings.
  2. The boundary comparison `minutes > 10` was evaluated after integer floor division. This meant `09:40:01` was truncated to 10 elapsed minutes, where `10 > 10` evaluated to `False`, incorrectly giving `0` late minutes.
* **How you'd notice it:** An employee with a `09:30` shift punches in at `09:40:01 IST`. Contract Rule R2 specifies this is strictly past the 10-minute grace period and must incur 10 late minutes. The starter function returned `0`.
* **How you fixed it:** Standardized instant conversion to Indian Standard Time (IST, UTC+5:30). Calculated the difference in exact total seconds against the shift start instant. Applied the condition: only if `diff_seconds > 600`, return `diff_seconds // 60`, otherwise `0`. This guarantees exact contract behavior:
  * `09:40:00` $\rightarrow$ `0`
  * `09:40:01` $\rightarrow$ `10`
  * `10:15:59` $\rightarrow$ `45`

---

### 3. `compute_work_hours` (lines 40–41) — Banker's Rounding vs Half-Up Rounding
* **Where:** `compute_work_hours` helper function
* **What is wrong:** Used built-in Python `round(hours, 2)`. Python's `round()` implements IEEE 754 "round-to-even" (banker's rounding), which rounds `.005` down to even numbers instead of arithmetic half-up required by Rule R4/R8.
* **How you'd notice it:** An attendance interval resulting in exactly `4.495` hours rounds down to `4.49` with Python's standard `round()`, but contract Rule R4/R8 mandates half-up rounding to `4.50` (which changes half-day status).
* **How you fixed it:** Implemented an explicit `round_half_up(val, 2)` helper utilizing Python's `decimal.Decimal` with the `ROUND_HALF_UP` quantization strategy.

---

### 4. `compute_overtime` (lines 44–47) — Missing Minimum Threshold & Overnight Shifts
* **Where:** `compute_overtime` helper function
* **What is wrong:**
  1. It credited any positive minutes past shift end as overtime, ignoring Rule R3 which requires a minimum threshold of 30 minutes before overtime begins counting.
  2. For overnight shifts (e.g. `22:00` to `06:00`), `shift_end` is numerically smaller than `shift_start`. The starter computed time difference against the start date's `06:00` (which is in the past), producing negative or zero values.
* **How you'd notice it:**
  * Punching out 15 minutes past shift end returned `15` instead of `0`.
  * For an overnight shift (`22:00–06:00`), punching out at `06:40` returned `0` instead of `40` minutes overtime.
* **How you fixed it:**
  * Added overnight shift detection: if `shift_end <= shift_start`, the shift end instant is attributed to `date + 1 day`.
  * Computed elapsed whole minutes (floor). If `minutes < 30`, return `0`; if `minutes >= 30`, return `minutes`.

---

### 5. `create_employee` (lines 77–85) — Non-Atomic Check & Schema Gaps
* **Where:** `POST /employees` endpoint and `EmployeeIn` schema
* **What is wrong:**
  1. Performed a `find_one` followed by `insert_one`. Under concurrent requests with the same `emp_code`, both checks pass, resulting in duplicate codes or unhandled crashes.
  2. Missing input validation: `shift_start == shift_end` was accepted, and `emp_code` regex (`^EMP\d{4,6}$`) was not enforced.
  3. Returned naive ISO timestamp strings for `created_at` instead of integer epoch milliseconds.
* **How you'd notice it:** Sending two concurrent POST requests with `emp_code: "EMP0001"` crashed with 500 or created duplicate entries. Supplying identical start and end shifts (`09:00` and `09:00`) returned 201 instead of 422.
* **How you fixed it:**
  * Added a unique index on `employees.emp_code` and caught `DuplicateKeyError` to return HTTP `409 Conflict`.
  * Added Pydantic field validators ensuring `shift_start != shift_end` and validating employee code formatting.
  * Converted `created_at` to integer epoch milliseconds in all response serializers.

---

### 6. `list_employees` (lines 88–96) — Broken Pagination Skip Formula & Filter Total
* **Where:** `GET /employees` endpoint
* **What is wrong:**
  1. The pagination skip formula was written as `skip = page * page_size`. For `page=1, page_size=20`, this set `skip = 20`, completely skipping the first 20 records on page 1!
  2. `total` was calculated as `db.employees.count_documents({})`, counting the entire collection and ignoring active department query filters.
  3. Did not enforce sorting by `emp_code` ascending.
* **How you'd notice it:** Requesting `GET /employees?page=1&page_size=20` omitted the first 20 employees. Filtering by `department=Sales` returned a `total` reflecting the entire company directory instead of only Sales staff.
* **How you fixed it:**
  * Corrected skip logic to `skip = (page - 1) * page_size`.
  * Passed the query filter `q` into `count_documents(q)`.
  * Chained `.sort("emp_code", ASCENDING)` on the cursor.

---

### 7. `punch_in` (lines 99–121) — Race Conditions & Leaky Internal IDs
* **Where:** `POST /attendance/punch-in` endpoint
* **What is wrong:**
  1. Used a check-then-insert pattern. Two simultaneous punch-ins for the same employee on the same date both passed the check, inserting duplicate attendance records for the day.
  2. Injected internal MongoDB `_id` into the response object as `"id"`, violating the strict OpenAPI schema.
  3. If an unknown `emp_code` was passed, `db.employees.find_one()` returned `None`, and the code crashed with a `500 Internal Server Error` when trying to read `emp['shift_start']`.
* **How you'd notice it:**
  * Two simultaneous punch-in calls created two records for the same employee date.
  * Punching in for non-existent employee `EMP9999` produced a 500 crash instead of a clean `404 Not Found`.
  * Response body contained an unexpected `"id"` property.
* **How you fixed it:**
  * Created a unique compound index on `attendance_logs(emp_code, date)` and handled `DuplicateKeyError` to return HTTP `409 Conflict`.
  * Added an explicit employee lookup check returning HTTP `404` if the employee does not exist.
  * Formatted output using a clean serializer conforming strictly to `AttendanceRecord` schema without `_id` or `id`.

---

### 8. `list_attendance` (lines 124–150) — In-Memory Fetch & Missing Range Validation
* **Where:** `GET /attendance` endpoint
* **What is wrong:**
  1. Executed `list(db.attendance_logs.find(q))` which loaded all matching records into Python server RAM, and then sorted and sliced in Python. On a collection of 100,000 documents, this exhausts server memory and takes several seconds.
  2. Did not validate that `date_from <= date_to` (an inverted range returned empty list instead of HTTP 422).
  3. Missing max limit constraint `page_size <= 100`.
* **How you'd notice it:** High memory usage and latency on large collections. Requesting `date_from=2026-07-10&date_to=2026-07-01` returned 200 with empty list instead of the required `422 Unprocessable Entity`.
* **How you fixed it:**
  * Replaced in-memory sorting with native MongoDB cursor operations: `.sort([("date", DESCENDING), ("emp_code", ASCENDING)]).skip((page - 1) * page_size).limit(page_size)`.
  * Backed the query with compound index `(date DESC, emp_code ASC)`.
  * Added validation raising HTTP `422` if `date_from > date_to`.

---

### 9. Input Schemas — Missing Type & Instant Range Restrictions
* **Where:** Pydantic request body schemas (`PunchInIn`, `PunchOutIn`, `EmployeeIn`)
* **What is wrong:** The starter accepted arbitrary timestamps, including small integers (seconds instead of epoch milliseconds), negative numbers, or invalid enum statuses (e.g. `ABSENT` on punch-in).
* **How you'd notice it:** Submitting `punched_at: 1783312500` (which is seconds rather than milliseconds) was stored directly, causing massive date calculation errors (year 1970). Punching in with `status: "ABSENT"` succeeded.
* **How you fixed it:** Added strict Pydantic `Field` bounds `ge=100_000_000_000, le=4_102_444_800_000` to reject second-based or out-of-range epoch timestamps with HTTP 422. Restricted punch-in status to valid presence enums (`PRESENT`, `WFH`, `ON_DUTY`).

---

### 10. Instant Truncation — Sub-second Milliseconds Stored
* **Where:** Instant intake on punch-in and punch-out
* **What is wrong:** Contract Rule R1 explicitly specifies: *"Before any calculation, instants are truncated to whole seconds (10:15:32.800 becomes 10:15:32.000), and the truncated value is what is stored and returned."* The starter preserved sub-second fractions, causing drift in work hour calculations.
* **How you'd notice it:** Sending `punched_at: 1783312500900` stored `.900` in the database and returned `.900` in responses.
* **How you fixed it:** Enforced integer floor truncation `(ms // 1000) * 1000` right at the API intake boundary before calculations, storage, or responses.

---

### 11. Database Connection — Naive Datetime Handling
* **Where:** `MongoClient` instantiation
* **What is wrong:** The starter connected to MongoDB without `tz_aware=True`. PyMongo returned naive datetimes from BSON. Mixing naive datetimes with timezone-aware Python `datetime` objects raised `TypeError: can't compare offset-naive and offset-aware datetimes`.
* **How you'd notice it:** Comparing BSON-retrieved dates against UTC/IST timezone-aware objects crashed helper functions with runtime `TypeError`.
* **How you fixed it:** Initialized PyMongo with `MongoClient(uri, tz_aware=True)` and standardized on storing UTC BSON datetimes internally while serializing to epoch milliseconds at API boundaries.

---

## Behaviors Examined and Confirmed Correct

During the review, I also evaluated the following design choices in the starter and determined they are solid and should be preserved:

1. **FastAPI Application Factory & Route Architecture:**
   Using FastAPI's lightweight route decorators, standard dependency patterns, and Pydantic validation models is clean, idiomatic, and maintainable.
2. **Configuration Hierarchy & Environment Fallbacks:**
   Reading `MONGO_URI` and `MONGO_DB` from the environment while falling back safely to local defaults (`mongodb://localhost:27017` / `attendance_db`) is developer-friendly and conforms to 12-factor app configuration principles.
3. **Pydantic Validation Error Status (HTTP 422):**
   FastAPI's native request validation correctly generates HTTP 422 responses matching the OpenAPI schema requirement for malformed payloads.
