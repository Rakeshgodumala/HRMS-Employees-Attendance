import React from 'react';

export default function Navbar({ activeTab, setActiveTab }) {
  return (
    <header className="navbar navbar-expand-lg navbar-dark bg-success px-3 shadow-sm border-bottom border-success-subtle">
      <div className="container-fluid">
        <span className="navbar-brand d-flex align-items-center me-4">
          <svg
            width="22"
            height="22"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            viewBox="0 0 24 24"
            className="me-2"
          >
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
            <line x1="16" y1="2" x2="16" y2="6" />
            <line x1="8" y1="2" x2="8" y2="6" />
            <line x1="3" y1="10" x2="21" y2="10" />
          </svg>
          <span className="fw-bold tracking-tight text-white">HROne Attendance</span>
        </span>

        <button
          className="navbar-toggler border-0"
          type="button"
          data-bs-toggle="collapse"
          data-bs-target="#navbarMenu"
          aria-controls="navbarMenu"
          aria-expanded="false"
          aria-label="Toggle navigation"
        >
          <span className="navbar-toggler-icon"></span>
        </button>

        <div className="collapse navbar-collapse" id="navbarMenu">
          <ul className="navbar-nav me-auto mb-2 mb-lg-0 gap-1">
            <li className="nav-item">
              <button
                className={`nav-link btn btn-link text-decoration-none px-3 py-1 rounded-pill ${
                  activeTab === 'dashboard'
                    ? 'active bg-white text-success fw-bold shadow-sm'
                    : 'text-white text-opacity-90 fw-medium'
                }`}
                onClick={() => setActiveTab('dashboard')}
              >
                Dashboard
              </button>
            </li>
            <li className="nav-item">
              <button
                className={`nav-link btn btn-link text-decoration-none px-3 py-1 rounded-pill ${
                  activeTab === 'attendance'
                    ? 'active bg-white text-success fw-bold shadow-sm'
                    : 'text-white text-opacity-90 fw-medium'
                }`}
                onClick={() => setActiveTab('attendance')}
              >
                Attendance Management
              </button>
            </li>
            <li className="nav-item">
              <button
                className={`nav-link btn btn-link text-decoration-none px-3 py-1 rounded-pill ${
                  activeTab === 'analytics'
                    ? 'active bg-white text-success fw-bold shadow-sm'
                    : 'text-white text-opacity-90 fw-medium'
                }`}
                onClick={() => setActiveTab('analytics')}
              >
                Analytics & Trends
              </button>
            </li>
            <li className="nav-item">
              <button
                className={`nav-link btn btn-link text-decoration-none px-3 py-1 rounded-pill ${
                  activeTab === 'correction'
                    ? 'active bg-white text-success fw-bold shadow-sm'
                    : 'text-white text-opacity-90 fw-medium'
                }`}
                onClick={() => setActiveTab('correction')}
              >
                Attendance Correction
              </button>
            </li>
          </ul>
        </div>
      </div>
    </header>
  );
}
