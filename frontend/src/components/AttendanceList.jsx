import React, { useEffect, useMemo, useState } from 'react';
import { api } from '../api';

export default function AttendanceList({ onSelectForCorrection }) {
  const [records, setRecords] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [actionMessage, setActionMessage] = useState(null);

  // Filters & Pagination State
  const [empCodeFilter, setEmpCodeFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // Punch Action Modal/Card State
  const [actionType, setActionType] = useState(null); // 'punch-in' | 'punch-out' | null
  const [actionEmpCode, setActionEmpCode] = useState('');
  const [actionStatus, setActionStatus] = useState('PRESENT');
  const [actionTime, setActionTime] = useState('');
  const [submittingAction, setSubmittingAction] = useState(false);
  const [employeeDirectory, setEmployeeDirectory] = useState([]);

  const empNameMap = useMemo(() => {
    const map = {};
    employeeDirectory.forEach((emp) => {
      map[emp.emp_code] = emp.name;
    });
    return map;
  }, [employeeDirectory]);

  useEffect(() => {
    api.listEmployees({ page: 1, page_size: 100 })
      .then((data) => setEmployeeDirectory(data.items || []))
      .catch(() => {});
  }, []);

  const fetchAttendance = async () => {
    setLoading(true);
    setError(null);
    try {
      let code = empCodeFilter.trim().toUpperCase();
      if (/^\d+$/.test(code)) {
        const num = parseInt(code, 10);
        const formattedNum = num > 1000 ? num - 1000 : num;
        code = `EMP${String(formattedNum).padStart(4, '0')}`;
      }

      const params = {
        page,
        page_size: pageSize,
      };
      if (code) params.emp_code = code;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      if (statusFilter) params.status = statusFilter;

      const data = await api.listAttendance(params);
      setRecords(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.message || 'Failed to load attendance logs');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAttendance();
  }, [page, pageSize]);

  const handleApplyFilter = (e) => {
    e.preventDefault();
    setPage(1);
    fetchAttendance();
  };

  const handleResetFilter = () => {
    setEmpCodeFilter('');
    setDateFrom('');
    setDateTo('');
    setStatusFilter('');
    setPage(1);
    setTimeout(() => fetchAttendance(), 0);
  };

  const formatInstant = (ms) => {
    if (!ms) return '—';
    try {
      // Format as IST time (UTC+5:30)
      const d = new Date(ms);
      return d.toLocaleTimeString('en-IN', {
        timeZone: 'Asia/Kolkata',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      });
    } catch {
      return String(ms);
    }
  };

  const handlePunchSubmit = async (e) => {
    e.preventDefault();
    if (!actionEmpCode.trim()) {
      alert('Please enter employee code');
      return;
    }

    setSubmittingAction(true);
    setActionMessage(null);

    let punchedAtMs = null;
    if (actionTime) {
      // User entered date-time string -> convert to integer epoch ms
      punchedAtMs = Math.floor(new Date(actionTime).getTime());
    }

    let code = actionEmpCode.trim().toUpperCase();
    if (/^\d+$/.test(code)) {
      const num = parseInt(code, 10);
      const formattedNum = num > 1000 ? num - 1000 : num;
      code = `EMP${String(formattedNum).padStart(4, '0')}`;
    }

    try {
      if (actionType === 'punch-in') {
        const payload = {
          emp_code: code,
          status: actionStatus,
        };
        if (punchedAtMs) payload.punched_at = punchedAtMs;

        const res = await api.punchIn(payload);
        setActionMessage({
          type: 'success',
          text: `Punch-in recorded successfully for ${res.emp_code} on ${res.date} (Status: ${res.status}).`,
        });
      } else if (actionType === 'punch-out') {
        const payload = {
          emp_code: code,
        };
        if (punchedAtMs) payload.punched_at = punchedAtMs;

        const res = await api.punchOut(payload);
        setActionMessage({
          type: 'success',
          text: `Punch-out recorded for ${res.emp_code} on ${res.date}. Work hours: ${res.work_hours}h, Overtime: ${res.overtime_minutes}m.`,
        });
      }
      setActionType(null);
      setActionEmpCode('');
      setActionTime('');
      fetchAttendance();
    } catch (err) {
      setActionMessage({
        type: 'danger',
        text: `Error (${err.status || 500}): ${err.message}`,
      });
    } finally {
      setSubmittingAction(false);
    }
  };

  const totalPages = Math.ceil(total / pageSize) || 1;

  const getStatusBadge = (status) => {
    switch (status) {
      case 'PRESENT':
        return <span className="badge badge-status-present">PRESENT</span>;
      case 'WFH':
        return <span className="badge badge-status-wfh">WFH</span>;
      case 'ON_DUTY':
        return <span className="badge badge-status-onduty">ON DUTY</span>;
      case 'ABSENT':
        return <span className="badge badge-status-absent">ABSENT</span>;
      case 'LEAVE':
        return <span className="badge badge-status-leave">LEAVE</span>;
      default:
        return <span className="badge bg-secondary">{status}</span>;
    }
  };

  return (
    <div className="container-fluid py-4 px-md-4">
      <div className="d-flex flex-wrap justify-content-between align-items-center mb-4 pb-2 border-bottom">
        <div>
          <h1 className="h3 mb-1 text-dark">Attendance Management</h1>
          <p className="text-muted small mb-0">Record daily punches, filter attendance logs, and inspect derived metrics</p>
        </div>
        <div className="d-flex gap-2 mt-2 mt-md-0">
          <button
            className="btn btn-success d-flex align-items-center px-3 py-2 shadow-sm rounded-pill fw-semibold"
            onClick={() => {
              setActionType('punch-in');
              setActionMessage(null);
            }}
          >
            <svg
              width="17"
              height="17"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              viewBox="0 0 24 24"
              className="me-2"
            >
              <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
              <polyline points="10 17 15 12 10 7" />
              <line x1="15" y1="12" x2="3" y2="12" />
            </svg>
            Punch In
          </button>
          <button
            className="btn btn-warning d-flex align-items-center px-3 py-2 shadow-sm rounded-pill fw-semibold text-dark"
            onClick={() => {
              setActionType('punch-out');
              setActionMessage(null);
            }}
          >
            <svg
              width="17"
              height="17"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              viewBox="0 0 24 24"
              className="me-2"
            >
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            Punch Out
          </button>
        </div>
      </div>

      {actionMessage && (
        <div className={`alert alert-${actionMessage.type} alert-dismissible fade show`} role="alert">
          {actionMessage.text}
          <button
            type="button"
            className="btn-close"
            onClick={() => setActionMessage(null)}
            aria-label="Close"
          ></button>
        </div>
      )}

      {/* Action Drawer/Card for Punch In/Out */}
      {actionType && (
        <div className={`card mb-4 border-${actionType === 'punch-in' ? 'success' : 'warning'} shadow-sm`}>
          <div
            className={`card-header ${
              actionType === 'punch-in' ? 'bg-success text-white' : 'bg-warning text-dark'
            } d-flex justify-content-between align-items-center py-2`}
          >
            <div className="d-flex align-items-center fw-bold">
              {actionType === 'punch-in' ? (
                <>
                  <svg
                    width="18"
                    height="18"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    viewBox="0 0 24 24"
                    className="me-2"
                  >
                    <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
                    <polyline points="10 17 15 12 10 7" />
                    <line x1="15" y1="12" x2="3" y2="12" />
                  </svg>
                  Record Shift Punch-In
                </>
              ) : (
                <>
                  <svg
                    width="18"
                    height="18"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    viewBox="0 0 24 24"
                    className="me-2"
                  >
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                    <polyline points="16 17 21 12 16 7" />
                    <line x1="21" y1="12" x2="9" y2="12" />
                  </svg>
                  Record Shift Punch-Out
                </>
              )}
            </div>
            <button
              className={`btn btn-sm btn-close ${actionType === 'punch-in' ? 'btn-close-white' : ''}`}
              onClick={() => setActionType(null)}
              aria-label="Close"
            ></button>
          </div>
          <div className="card-body">
            <form onSubmit={handlePunchSubmit} className="row g-3">
              <div className="col-12 col-md-4">
                <label className="form-label small fw-bold">Employee Code *</label>
                <input
                  type="text"
                  className="form-control form-control-sm"
                  placeholder="e.g. EMP0001 or 1"
                  list="employeeDirectoryList"
                  value={actionEmpCode}
                  onChange={(e) => setActionEmpCode(e.target.value)}
                  required
                />
                <span className="text-muted" style={{ fontSize: '0.75rem' }}>
                  Choose from directory (EMP0001 – EMP0006)
                </span>
              </div>

              {actionType === 'punch-in' && (
                <div className="col-12 col-md-4">
                  <label className="form-label small fw-bold">Presence Status</label>
                  <select
                    className="form-select form-select-sm"
                    value={actionStatus}
                    onChange={(e) => setActionStatus(e.target.value)}
                  >
                    <option value="PRESENT">PRESENT (On-site)</option>
                    <option value="WFH">WFH (Work From Home)</option>
                    <option value="ON_DUTY">ON_DUTY (Official Travel)</option>
                  </select>
                </div>
              )}

              <div className="col-12 col-md-4">
                <label className="form-label small fw-bold">
                  Punched At (Optional Instant)
                </label>
                <input
                  type="datetime-local"
                  className="form-control form-control-sm"
                  value={actionTime}
                  onChange={(e) => setActionTime(e.target.value)}
                />
                <span className="text-muted" style={{ fontSize: '0.75rem' }}>
                  Leave blank to use current server clock.
                </span>
              </div>

              <div className="col-12 d-flex justify-content-end gap-2 mt-3">
                <button
                  type="button"
                  className="btn btn-sm btn-outline-secondary"
                  onClick={() => setActionType(null)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-sm btn-primary"
                  disabled={submittingAction}
                >
                  {submittingAction ? 'Submitting...' : 'Submit Punch'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Filter Toolbar */}
      <div className="card border-0 shadow-sm mb-4">
        <div className="card-body py-3">
          <form onSubmit={handleApplyFilter} className="row g-2 align-items-end">
            <div className="col-12 col-sm-6 col-md-3">
              <label className="form-label small fw-bold mb-1">Employee Code</label>
              <input
                type="text"
                className="form-control form-control-sm"
                placeholder="e.g. EMP0001 or 1"
                list="employeeDirectoryList"
                value={empCodeFilter}
                onChange={(e) => setEmpCodeFilter(e.target.value)}
              />
              {/* Global datalist for employee selection */}
              <datalist id="employeeDirectoryList">
                {employeeDirectory.map((emp) => (
                  <option key={emp.emp_code} value={emp.emp_code}>
                    {emp.name} ({emp.department})
                  </option>
                ))}
              </datalist>
            </div>
            <div className="col-6 col-sm-3 col-md-2">
              <label className="form-label small fw-bold mb-1">Date From</label>
              <input
                type="date"
                className="form-control form-control-sm"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
            </div>
            <div className="col-6 col-sm-3 col-md-2">
              <label className="form-label small fw-bold mb-1">Date To</label>
              <input
                type="date"
                className="form-control form-control-sm"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
            </div>
            <div className="col-12 col-sm-4 col-md-2">
              <label className="form-label small fw-bold mb-1">Status</label>
              <select
                className="form-select form-select-sm"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="">All Statuses</option>
                <option value="PRESENT">PRESENT</option>
                <option value="WFH">WFH</option>
                <option value="ON_DUTY">ON_DUTY</option>
                <option value="ABSENT">ABSENT</option>
                <option value="LEAVE">LEAVE</option>
              </select>
            </div>
            <div className="col-12 col-sm-8 col-md-3 d-flex gap-2">
              <button type="submit" className="btn btn-primary btn-sm flex-grow-1">
                Filter
              </button>
              <button
                type="button"
                className="btn btn-outline-secondary btn-sm"
                onClick={handleResetFilter}
              >
                Reset
              </button>
            </div>
          </form>
        </div>
      </div>

      {error && (
        <div className="alert alert-danger" role="alert">
          {error}
        </div>
      )}

      {/* Attendance Table */}
      <div className="card border-0 shadow-sm">
        <div className="card-header bg-white py-3 border-bottom d-flex justify-content-between align-items-center">
          <div>
            <strong className="text-dark">Attendance Records</strong>
            <span className="text-muted small ms-2">({total} total found)</span>
          </div>
          <div className="d-flex align-items-center gap-2">
            <span className="small text-muted">Page Size:</span>
            <select
              className="form-select form-select-sm"
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(1);
              }}
              style={{ width: '80px' }}
            >
              <option value="10">10</option>
              <option value="20">20</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
          </div>
        </div>

        <div className="card-body p-0">
          {loading ? (
            <div className="text-center py-5">
              <div className="spinner-border text-primary" role="status">
                <span className="visually-hidden">Loading...</span>
              </div>
            </div>
          ) : records.length === 0 ? (
            <div className="p-5 text-center text-muted">
              No attendance records match the selected criteria.
            </div>
          ) : (
            <div className="table-responsive">
              <table className="table table-hover align-middle mb-0">
                <thead>
                  <tr>
                    <th>Emp Code</th>
                    <th>Emp Name</th>
                    <th>Date (IST)</th>
                    <th>Status</th>
                    <th>Punch In</th>
                    <th>Punch Out</th>
                    <th className="text-center">Hours</th>
                    <th className="text-center">Late</th>
                    <th className="text-center">Overtime</th>
                    <th className="text-center">Half Day</th>
                    <th className="text-end">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((r) => (
                    <tr key={`${r.emp_code}-${r.date}`}>
                      <td className="fw-semibold text-primary">{r.emp_code}</td>
                      <td className="fw-medium text-dark">{empNameMap[r.emp_code] || '—'}</td>
                      <td>{r.date}</td>
                      <td>{getStatusBadge(r.status)}</td>
                      <td>{formatInstant(r.punch_in)}</td>
                      <td>{formatInstant(r.punch_out)}</td>
                      <td className="text-center">
                        {r.work_hours !== null && r.work_hours !== undefined ? (
                          <span className="fw-medium">{r.work_hours.toFixed(2)}h</span>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                      <td className="text-center">
                        {r.late_minutes > 0 ? (
                          <span className="badge bg-danger-subtle text-danger border border-danger-subtle">
                            {r.late_minutes}m
                          </span>
                        ) : (
                          <span className="text-muted">0</span>
                        )}
                      </td>
                      <td className="text-center">
                        {r.overtime_minutes > 0 ? (
                          <span className="badge bg-success-subtle text-success border border-success-subtle">
                            +{r.overtime_minutes}m
                          </span>
                        ) : (
                          <span className="text-muted">0</span>
                        )}
                      </td>
                      <td className="text-center">
                        {r.half_day ? (
                          <span className="badge bg-warning text-dark">Half Day</span>
                        ) : (
                          <span className="text-muted">No</span>
                        )}
                      </td>
                      <td className="text-end">
                        <button
                          className="btn btn-outline-secondary btn-sm py-0 px-2"
                          onClick={() => onSelectForCorrection(r.emp_code, r.date)}
                          title="Regularize / Correct this record"
                        >
                          Correct
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Pagination Bar */}
        <div className="card-footer bg-white d-flex flex-wrap justify-content-between align-items-center py-2">
          <span className="small text-muted mb-2 mb-md-0">
            Showing Page {page} of {totalPages} ({total} records total)
          </span>
          <div className="btn-group btn-group-sm">
            <button
              className="btn btn-outline-secondary"
              disabled={page <= 1 || loading}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </button>
            <button
              className="btn btn-outline-secondary"
              disabled={page >= totalPages || loading}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
