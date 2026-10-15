import React, { useEffect, useState } from 'react';
import { api } from '../api';

export default function Analytics() {
  const [subTab, setSubTab] = useState('trend'); // 'trend' | 'leaderboard' | 'dept_summary' | 'employee_monthly'

  // Department Trend State
  const [trendDept, setTrendDept] = useState('Engineering');
  const [trendFrom, setTrendFrom] = useState('2026-07-01');
  const [trendTo, setTrendTo] = useState('2026-07-14');
  const [trendData, setTrendData] = useState(null);
  const [trendLoading, setTrendLoading] = useState(false);
  const [trendError, setTrendError] = useState(null);

  // Late Leaderboard State
  const [leadMonth, setLeadMonth] = useState('2026-07');
  const [leadLimit, setLeadLimit] = useState(10);
  const [leadDept, setLeadDept] = useState('');
  const [leadData, setLeadData] = useState(null);
  const [leadLoading, setLeadLoading] = useState(false);
  const [leadError, setLeadError] = useState(null);

  // Department Summary State
  const [summaryMonth, setSummaryMonth] = useState('2026-07');
  const [summaryDept, setSummaryDept] = useState('');
  const [summaryData, setSummaryData] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState(null);

  // Employee Monthly State
  const [empCode, setEmpCode] = useState('EMP0001');
  const [empMonth, setEmpMonth] = useState('2026-07');
  const [empData, setEmpData] = useState(null);
  const [empLoading, setEmpLoading] = useState(false);
  const [empError, setEmpError] = useState(null);

  // Load Department Trend
  const fetchTrend = async () => {
    if (!trendDept || !trendFrom || !trendTo) return;
    setTrendLoading(true);
    setTrendError(null);
    try {
      const data = await api.getDepartmentTrend(trendDept, trendFrom, trendTo);
      setTrendData(data);
    } catch (err) {
      setTrendError(err.message || 'Failed to fetch trend analytics');
    } finally {
      setTrendLoading(false);
    }
  };

  // Load Leaderboard
  const fetchLeaderboard = async () => {
    if (!leadMonth) return;
    setLeadLoading(true);
    setLeadError(null);
    try {
      const data = await api.getLateLeaderboard(leadMonth, leadLimit, leadDept || undefined);
      setLeadData(data);
    } catch (err) {
      setLeadError(err.message || 'Failed to fetch late leaderboard');
    } finally {
      setLeadLoading(false);
    }
  };

  // Load Department Summary
  const fetchDeptSummary = async () => {
    if (!summaryMonth) return;
    setSummaryLoading(true);
    setSummaryError(null);
    try {
      const data = await api.getDepartmentSummary(summaryMonth, summaryDept || undefined);
      setSummaryData(data);
    } catch (err) {
      setSummaryError(err.message || 'Failed to fetch department summary');
    } finally {
      setSummaryLoading(false);
    }
  };

  // Load Employee Monthly
  const fetchEmployeeMonthly = async () => {
    if (!empCode || !empMonth) return;
    setEmpLoading(true);
    setEmpError(null);
    try {
      const data = await api.getEmployeeMonthly(empCode.trim().toUpperCase(), empMonth);
      setEmpData(data);
    } catch (err) {
      setEmpError(err.message || 'Failed to fetch employee monthly summary');
    } finally {
      setEmpLoading(false);
    }
  };

  useEffect(() => {
    if (subTab === 'trend' && !trendData) fetchTrend();
    if (subTab === 'leaderboard' && !leadData) fetchLeaderboard();
    if (subTab === 'dept_summary' && !summaryData) fetchDeptSummary();
    if (subTab === 'employee_monthly' && !empData) fetchEmployeeMonthly();
  }, [subTab]);

  return (
    <div className="container-fluid py-4 px-md-4">
      <div className="mb-4 pb-2 border-bottom">
        <h1 className="h3 mb-1 text-dark">Enterprise Analytics & Reports</h1>
        <p className="text-muted small mb-0">Workforce attendance insights, punctuality trends, and department analytics</p>
      </div>

      {/* Sub Tabs Navigation */}
      <ul className="nav nav-pills mb-4 gap-2">
        <li className="nav-item">
          <button
            className={`nav-link ${subTab === 'trend' ? 'active' : ''}`}
            onClick={() => setSubTab('trend')}
          >
            Department Daily Trend (7-Day Average)
          </button>
        </li>
        <li className="nav-item">
          <button
            className={`nav-link ${subTab === 'leaderboard' ? 'active' : ''}`}
            onClick={() => setSubTab('leaderboard')}
          >
            Late Leaderboard (Punctuality Rankings)
          </button>
        </li>
        <li className="nav-item">
          <button
            className={`nav-link ${subTab === 'dept_summary' ? 'active' : ''}`}
            onClick={() => setSubTab('dept_summary')}
          >
            Department Monthly Summary
          </button>
        </li>
        <li className="nav-item">
          <button
            className={`nav-link ${subTab === 'employee_monthly' ? 'active' : ''}`}
            onClick={() => setSubTab('employee_monthly')}
          >
            Employee Monthly Breakdown
          </button>
        </li>
      </ul>

      {/* ----------------- SUB-TAB 1: DEPARTMENT TREND ----------------- */}
      {subTab === 'trend' && (
        <div className="card border-0 shadow-sm">
          <div className="card-header bg-white py-3 border-bottom">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                fetchTrend();
              }}
              className="row g-2 align-items-end"
            >
              <div className="col-12 col-sm-4 col-md-3">
                <label className="form-label small fw-bold mb-1">Department</label>
                <input
                  type="text"
                  className="form-control form-control-sm"
                  value={trendDept}
                  onChange={(e) => setTrendDept(e.target.value)}
                  placeholder="e.g. Engineering"
                  required
                />
              </div>
              <div className="col-6 col-sm-3 col-md-3">
                <label className="form-label small fw-bold mb-1">From Date (IST)</label>
                <input
                  type="date"
                  className="form-control form-control-sm"
                  value={trendFrom}
                  onChange={(e) => setTrendFrom(e.target.value)}
                  required
                />
              </div>
              <div className="col-6 col-sm-3 col-md-3">
                <label className="form-label small fw-bold mb-1">To Date (IST)</label>
                <input
                  type="date"
                  className="form-control form-control-sm"
                  value={trendTo}
                  onChange={(e) => setTrendTo(e.target.value)}
                  required
                />
              </div>
              <div className="col-12 col-sm-2 col-md-3">
                <button
                  type="submit"
                  className="btn btn-primary btn-sm w-100"
                  disabled={trendLoading}
                >
                  {trendLoading ? 'Generating...' : 'Calculate Trend'}
                </button>
              </div>
            </form>
          </div>

          <div className="card-body p-0">
            {trendError && (
              <div className="alert alert-danger m-3 mb-0" role="alert">
                {trendError}
              </div>
            )}

            {trendLoading ? (
              <div className="text-center py-5">
                <div className="spinner-border text-primary" role="status">
                  <span className="visually-hidden">Loading...</span>
                </div>
              </div>
            ) : !trendData || !trendData.items ? (
              <div className="p-4 text-center text-muted">Select department and dates to view daily trend.</div>
            ) : (
              <div className="table-responsive">
                <table className="table table-hover align-middle mb-0">
                  <thead>
                    <tr>
                      <th>Calendar Date</th>
                      <th className="text-center">Working Day</th>
                      <th className="text-center">Headcount (R9)</th>
                      <th className="text-center">Present Count</th>
                      <th className="text-center">Late Count</th>
                      <th className="text-center">Attendance Rate</th>
                      <th style={{ minWidth: '180px' }}>7-Day Moving Avg</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trendData.items.map((row) => (
                      <tr key={row.date}>
                        <td className="fw-medium">{row.date}</td>
                        <td className="text-center">
                          {row.is_working_day ? (
                            <span className="badge bg-primary-subtle text-primary border border-primary-subtle">
                              Weekday
                            </span>
                          ) : (
                            <span className="badge bg-light text-muted border">Weekend</span>
                          )}
                        </td>
                        <td className="text-center">{row.headcount}</td>
                        <td className="text-center">{row.present_count.toFixed(1)}</td>
                        <td className="text-center">
                          {row.late_count > 0 ? (
                            <span className="badge bg-danger-subtle text-danger">{row.late_count}</span>
                          ) : (
                            '0'
                          )}
                        </td>
                        <td className="text-center font-monospace">
                          {row.attendance_rate !== null ? (
                            <span>{(row.attendance_rate * 100).toFixed(2)}%</span>
                          ) : (
                            <span className="text-muted">—</span>
                          )}
                        </td>
                        <td>
                          {row.moving_avg_7d !== null ? (
                            <div>
                              <div className="d-flex justify-content-between small text-muted mb-1">
                                <span>{(row.moving_avg_7d * 100).toFixed(2)}%</span>
                              </div>
                              <div className="progress" style={{ height: '6px' }}>
                                <div
                                  className="progress-bar bg-success"
                                  role="progressbar"
                                  style={{ width: `${Math.min(100, Math.max(0, row.moving_avg_7d * 100))}%` }}
                                ></div>
                              </div>
                            </div>
                          ) : (
                            <span className="text-muted small">—</span>
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
      )}

      {/* ----------------- SUB-TAB 2: LATE LEADERBOARD ----------------- */}
      {subTab === 'leaderboard' && (
        <div className="card border-0 shadow-sm">
          <div className="card-header bg-white py-3 border-bottom">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                fetchLeaderboard();
              }}
              className="row g-2 align-items-end"
            >
              <div className="col-12 col-sm-4 col-md-3">
                <label className="form-label small fw-bold mb-1">Month</label>
                <input
                  type="month"
                  className="form-control form-control-sm"
                  value={leadMonth}
                  onChange={(e) => setLeadMonth(e.target.value)}
                  required
                />
              </div>
              <div className="col-6 col-sm-3 col-md-3">
                <label className="form-label small fw-bold mb-1">Limit (Top N)</label>
                <input
                  type="number"
                  min="1"
                  max="50"
                  className="form-control form-control-sm"
                  value={leadLimit}
                  onChange={(e) => setLeadLimit(Number(e.target.value))}
                />
              </div>
              <div className="col-6 col-sm-3 col-md-3">
                <label className="form-label small fw-bold mb-1">Filter Dept (Optional)</label>
                <input
                  type="text"
                  className="form-control form-control-sm"
                  value={leadDept}
                  onChange={(e) => setLeadDept(e.target.value)}
                  placeholder="All Departments"
                />
              </div>
              <div className="col-12 col-sm-2 col-md-3">
                <button
                  type="submit"
                  className="btn btn-primary btn-sm w-100"
                  disabled={leadLoading}
                >
                  {leadLoading ? 'Ranking...' : 'Generate Ranking'}
                </button>
              </div>
            </form>
          </div>

          <div className="card-body p-0">
            {leadError && (
              <div className="alert alert-danger m-3 mb-0" role="alert">
                {leadError}
              </div>
            )}

            {leadLoading ? (
              <div className="text-center py-5">
                <div className="spinner-border text-primary" role="status">
                  <span className="visually-hidden">Loading...</span>
                </div>
              </div>
            ) : !leadData || !leadData.items || leadData.items.length === 0 ? (
              <div className="p-5 text-center text-muted">
                No late arrivals recorded for this month matching criteria.
              </div>
            ) : (
              <div className="table-responsive">
                <table className="table table-hover align-middle mb-0">
                  <thead>
                    <tr>
                      <th className="text-center" style={{ width: '80px' }}>Rank</th>
                      <th>Emp Code</th>
                      <th>Employee Name</th>
                      <th>Department</th>
                      <th className="text-center">Late Occurrences</th>
                      <th className="text-end">Total Late (Minutes)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {leadData.items.map((r, i) => (
                      <tr key={`${r.emp_code}-${i}`}>
                        <td className="text-center">
                          <span className={`badge ${r.rank === 1 ? 'bg-danger' : r.rank <= 3 ? 'bg-warning text-dark' : 'bg-secondary'}`}>
                            #{r.rank}
                          </span>
                        </td>
                        <td className="fw-semibold text-primary">{r.emp_code}</td>
                        <td className="fw-medium text-dark">{r.name}</td>
                        <td className="text-muted">{r.department}</td>
                        <td className="text-center">{r.late_count}</td>
                        <td className="text-end fw-bold text-danger">{r.total_late_minutes}m</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ----------------- SUB-TAB 3: DEPARTMENT SUMMARY ----------------- */}
      {subTab === 'dept_summary' && (
        <div className="card border-0 shadow-sm">
          <div className="card-header bg-white py-3 border-bottom">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                fetchDeptSummary();
              }}
              className="row g-2 align-items-end"
            >
              <div className="col-12 col-sm-6 col-md-4">
                <label className="form-label small fw-bold mb-1">Month</label>
                <input
                  type="month"
                  className="form-control form-control-sm"
                  value={summaryMonth}
                  onChange={(e) => setSummaryMonth(e.target.value)}
                  required
                />
              </div>
              <div className="col-12 col-sm-6 col-md-4">
                <label className="form-label small fw-bold mb-1">Department (Optional)</label>
                <input
                  type="text"
                  className="form-control form-control-sm"
                  value={summaryDept}
                  onChange={(e) => setSummaryDept(e.target.value)}
                  placeholder="All Departments"
                />
              </div>
              <div className="col-12 col-md-4">
                <button
                  type="submit"
                  className="btn btn-primary btn-sm w-100"
                  disabled={summaryLoading}
                >
                  {summaryLoading ? 'Aggregating...' : 'Fetch Summary'}
                </button>
              </div>
            </form>
          </div>

          <div className="card-body p-0">
            {summaryError && (
              <div className="alert alert-danger m-3 mb-0" role="alert">
                {summaryError}
              </div>
            )}

            {summaryLoading ? (
              <div className="text-center py-5">
                <div className="spinner-border text-primary" role="status">
                  <span className="visually-hidden">Loading...</span>
                </div>
              </div>
            ) : !summaryData || !summaryData.items || summaryData.items.length === 0 ? (
              <div className="p-5 text-center text-muted">
                No department attendance logs available for this period.
              </div>
            ) : (
              <div className="table-responsive">
                <table className="table table-hover align-middle mb-0">
                  <thead>
                    <tr>
                      <th>Department</th>
                      <th className="text-center">Headcount (R9)</th>
                      <th className="text-center">Present Days</th>
                      <th className="text-center">Avg Work Hours</th>
                      <th className="text-center">Late Records</th>
                      <th className="text-center">Total Late Mins</th>
                      <th className="text-center">Leave Days</th>
                      <th className="text-center">On-Duty Records</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summaryData.items.map((d) => (
                      <tr key={d.department}>
                        <td className="fw-semibold text-dark">{d.department}</td>
                        <td className="text-center">{d.headcount}</td>
                        <td className="text-center">{d.present_days?.toFixed(2)}</td>
                        <td className="text-center">
                          {d.avg_work_hours !== null ? `${d.avg_work_hours.toFixed(2)}h` : '—'}
                        </td>
                        <td className="text-center">{d.late_count}</td>
                        <td className="text-center text-danger fw-medium">{d.total_late_minutes}m</td>
                        <td className="text-center">{d.leave_count}</td>
                        <td className="text-center">{d.on_duty_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ----------------- SUB-TAB 4: EMPLOYEE MONTHLY ----------------- */}
      {subTab === 'employee_monthly' && (
        <div className="card border-0 shadow-sm">
          <div className="card-header bg-white py-3 border-bottom">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                fetchEmployeeMonthly();
              }}
              className="row g-2 align-items-end"
            >
              <div className="col-12 col-sm-6 col-md-4">
                <label className="form-label small fw-bold mb-1">Employee Code</label>
                <input
                  type="text"
                  className="form-control form-control-sm"
                  value={empCode}
                  onChange={(e) => setEmpCode(e.target.value)}
                  placeholder="e.g. EMP0001"
                  required
                />
              </div>
              <div className="col-12 col-sm-6 col-md-4">
                <label className="form-label small fw-bold mb-1">Month</label>
                <input
                  type="month"
                  className="form-control form-control-sm"
                  value={empMonth}
                  onChange={(e) => setEmpMonth(e.target.value)}
                  required
                />
              </div>
              <div className="col-12 col-md-4">
                <button
                  type="submit"
                  className="btn btn-primary btn-sm w-100"
                  disabled={empLoading}
                >
                  {empLoading ? 'Calculating...' : 'Query Monthly Record'}
                </button>
              </div>
            </form>
          </div>

          <div className="card-body">
            {empError && (
              <div className="alert alert-danger" role="alert">
                {empError}
              </div>
            )}

            {empLoading ? (
              <div className="text-center py-5">
                <div className="spinner-border text-primary" role="status">
                  <span className="visually-hidden">Loading...</span>
                </div>
              </div>
            ) : !empData ? (
              <div className="p-4 text-center text-muted">
                Enter an employee code and month to inspect individual analytics.
              </div>
            ) : (
              <div>
                <h2 className="h5 fw-bold mb-3 text-dark">
                  Summary for {empData.emp_code} — {empData.month}
                </h2>
                <div className="row g-3">
                  <div className="col-6 col-md-3">
                    <div className="p-3 stat-card">
                      <div className="stat-label">Working Days (Mon-Fri)</div>
                      <div className="stat-value">{empData.working_days}</div>
                      <div className="small text-muted">Eligible from joined_on</div>
                    </div>
                  </div>
                  <div className="col-6 col-md-3">
                    <div className="p-3 stat-card">
                      <div className="stat-label">Present Days</div>
                      <div className="stat-value text-success">{empData.present_days?.toFixed(1)}</div>
                      <div className="small text-muted">Weekday presents (Half day = 0.5)</div>
                    </div>
                  </div>
                  <div className="col-6 col-md-3">
                    <div className="p-3 stat-card">
                      <div className="stat-label">Attendance Rate</div>
                      <div className="stat-value text-primary">
                        {empData.attendance_pct !== null ? `${empData.attendance_pct.toFixed(2)}%` : '—'}
                      </div>
                      <div className="small text-muted">Present / Working Days</div>
                    </div>
                  </div>
                  <div className="col-6 col-md-3">
                    <div className="p-3 stat-card">
                      <div className="stat-label">Leave Days</div>
                      <div className="stat-value text-secondary">{empData.leave_days}</div>
                      <div className="small text-muted">Approved leaves</div>
                    </div>
                  </div>
                  <div className="col-6 col-md-3">
                    <div className="p-3 stat-card">
                      <div className="stat-label">Late Occurrences</div>
                      <div className="stat-value text-danger">{empData.late_count}</div>
                      <div className="small text-muted">Exceeding 10m grace</div>
                    </div>
                  </div>
                  <div className="col-6 col-md-3">
                    <div className="p-3 stat-card">
                      <div className="stat-label">Total Late Minutes</div>
                      <div className="stat-value text-danger">{empData.total_late_minutes}m</div>
                      <div className="small text-muted">Sum of late minutes</div>
                    </div>
                  </div>
                  <div className="col-6 col-md-3">
                    <div className="p-3 stat-card">
                      <div className="stat-label">Total Overtime</div>
                      <div className="stat-value text-success">{empData.total_overtime_minutes}m</div>
                      <div className="small text-muted">Overtime &gt;= 30m</div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
