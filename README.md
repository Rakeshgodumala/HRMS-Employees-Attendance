# HROne Employee Attendance & Workforce Analytics System

An enterprise-grade attendance tracking and workforce analytics platform built with **FastAPI**, **MongoDB 6.0+**, and a responsive **React (Vite)** dashboard.

The system enforces strict business rules (grace periods, overnight shifts, overtime thresholds, decimal half-up rounding), concurrency-safe punch records, and real-time MongoDB aggregation pipelines for moving averages and competition tie rankings.

---

## 📌 Features at a Glance

* **Executive Dashboard:** High-level workforce metrics, eligible headcount tracking (Rule R9), worked days, and monthly tardiness rollups.
* **Attendance Management:** Live operational portal to record **Punch-In** and **Punch-Out** with instant validation, date filters, and IST time display.
* **Attendance Regularization:** Auditable manual correction of punch times and statuses with an **immutable append-only audit trail** preserving author, reason, and field diffs.
* **Deep Analytics & Trends:**
  * **Department Daily Trends:** Native `$densify` calendar gap-filling with a 7-day rolling moving average.
  * **Late Leaderboard:** Standard competition ranking (`1, 2, 2, 4`) via MongoDB `$rank` window operators with tie handling.
  * **Department Summary:** Cross-collection joins (`$lookup`) correctly preserving staff with 0 logs.
  * **Employee Monthly Report:** Individual working days, presence rate, overtime, and tardiness breakdown.

---

## 🛠️ Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Backend Engine** | Python 3.11+, FastAPI, Uvicorn, Pydantic v2 |
| **Database** | MongoDB 6.0+ (Native Aggregations: `$densify`, `$setWindowFields`, `$rank`, `$lookup`) |
| **Frontend UI** | React 19, Vite, Bootstrap 5, Vanilla CSS |
| **Testing** | Pytest, TestClient, Concurrent Thread Pools |

---

## 🚀 Quickstart Guide (Windows)

### 1. Prerequisites
- **Python 3.11+** installed
- **Node.js 18+** & **npm** installed
- **MongoDB 6.0+** running locally on port `27017` (or provide `MONGO_URI`)

---

### 2. Backend Setup & Run

Open a terminal at the project root (`HRMS Task`):

```powershell
# 1. (Optional) Create and activate a Python virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Install backend dependencies
pip install -r requirements.txt

# 3. (Optional) Seed sample data for July 2026
python sample_seed.py

# 4. Start the FastAPI backend server
uvicorn app.main:app --port 8000
```

* **API Base URL:** `http://localhost:8000`
* **Interactive Swagger UI Docs:** `http://localhost:8000/docs`
* **Health Check Readiness Probe:** `http://localhost:8000/health` (Returns 200 on DB ping, 503 if DB is down)

---

### 3. Frontend Dashboard Setup & Run

Open a **second terminal** in the `frontend/` folder:

```powershell
# 1. Navigate to frontend folder
cd frontend

# 2. Install frontend dependencies
npm install

# 3. Start the Vite development server
npm run dev
```

* **Frontend Dashboard URL:** Open `http://localhost:5173` in your browser.

---

## 🧪 Automated Testing

Run the comprehensive test suite covering all business rules, concurrency race conditions, and explain plans:

```powershell
python -m pytest -v
```

* **17 of 17 tests pass (100% pass rate)**.
* Validates concurrent punch-ins (`201` + `409`), concurrent punch-outs, overnight shifts, competition ranking ties, and database index scans (`IXSCAN`).

---

## 📐 Business Rules Cheat Sheet

| Rule | Name | Rule Summary & Exact Boundary Behavior |
| :---: | :--- | :--- |
| **R1** | **Overnight Shifts** | Shifts spanning midnight (e.g. `22:00–06:00`) are attributed to the shift start calendar date. |
| **R2** | **10-Min Grace Period** | Shift `09:30`: Arrival at `09:40:00` $\rightarrow$ **0m Late**. Arrival at `09:40:01` $\rightarrow$ **10m Late** (counted from shift start `09:30`). |
| **R3** | **Overtime** | Counted only if staying $\ge 30$ minutes past shift end; otherwise **0m**. |
| **R4** | **Work Hours** | $(\text{punch\_out} - \text{punch\_in})$ in seconds / 3600, rounded to 2 decimal places **half-up**. |
| **R5** | **Half Day** | If work hours $< 4.50\text{h}$, record is marked `half_day: true` (counts as `0.5` present day). |
| **R6** | **Presence** | `PRESENT`, `WFH`, and `ON_DUTY` count as present. `ABSENT` and `LEAVE` do not. |
| **R7** | **Working Days** | Monday through Friday. Weekend records add to overtime and late totals. |
| **R8** | **Rounding** | Strict decimal half-up rounding (rates to 4 decimals, hours/metrics to 2 decimals). |
| **R9** | **Headcount** | Includes all active staff who joined on or before month end, even with zero logs. |
| **R10** | **Pagination** | Page starts at 1, max page size is 100, filtered count reflects active filters. |

---

## 📂 Key Architecture Documents

* **[REVIEW.md](REVIEW.md):** Detailed analysis of starter code defects, reproducing symptoms, and applied engineering fixes.
* **[DECISIONS.md](DECISIONS.md):** Written justifications for compound indexes, race condition handling, tie ranks, headcount joins, and 100x scaling strategy.
* **[DATA_MODEL.md](DATA_MODEL.md):** BSON document structures, index definitions, and field types.
* **[openapi.yaml](openapi.yaml):** Authoritative OpenAPI 3.0.3 contract specification.

---

## 👤 Author
**Rakesh Godumala**  
*HROne Employee Attendance & Workforce Analytics System*
