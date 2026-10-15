# DECISIONS.md

1. **Indexes.**
We created unique `employees(emp_code)` and compound `attendance_logs(emp_code, date)` to enforce business key uniqueness and prevent duplicate records. `employees(department, emp_code)` and `employees(joined_on)` back filtered lookups and headcount date-range queries. `attendance_logs(date DESC, emp_code ASC)` serves pagination and sorting, while `(date, late_minutes DESC)` backs the late leaderboard aggregation. These ensure index scans (`IXSCAN`) and eliminate collection scans (`COLLSCAN`).

2. **Punch-in race.**
When two identical punch-in requests arrive simultaneously, both evaluate shift rules and execute atomic inserts. The compound unique index on `(emp_code, date)` serializes write commitment at the storage engine level. Exactly one request commits (HTTP 201). The second raises `DuplicateKeyError`, caught by our handler to return HTTP 409 conflict.

3. **Ties.**
The late leaderboard uses MongoDB's `$rank` window function for standard competition ranking (1, 2, 2, 4). When employees tie at the cutoff rank, both share that rank and are included because filtering requires `rank <= limit`. The next rank is skipped, and tied rows sort by `emp_code` ascending.

4. **Headcount.**
Department summary starts from `employees`, filtering active staff where `joined_on <= month_end`, then performs a `$lookup` into `attendance_logs`. Employees with zero monthly logs remain present with empty log arrays, contributing 1 to headcount and 0 to attendance.

5. **One thing you would change for 100x the data.**
At 100x volume (10M+ records), we would shard `attendance_logs` using a compound hashed shard key `(emp_code, date)` and maintain pre-aggregated daily departmental rollups via MongoDB change streams to eliminate expensive cross-collection multi-stage aggregations over raw historical logs.
