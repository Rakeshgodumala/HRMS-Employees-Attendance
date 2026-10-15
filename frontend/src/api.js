/**
 * API Service for HROne Employee Attendance & Analytics System
 * Communicates with FastAPI backend on http://localhost:8000
 */

const BASES = [
  import.meta.env.VITE_API_BASE_URL,
  'http://127.0.0.1:8000',
  'http://localhost:8000',
].filter(Boolean);

let currentBaseIndex = 0;

async function request(endpoint, options = {}) {
  const config = {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  };

  // Try candidate bases (handles Windows IPv4 vs IPv6 resolution differences)
  let lastError = null;
  for (let attempt = 0; attempt < BASES.length; attempt++) {
    const base = BASES[(currentBaseIndex + attempt) % BASES.length];
    const url = `${base}${endpoint}`;

    try {
      const res = await fetch(url, config);
      currentBaseIndex = (currentBaseIndex + attempt) % BASES.length; // remember working base
      let data = null;
      const contentType = res.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        data = await res.json();
      } else {
        data = await res.text();
      }

      if (!res.ok) {
        let message = 'An unexpected error occurred';
        if (data && typeof data === 'object') {
          if (data.detail) {
            if (Array.isArray(data.detail)) {
              message = data.detail.map((err) => `${err.loc?.join('.') || 'field'}: ${err.msg}`).join(', ');
            } else {
              message = String(data.detail);
            }
          }
        } else if (typeof data === 'string' && data.length > 0) {
          message = data;
        }
        const error = new Error(message);
        error.status = res.status;
        error.data = data;
        throw error;
      }

      return data;
    } catch (err) {
      if (err.status) throw err; // HTTP error from server (404, 409, 422, etc.)
      lastError = err;
      // Network failure, try next base host
    }
  }

  const netErr = new Error('Could not connect to backend server. Ensure FastAPI is running on port 8000.');
  netErr.status = 503;
  netErr.original = lastError;
  throw netErr;
}

export const api = {
  getHealth: () => request('/health'),

  listEmployees: (params = {}) => {
    const query = new URLSearchParams();
    if (params.department) query.set('department', params.department);
    if (params.page) query.set('page', params.page);
    if (params.page_size) query.set('page_size', params.page_size);
    const qs = query.toString();
    return request(`/employees${qs ? `?${qs}` : ''}`);
  },

  listAttendance: (params = {}) => {
    const query = new URLSearchParams();
    if (params.emp_code) query.set('emp_code', params.emp_code);
    if (params.date_from) query.set('date_from', params.date_from);
    if (params.date_to) query.set('date_to', params.date_to);
    if (params.status) query.set('status', params.status);
    if (params.page) query.set('page', params.page);
    if (params.page_size) query.set('page_size', params.page_size);
    const qs = query.toString();
    return request(`/attendance${qs ? `?${qs}` : ''}`);
  },

  punchIn: (body) => request('/attendance/punch-in', {
    method: 'POST',
    body: JSON.stringify(body),
  }),

  punchOut: (body) => request('/attendance/punch-out', {
    method: 'POST',
    body: JSON.stringify(body),
  }),

  regularizeAttendance: (empCode, date, body) => request(`/attendance/${encodeURIComponent(empCode)}/${encodeURIComponent(date)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  }),

  getEmployeeMonthly: (empCode, month) => {
    return request(`/analytics/employees/${encodeURIComponent(empCode)}/monthly?month=${encodeURIComponent(month)}`);
  },

  getDepartmentSummary: (month, department) => {
    const query = new URLSearchParams({ month });
    if (department) query.set('department', department);
    return request(`/analytics/departments/summary?${query.toString()}`);
  },

  getLateLeaderboard: (month, limit = 10, department) => {
    const query = new URLSearchParams({ month, limit: String(limit) });
    if (department) query.set('department', department);
    return request(`/analytics/leaderboard/late?${query.toString()}`);
  },

  getDepartmentTrend: (department, fromDate, toDate) => {
    const query = new URLSearchParams({ from: fromDate, to: toDate });
    return request(`/analytics/departments/${encodeURIComponent(department)}/trend?${query.toString()}`);
  },
};
