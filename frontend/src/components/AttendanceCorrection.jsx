import React, { useEffect, useState } from 'react';
import { api } from '../api';

export default function AttendanceCorrection({ prefillEmpCode, prefillDate }) {
  const [empCode, setEmpCode] = useState(prefillEmpCode || '');
  const [date, setDate] = useState(prefillDate || '');

  // Current record state
  const [loadingCurrent, setLoadingCurrent] = useState(false);
  const [currentRecord, setCurrentRecord] = useState(null);
  const [fetchError, setFetchError] = useState(null);

  // Form inputs for regularization
  const [newStatus, setNewStatus] = useState('');
  const [newPunchInTime, setNewPunchInTime] = useState('');
  const [newPunchOutTime, setNewPunchOutTime] = useState('');
  const [reason, setReason] = useState('');
  const [regularizedBy, setRegularizedBy] = useState('hr.admin');

  // Submit status
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [submitSuccess, setSubmitSuccess] = useState(null);

  const formatInstantToLocal = (ms) => {
    if (!ms) return '';
    try {
      const d = new Date(ms);
      // Format to YYYY-MM-DDTHH:mm for datetime-local input
      const year = d.getFullYear();
      const month = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      const hours = String(d.getHours()).padStart(2, '0');
      const minutes = String(d.getMinutes()).padStart(2, '0');
      return `${year}-${month}-${day}T${hours}:${minutes}`;
    } catch {
      return '';
    }
  };

  const formatInstantDisplay = (ms) => {
    if (!ms) return '—';
    try {
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

  const loadRecord = async (targetEmp, targetDate) => {
    if (!targetEmp || !targetDate) return;
    setLoadingCurrent(true);
    setFetchError(null);
    setSubmitSuccess(null);
    setSubmitError(null);

    try {
      const res = await api.listAttendance({
        emp_code: targetEmp.trim().toUpperCase(),
        date_from: targetDate,
        date_to: targetDate,
        page_size: 1,
      });

      if (res.items && res.items.length > 0) {
        const doc = res.items[0];
        setCurrentRecord(doc);
        setNewStatus(doc.status || 'PRESENT');
        setNewPunchInTime(formatInstantToLocal(doc.punch_in));
        setNewPunchOutTime(formatInstantToLocal(doc.punch_out));
      } else {
        setCurrentRecord(null);
        setFetchError(`No attendance log found for ${targetEmp} on ${targetDate}.`);
      }
    } catch (err) {
      setFetchError(err.message || 'Failed to retrieve attendance record');
    } finally {
      setLoadingCurrent(false);
    }
  };

  useEffect(() => {
    if (prefillEmpCode && prefillDate) {
      setEmpCode(prefillEmpCode);
      setDate(prefillDate);
      loadRecord(prefillEmpCode, prefillDate);
    }
  }, [prefillEmpCode, prefillDate]);

  const handleLookup = (e) => {
    e.preventDefault();
    if (!empCode || !date) {
      alert('Please enter both Employee Code and Attendance Date');
      return;
    }
    loadRecord(empCode, date);
  };

  const handleRegularizeSubmit = async (e) => {
    e.preventDefault();
    if (!reason.trim() || reason.trim().length < 5) {
      alert('Reason must be at least 5 characters long.');
      return;
    }
    if (!regularizedBy.trim()) {
      alert('Regularized By (actor) is required.');
      return;
    }

    setSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);

    const payload = {
      reason: reason.trim(),
      regularized_by: regularizedBy.trim(),
    };

    if (newStatus && newStatus !== currentRecord?.status) {
      payload.status = newStatus;
    }

    if (newStatus === 'ABSENT' || newStatus === 'LEAVE') {
      // Per contract, ABSENT or LEAVE clears punches and does not send them
    } else {
      if (newPunchInTime) {
        const inMs = Math.floor(new Date(newPunchInTime).getTime());
        if (inMs !== currentRecord?.punch_in) {
          payload.punch_in = inMs;
        }
      }
      if (newPunchOutTime) {
        const outMs = Math.floor(new Date(newPunchOutTime).getTime());
        if (outMs !== currentRecord?.punch_out) {
          payload.punch_out = outMs;
        }
      }
    }

    if (!payload.status && payload.punch_in === undefined && payload.punch_out === undefined) {
      setSubmitError('No changes detected. Regularization requires modifying at least one field (Target Status, Punch In, or Punch Out).');
      setSubmitting(false);
      return;
    }

    try {
      const updated = await api.regularizeAttendance(empCode.trim().toUpperCase(), date, payload);
      setCurrentRecord(updated);
      setSubmitSuccess('Record regularized successfully. Derived metrics recomputed and audit trail appended.');
      setReason('');
    } catch (err) {
      setSubmitError(`Correction rejected (${err.status || 400}): ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="container-fluid py-4 px-md-4">
      <div className="mb-4 pb-2 border-bottom">
        <h1 className="h3 mb-1 text-dark">Attendance Regularization (Manual Correction)</h1>
        <p className="text-muted small mb-0">Address records by (emp_code, date), recompute derived fields, and append immutable audit history</p>
      </div>

      {/* Record Selector */}
      <div className="card border-0 shadow-sm mb-4">
        <div className="card-body py-3">
          <form onSubmit={handleLookup} className="row g-2 align-items-end">
            <div className="col-12 col-sm-5 col-md-4">
              <label className="form-label small fw-bold mb-1">Employee Code *</label>
              <input
                type="text"
                className="form-control form-control-sm"
                placeholder="e.g. EMP0001"
                value={empCode}
                onChange={(e) => setEmpCode(e.target.value)}
                required
              />
            </div>
            <div className="col-12 col-sm-5 col-md-4">
              <label className="form-label small fw-bold mb-1">Attendance Date (YYYY-MM-DD) *</label>
              <input
                type="date"
                className="form-control form-control-sm"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
              />
            </div>
            <div className="col-12 col-sm-2 col-md-4">
              <button
                type="submit"
                className="btn btn-primary btn-sm w-100"
                disabled={loadingCurrent}
              >
                {loadingCurrent ? 'Fetching...' : 'Load Record for Correction'}
              </button>
            </div>
          </form>
        </div>
      </div>

      {fetchError && (
        <div className="alert alert-warning" role="alert">
          {fetchError}
        </div>
      )}

      {submitSuccess && (
        <div className="alert alert-success alert-dismissible fade show" role="alert">
          {submitSuccess}
          <button type="button" className="btn-close" onClick={() => setSubmitSuccess(null)}></button>
        </div>
      )}

      {submitError && (
        <div className="alert alert-danger" role="alert">
          {submitError}
        </div>
      )}

      {currentRecord && (
        <div className="row g-4">
          {/* Edit Form */}
          <div className="col-12 col-lg-7">
            <div className="card border-0 shadow-sm">
              <div className="card-header bg-white py-3 border-bottom d-flex justify-content-between align-items-center">
                <h2 className="h6 mb-0 text-dark fw-bold">
                  Editing: {currentRecord.emp_code} on {currentRecord.date}
                </h2>
                <span className="badge bg-secondary">Status: {currentRecord.status}</span>
              </div>
              <div className="card-body">
                <form onSubmit={handleRegularizeSubmit}>
                  <div className="mb-3">
                    <label className="form-label small fw-bold">Target Status</label>
                    <select
                      className="form-select form-select-sm"
                      value={newStatus}
                      onChange={(e) => setNewStatus(e.target.value)}
                    >
                      <option value="PRESENT">PRESENT (Worked on site)</option>
                      <option value="WFH">WFH (Worked from home)</option>
                      <option value="ON_DUTY">ON_DUTY (Official duty)</option>
                      <option value="ABSENT">ABSENT (Clears punches)</option>
                      <option value="LEAVE">LEAVE (Approved leave - clears punches)</option>
                    </select>
                  </div>

                  {newStatus !== 'ABSENT' && newStatus !== 'LEAVE' && (
                    <div className="row g-3 mb-3">
                      <div className="col-12 col-sm-6">
                        <label className="form-label small fw-bold">Punch In Instant</label>
                        <input
                          type="datetime-local"
                          className="form-control form-control-sm"
                          value={newPunchInTime}
                          onChange={(e) => setNewPunchInTime(e.target.value)}
                        />
                        <span className="text-muted" style={{ fontSize: '0.75rem' }}>
                          Current: {formatInstantDisplay(currentRecord.punch_in)} IST
                        </span>
                      </div>
                      <div className="col-12 col-sm-6">
                        <label className="form-label small fw-bold">Punch Out Instant</label>
                        <input
                          type="datetime-local"
                          className="form-control form-control-sm"
                          value={newPunchOutTime}
                          onChange={(e) => setNewPunchOutTime(e.target.value)}
                        />
                        <span className="text-muted" style={{ fontSize: '0.75rem' }}>
                          Current: {formatInstantDisplay(currentRecord.punch_out)} IST
                        </span>
                      </div>
                    </div>
                  )}

                  <div className="mb-3">
                    <label className="form-label small fw-bold">Reason for Regularization *</label>
                    <textarea
                      className="form-control form-control-sm"
                      rows="2"
                      placeholder="e.g. Biometric device scanner synchronization delay"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      minLength={5}
                      maxLength={200}
                      required
                    ></textarea>
                    <span className="text-muted" style={{ fontSize: '0.75rem' }}>
                      Required by contract (5–200 characters).
                    </span>
                  </div>

                  <div className="mb-3">
                    <label className="form-label small fw-bold">Authorized By (Actor) *</label>
                    <input
                      type="text"
                      className="form-control form-control-sm"
                      value={regularizedBy}
                      onChange={(e) => setRegularizedBy(e.target.value)}
                      placeholder="e.g. hr.manager"
                      maxLength={50}
                      required
                    />
                  </div>

                  <div className="d-flex justify-content-end gap-2 mt-4">
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-secondary"
                      onClick={() => loadRecord(empCode, date)}
                    >
                      Reset Form
                    </button>
                    <button
                      type="submit"
                      className="btn btn-sm btn-primary px-4"
                      disabled={submitting}
                    >
                      {submitting ? 'Applying Changes...' : 'Save & Append Audit Entry'}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>

          {/* Derived Values & Audit History Panel */}
          <div className="col-12 col-lg-5">
            {/* Derived values card */}
            <div className="card border-0 shadow-sm mb-4">
              <div className="card-header bg-white py-3 border-bottom">
                <h3 className="h6 mb-0 text-dark fw-bold">Active Derived Metrics (Authoritative)</h3>
              </div>
              <div className="card-body">
                <div className="row g-2 text-center">
                  <div className="col-6 col-sm-3">
                    <div className="p-2 border rounded bg-light">
                      <div className="small text-muted">Work Hours</div>
                      <div className="fw-bold">{currentRecord.work_hours !== null ? `${currentRecord.work_hours}h` : '—'}</div>
                    </div>
                  </div>
                  <div className="col-6 col-sm-3">
                    <div className="p-2 border rounded bg-light">
                      <div className="small text-muted">Late Mins</div>
                      <div className="fw-bold text-danger">{currentRecord.late_minutes}m</div>
                    </div>
                  </div>
                  <div className="col-6 col-sm-3">
                    <div className="p-2 border rounded bg-light">
                      <div className="small text-muted">Overtime</div>
                      <div className="fw-bold text-success">{currentRecord.overtime_minutes}m</div>
                    </div>
                  </div>
                  <div className="col-6 col-sm-3">
                    <div className="p-2 border rounded bg-light">
                      <div className="small text-muted">Half Day</div>
                      <div className="fw-bold">{currentRecord.half_day ? 'Yes' : 'No'}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Audit History Timeline */}
            <div className="card border-0 shadow-sm">
              <div className="card-header bg-white py-3 border-bottom d-flex justify-content-between align-items-center">
                <h3 className="h6 mb-0 text-dark fw-bold">Audit History (Immutable)</h3>
                <span className="badge bg-light text-dark border">
                  {currentRecord.history?.length || 0} entry(s)
                </span>
              </div>
              <div className="card-body p-0">
                {!currentRecord.history || currentRecord.history.length === 0 ? (
                  <div className="p-4 text-center text-muted small">
                    No manual corrections have been made to this record.
                  </div>
                ) : (
                  <div className="list-group list-group-flush">
                    {currentRecord.history.map((hist, idx) => (
                      <div key={idx} className="list-group-item p-3">
                        <div className="d-flex justify-content-between align-items-center mb-1">
                          <strong className="text-primary small">{hist.by || 'Anonymous'}</strong>
                          <span className="text-muted small">
                            {formatInstantDisplay(hist.at)} IST
                          </span>
                        </div>
                        <p className="mb-2 text-dark small fst-italic">"{hist.reason}"</p>

                        <div className="bg-light p-2 rounded small">
                          <div className="fw-semibold text-muted mb-1" style={{ fontSize: '0.75rem' }}>CHANGES RECORDED:</div>
                          {Object.entries(hist.changes || {}).map(([field, delta]) => (
                            <div key={field} className="d-flex justify-content-between">
                              <span className="text-secondary">{field}:</span>
                              <span>
                                <span className="history-diff-from">
                                  {field.includes('punch') ? formatInstantDisplay(delta.from) : String(delta.from ?? 'null')}
                                </span>
                                <span>→</span>
                                <span className="history-diff-to ms-1">
                                  {field.includes('punch') ? formatInstantDisplay(delta.to) : String(delta.to ?? 'null')}
                                </span>
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
