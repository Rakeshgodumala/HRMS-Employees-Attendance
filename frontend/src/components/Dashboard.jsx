import React, { useEffect, useState } from 'react';
import { api } from '../api';

export default function Dashboard({ setActiveTab }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedMonth, setSelectedMonth] = useState('2026-07');
  const [stats, setStats] = useState({
    totalEmployees: 0,
    totalAttendanceRecords: 0,
    departments: [],
    leaderboard: [],
  });

  const loadDashboardData = async (month) => {
    setLoading(true);
    setError(null);
    try {
      const [empRes, attRes, deptRes, leadRes] = await Promise.all([
        api.listEmployees({ page: 1, page_size: 1 }),
        api.listAttendance({ page: 1, page_size: 1 }),
        api.getDepartmentSummary(month),
        api.getLateLeaderboard(month, 5),
      ]);

      setStats({
        totalEmployees: empRes.total || 0,
        totalAttendanceRecords: attRes.total || 0,
        departments: deptRes.items || [],
        leaderboard: leadRes.items || [],
      });
    } catch (err) {
      setError(err.message || 'Failed to load dashboard metrics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardData(selectedMonth);
  }, [selectedMonth]);

  // Aggregate monthly department metrics
  const totalHeadcount = stats.departments.reduce((acc, d) => acc + (d.headcount || 0), 0);
  const totalPresentDays = stats.departments.reduce((acc, d) => acc + (d.present_days || 0), 0);
  const totalLateCount = stats.departments.reduce((acc, d) => acc + (d.late_count || 0), 0);
  const totalLateMinutes = stats.departments.reduce((acc, d) => acc + (d.total_late_minutes || 0), 0);

  return (
    <div className="container-fluid py-4 px-md-4">
      <div className="d-flex flex-wrap justify-content-between align-items-center mb-4 pb-2 border-bottom">
        <div>
          <h1 className="h3 mb-0 text-dark">Executive Attendance Overview</h1>
        </div>
        <div className="d-flex align-items-center gap-2 mt-2 mt-md-0">
          <label htmlFor="dashboardMonth" className="form-label mb-0 small fw-bold">Period (Month):</label>
          <input
            id="dashboardMonth"
            type="month"
            className="form-control form-control-sm"
            value={selectedMonth}
            onChange={(e) => setSelectedMonth(e.target.value)}
            style={{ width: '160px' }}
          />
          <button
            className="btn btn-sm btn-outline-secondary"
            onClick={() => loadDashboardData(selectedMonth)}
            disabled={loading}
          >
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="alert alert-danger d-flex align-items-center" role="alert">
          <div>
            <strong>Error loading dashboard:</strong> {error}
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-center py-5">
          <div className="spinner-border text-primary" role="status">
            <span className="visually-hidden">Loading metrics...</span>
          </div>
          <p className="text-muted mt-2 small">Computing aggregation pipelines...</p>
        </div>
      ) : (
        <>
          {/* Top Metric Cards */}
          <div className="row g-3 mb-4">
            <div className="col-12 col-sm-6 col-lg-3">
              <div className="p-3 stat-card">
                <div className="stat-label">Total Registered Staff</div>
                <div className="stat-value">{stats.totalEmployees}</div>
                <div className="small text-muted mt-1">Total active directory size</div>
              </div>
            </div>
            <div className="col-12 col-sm-6 col-lg-3">
              <div className="p-3 stat-card">
                <div className="stat-label">Month Total Headcount (R9)</div>
                <div className="stat-value">{totalHeadcount}</div>
                <div className="small text-muted mt-1">Eligible joined staff for {selectedMonth}</div>
              </div>
            </div>
            <div className="col-12 col-sm-6 col-lg-3">
              <div className="p-3 stat-card">
                <div className="stat-label">Monthly Present Days (R6)</div>
                <div className="stat-value text-success">{totalPresentDays.toFixed(1)}</div>
                <div className="small text-muted mt-1">Sum of weekday present days</div>
              </div>
            </div>
            <div className="col-12 col-sm-6 col-lg-3">
              <div className="p-3 stat-card">
                <div className="stat-label">Late Arrivals / Minutes</div>
                <div className="stat-value text-danger">
                  {totalLateCount} <span className="fs-6 text-muted fw-normal">({totalLateMinutes}m)</span>
                </div>
                <div className="small text-muted mt-1">Instances exceeding 10m grace (R2)</div>
              </div>
            </div>
          </div>

          {/* Quick Action Navigation Buttons */}
          <div className="card mb-4 border-0 shadow-sm bg-white">
            <div className="card-body d-flex flex-wrap gap-2 justify-content-between align-items-center">
              <div>
                <strong className="d-block">Quick Operational Access</strong>
                <span className="text-muted small">Manage real-time punches, verify audit history, or inspect trends</span>
              </div>
              <div className="d-flex gap-2">
                <button
                  className="btn btn-outline-primary btn-sm"
                  onClick={() => setActiveTab('attendance')}
                >
                  Manage Attendance Records
                </button>
                <button
                  className="btn btn-outline-primary btn-sm"
                  onClick={() => setActiveTab('analytics')}
                >
                  View Department Trends
                </button>
                <button
                  className="btn btn-outline-secondary btn-sm"
                  onClick={() => setActiveTab('correction')}
                >
                  Regularize Punch Record
                </button>
              </div>
            </div>
          </div>

          <div className="row g-4">
            {/* Department Breakdown Table */}
            <div className="col-12 col-lg-7">
              <div className="card border-0 shadow-sm h-100">
                <div className="card-header bg-white py-3 border-bottom d-flex justify-content-between align-items-center">
                  <h2 className="h6 mb-0 text-dark fw-bold">Department Attendance Summary</h2>
                  <span className="badge bg-light text-dark border">{stats.departments.length} Departments</span>
                </div>
                <div className="card-body p-0">
                  {stats.departments.length === 0 ? (
                    <div className="p-4 text-center text-muted">No attendance activity found for {selectedMonth}.</div>
                  ) : (
                    <div className="table-responsive mb-0">
                      <table className="table table-hover align-middle mb-0">
                        <thead>
                          <tr>
                            <th>Department</th>
                            <th className="text-center">Headcount</th>
                            <th className="text-center">Present Days</th>
                            <th className="text-center">Avg Hours</th>
                            <th className="text-center">Late Count</th>
                          </tr>
                        </thead>
                        <tbody>
                          {stats.departments.map((dept) => (
                            <tr key={dept.department}>
                              <td className="fw-medium text-dark">{dept.department}</td>
                              <td className="text-center">{dept.headcount}</td>
                              <td className="text-center">{dept.present_days?.toFixed(2)}</td>
                              <td className="text-center">
                                {dept.avg_work_hours !== null ? `${dept.avg_work_hours.toFixed(2)}h` : '—'}
                              </td>
                              <td className="text-center">
                                {dept.late_count > 0 ? (
                                  <span className="badge bg-warning text-dark">{dept.late_count} ({dept.total_late_minutes}m)</span>
                                ) : (
                                  <span className="badge bg-light text-muted border">0</span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Late Leaderboard Ranking Preview */}
            <div className="col-12 col-lg-5">
              <div className="card border-0 shadow-sm h-100">
                <div className="card-header bg-white py-3 border-bottom d-flex justify-content-between align-items-center">
                  <h2 className="h6 mb-0 text-dark fw-bold">Late Leaderboard (Top 5)</h2>
                  <span className="badge bg-light text-dark border">Ranked with Ties</span>
                </div>
                <div className="card-body p-0">
                  {stats.leaderboard.length === 0 ? (
                    <div className="p-4 text-center text-muted">No late records recorded for this period.</div>
                  ) : (
                    <div className="table-responsive mb-0">
                      <table className="table table-hover align-middle mb-0">
                        <thead>
                          <tr>
                            <th className="text-center">Rank</th>
                            <th>Employee</th>
                            <th>Dept</th>
                            <th className="text-end">Late (Min)</th>
                          </tr>
                        </thead>
                        <tbody>
                          {stats.leaderboard.map((item, idx) => (
                            <tr key={`${item.emp_code}-${idx}`}>
                              <td className="text-center">
                                <span className="badge bg-secondary">#{item.rank}</span>
                              </td>
                              <td>
                                <div className="fw-medium text-dark">{item.name}</div>
                                <div className="text-muted small">{item.emp_code}</div>
                              </td>
                              <td className="small text-muted">{item.department}</td>
                              <td className="text-end fw-bold text-danger">
                                {item.total_late_minutes}m
                                <div className="text-muted fw-normal small">{item.late_count} occurrence(s)</div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
