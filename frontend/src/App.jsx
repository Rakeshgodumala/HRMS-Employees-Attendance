import React, { useState } from 'react';
import Navbar from './components/Navbar';
import Dashboard from './components/Dashboard';
import AttendanceList from './components/AttendanceList';
import Analytics from './components/Analytics';
import AttendanceCorrection from './components/AttendanceCorrection';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [correctionPrefill, setCorrectionPrefill] = useState({ empCode: '', date: '' });

  const handleSelectForCorrection = (empCode, date) => {
    setCorrectionPrefill({ empCode, date });
    setActiveTab('correction');
  };

  return (
    <div className="d-flex flex-column min-vh-100 bg-light">
      <Navbar activeTab={activeTab} setActiveTab={setActiveTab} />

      <main className="flex-grow-1">
        {activeTab === 'dashboard' && (
          <Dashboard setActiveTab={setActiveTab} />
        )}

        {activeTab === 'attendance' && (
          <AttendanceList onSelectForCorrection={handleSelectForCorrection} />
        )}

        {activeTab === 'analytics' && (
          <Analytics />
        )}

        {activeTab === 'correction' && (
          <AttendanceCorrection
            prefillEmpCode={correctionPrefill.empCode}
            prefillDate={correctionPrefill.date}
          />
        )}
      </main>

      <footer className="bg-white border-top py-3 mt-auto">
        <div className="container-fluid px-md-4 text-center text-muted small">
          <span>HROne Employee Attendance & Analytics © Rakesh Godumala</span>
        </div>
      </footer>
    </div>
  );
}
