import React, { useState, useEffect, useMemo } from 'react';

const REASON_METADATA = {
  VALUE_MISMATCH: {
    label: 'Value Mismatch',
    badgeClass: 'badge-value-mismatch',
    severity: 'Critical',
    desc: 'System B value differs from System A total, or B value is missing/blank.',
    action: 'Review adjustment calculation and verify System B journal entry.',
  },
  MISSING_IN_B: {
    label: 'Missing in B',
    badgeClass: 'badge-missing',
    severity: 'High',
    desc: 'Record exists in System A but has no entry in System B.',
    action: 'Create corresponding transaction entry in System B or verify sync pipeline.',
  },
  ORPHAN_IN_B: {
    label: 'Orphan in B',
    badgeClass: 'badge-orphan',
    severity: 'High',
    desc: 'System B entry references a record that does not exist in System A.',
    action: 'Investigate source voucher in System B or confirm if record was deleted in System A.',
  },
  DUPLICATE_IN_B: {
    label: 'Duplicate in B',
    badgeClass: 'badge-duplicate',
    severity: 'Critical',
    desc: 'Multiple B entries for one record that do not add up to A total.',
    action: 'Identify redundant duplicate entry and reverse duplicate posting in System B.',
  },
  LOCATION_MISMATCH: {
    label: 'Location Mismatch',
    badgeClass: 'badge-location',
    severity: 'Warning',
    desc: 'Location recorded in System A differs from System B.',
    action: 'Re-assign transaction to the correct branch location. Foreign location masked for tenant security.',
  },
  DATE_MISMATCH: {
    label: 'Date Mismatch',
    badgeClass: 'badge-date',
    severity: 'Warning',
    desc: 'Event date in System A differs from recorded date in System B.',
    action: 'Verify accrual vs posting date; update accounting period in System B if required.',
  },
  RECORD_VOIDED: {
    label: 'Record Voided',
    badgeClass: 'badge-voided',
    severity: 'High',
    desc: 'Transaction marked VOIDED in System A, but System B maintains an active ledger posting.',
    action: 'Post reversal journal entry in System B to eliminate phantom cash balance.',
  },
  CLEAN_MATCH: {
    label: 'Clean Match',
    badgeClass: 'badge-clean',
    severity: 'Clean',
    desc: 'Transaction balances cleanly in amount, location, and date across both systems.',
    action: 'No action required. Reconciled and approved.',
  },
  CLEAN_SPLIT: {
    label: 'Balanced Split',
    badgeClass: 'badge-split',
    severity: 'Clean',
    desc: 'Multi-part split entry in System B that sums exactly to System A total_value.',
    action: 'Valid business split verified. Approved by audit.',
  },
};

function formatCurrency(val) {
  if (val === null || val === undefined || val === '') {
    return '';
  }
  const num = parseFloat(val);
  if (isNaN(num)) return val;
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
  }).format(num);
}

function formatDifference(val) {
  if (val === null || val === undefined || val === '') {
    return '';
  }
  const clean = String(val).replace('+', '');
  const num = parseFloat(clean);
  if (isNaN(num)) return val;
  if (num === 0) return '$0.00';
  const formatted = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
  }).format(Math.abs(num));
  return num > 0 ? `+${formatted}` : `-${formatted}`;
}

function escapeCSVCell(value) {
  return `"${String(value ?? '').replace(/"/g, '""')}"`;
}

export default function App() {
  const [currentOrg, setCurrentOrg] = useState('ORG-A');
  const [viewMode, setViewMode] = useState('disagreements'); // 'disagreements' | 'all' | 'clean'
  const [selectedReason, setSelectedReason] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortField, setSortField] = useState('-value');
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [auditActions, setAuditActions] = useState({});

  const [data, setData] = useState({
    total: 0,
    total_disagreements: 0,
    total_clean: 0,
    total_analyzed: 0,
    match_rate_pct: 100,
    total_variance_usd: '0.00',
    counts_by_reason: {},
    results: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch data from backend
  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);

    const params = new URLSearchParams();
    params.set('org', currentOrg);

    // Pass include_clean=true if user selected 'all' or 'clean' view modes
    if (viewMode === 'all' || viewMode === 'clean') {
      params.set('include_clean', 'true');
    }

    if (selectedReason && selectedReason !== 'ALL') {
      params.set('reason', selectedReason);
    }
    if (sortField) {
      params.set('sort', sortField);
    }
    if (searchQuery.trim()) {
      params.set('search', searchQuery.trim());
    }

    const apiBase = (window.location.port === '8000' || window.location.port === '5173')
      ? ''
      : (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000');
    const apiUrl = `${apiBase}/api/disagreements/?${params.toString()}`;

    fetch(apiUrl)
      .then(async (res) => {
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.error || `HTTP ${res.status}: ${res.statusText}`);
        }
        return res.json();
      })
      .then((json) => {
        if (isMounted) {
          setData(json);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          console.error('Fetch error:', err);
          setError(err.message);
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [currentOrg, viewMode, selectedReason, sortField, searchQuery]);

  const handleSort = (field) => {
    if (sortField === field) {
      setSortField(`-${field}`);
    } else if (sortField === `-${field}`) {
      setSortField(field);
    } else {
      setSortField(field);
    }
  };

  const getSortIcon = (field) => {
    if (sortField === field) return ' ▲';
    if (sortField === `-${field}`) return ' ▼';
    return '';
  };

  // Filter results client-side for clean view mode if selected
  const displayedResults = useMemo(() => {
    if (viewMode === 'clean') {
      return (data.results || []).filter((r) => r.reason.startsWith('CLEAN_'));
    }
    return data.results || [];
  }, [data.results, viewMode]);

  // Export current table view as a timestamped CSV
  const exportToCSV = () => {
    if (!displayedResults.length) return;
    const headers = [
      'Record ID',
      'Entry ID',
      'Reason',
      'Location',
      'Location (System A)',
      'Location (System B)',
      'System A Value',
      'System B Value',
      'Difference',
      'Date (System A)',
      'Date (System B)',
      'Audit Status',
      'Details',
    ];

    const rows = displayedResults.map((r) => [
      r.record_id,
      r.entry_id,
      r.reason,
      r.location,
      r.location_a,
      r.location_b,
      r.a_value,
      r.b_value,
      r.difference,
      r.a_date,
      r.b_date,
      auditActions[r.record_id] || 'Pending Review',
      r.details,
    ].map(escapeCSVCell));

    const csvContent = [headers.map(escapeCSVCell).join(','), ...rows.map((row) => row.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `DealerOS_Reconciliation_${currentOrg}_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  const handleAuditAction = (recordId, actionName) => {
    setAuditActions((prev) => ({
      ...prev,
      [recordId]: actionName,
    }));
  };

  return (
    <div className="app-container">
      {/* Top Header & Tenant Selector */}
      <header className="app-header">
        <div className="brand-section">
          <div className="brand-logo">D</div>
          <div className="brand-info">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h1>DealerOS Reconciliation</h1>
              <span className="live-pill">Live System</span>
            </div>
            <p>Dual-Ledger Audit & Disagreement Detection Engine</p>
          </div>
        </div>

        <div className="tenant-panel">
          <span className="tenant-label">Active Tenant:</span>
          <div className="tenant-buttons">
            <button
              className={`tenant-btn ${currentOrg === 'ORG-A' ? 'active' : ''}`}
              onClick={() => {
                setCurrentOrg('ORG-A');
                setSelectedReason('ALL');
                setSelectedRecord(null);
              }}
            >
              🏢 ORG-A (Loc 101–103)
            </button>
            <button
              className={`tenant-btn ${currentOrg === 'ORG-B' ? 'active' : ''}`}
              onClick={() => {
                setCurrentOrg('ORG-B');
                setSelectedReason('ALL');
                setSelectedRecord(null);
              }}
            >
              🏢 ORG-B (Loc 201–202)
            </button>
          </div>
        </div>
      </header>

      {/* Executive Summary Metrics Banner */}
      <section className="executive-banner">
        <div className="exec-stat-box">
          <span className="exec-stat-label">Reconciliation Rate</span>
          <div className="exec-stat-value" style={{ color: data.match_rate_pct >= 90 ? '#16a34a' : '#d97706' }}>
            {data.match_rate_pct}%
          </div>
          <div className="match-progress-bar">
            <div className="match-progress-fill" style={{ width: `${data.match_rate_pct}%` }}></div>
          </div>
        </div>

        <div className="exec-stat-box">
          <span className="exec-stat-label">Total Transactions</span>
          <div className="exec-stat-value">{data.total_analyzed || 0}</div>
          <span className="exec-stat-sub">Across System A & B</span>
        </div>

        <div className="exec-stat-box">
          <span className="exec-stat-label">Clean Matches</span>
          <div className="exec-stat-value" style={{ color: '#16a34a' }}>
            {data.total_clean || 0}
          </div>
          <span className="exec-stat-sub">Balanced & Verified</span>
        </div>

        <div className="exec-stat-box">
          <span className="exec-stat-label">Disagreements</span>
          <div className="exec-stat-value" style={{ color: '#dc2626' }}>
            {data.total_disagreements || 0}
          </div>
          <span className="exec-stat-sub">Action Required</span>
        </div>

        <div className="exec-stat-box">
          <span className="exec-stat-label">Net Dollar Variance</span>
          <div className="exec-stat-value" style={{ color: '#0f172a' }}>
            {formatCurrency(data.total_variance_usd)}
          </div>
          <span className="exec-stat-sub">Cumulative Variance</span>
        </div>
      </section>

      {/* KPI Cards / Disagreement Breakdown */}
      <section className="kpi-grid">
        <div
          className={`kpi-card ${selectedReason === 'ALL' && viewMode === 'disagreements' ? 'selected' : ''}`}
          onClick={() => {
            setViewMode('disagreements');
            setSelectedReason('ALL');
          }}
        >
          <div className="kpi-title">All Disagreements</div>
          <div className="kpi-value">{data.total_disagreements || 0}</div>
          <div className="kpi-desc">Actionable discrepancies</div>
        </div>

        <div
          className={`kpi-card ${selectedReason === 'VALUE_MISMATCH' ? 'selected' : ''}`}
          onClick={() => {
            setViewMode('disagreements');
            setSelectedReason('VALUE_MISMATCH');
          }}
        >
          <div className="kpi-title">Value Mismatches</div>
          <div className="kpi-value" style={{ color: 'var(--danger)' }}>
            {data.counts_by_reason?.VALUE_MISMATCH || 0}
          </div>
          <div className="kpi-desc">Base vs Total or blank fields</div>
        </div>

        <div
          className={`kpi-card ${selectedReason === 'MISSING_IN_B' ? 'selected' : ''}`}
          onClick={() => {
            setViewMode('disagreements');
            setSelectedReason('MISSING_IN_B');
          }}
        >
          <div className="kpi-title">Missing in B</div>
          <div className="kpi-value" style={{ color: 'var(--warning)' }}>
            {data.counts_by_reason?.MISSING_IN_B || 0}
          </div>
          <div className="kpi-desc">Unrecorded transactions</div>
        </div>

        <div
          className={`kpi-card ${selectedReason === 'DUPLICATE_IN_B' ? 'selected' : ''}`}
          onClick={() => {
            setViewMode('disagreements');
            setSelectedReason('DUPLICATE_IN_B');
          }}
        >
          <div className="kpi-title">Duplicates in B</div>
          <div className="kpi-value" style={{ color: 'var(--purple)' }}>
            {data.counts_by_reason?.DUPLICATE_IN_B || 0}
          </div>
          <div className="kpi-desc">Double-posted entries (splits excluded)</div>
        </div>

        <div
          className={`kpi-card ${selectedReason === 'ORPHAN_IN_B' ? 'selected' : ''}`}
          onClick={() => {
            setViewMode('disagreements');
            setSelectedReason('ORPHAN_IN_B');
          }}
        >
          <div className="kpi-title">Orphan Entries</div>
          <div className="kpi-value" style={{ color: 'var(--cyan)' }}>
            {data.counts_by_reason?.ORPHAN_IN_B || 0}
          </div>
          <div className="kpi-desc">Entries without System A record</div>
        </div>
      </section>

      {/* Control Bar: View Mode Switcher, Reason Filter, Search & Export */}
      <div className="controls-card">
        <div className="controls-left">
          {/* View Mode Pills */}
          <div className="view-mode-group">
            <button
              className={`view-mode-btn ${viewMode === 'disagreements' ? 'active' : ''}`}
              onClick={() => {
                setViewMode('disagreements');
                setSelectedReason('ALL');
              }}
            >
              ⚠️ Disagreements ({data.total_disagreements || 0})
            </button>
            <button
              className={`view-mode-btn ${viewMode === 'clean' ? 'active' : ''}`}
              onClick={() => {
                setViewMode('clean');
                setSelectedReason('ALL');
              }}
            >
              ✅ Clean Matches ({data.total_clean || 0})
            </button>
            <button
              className={`view-mode-btn ${viewMode === 'all' ? 'active' : ''}`}
              onClick={() => {
                setViewMode('all');
                setSelectedReason('ALL');
              }}
            >
              📊 Full Ledger ({data.total_analyzed || 0})
            </button>
          </div>

          {/* Reason Select Dropdown */}
          <div className="filter-group">
            <select
              id="reason-select"
              className="select-input"
              value={selectedReason}
              onChange={(e) => setSelectedReason(e.target.value)}
            >
              <option value="ALL">All Categories</option>
              {Object.keys(REASON_METADATA).map((reasonKey) => {
                const count = data.counts_by_reason?.[reasonKey] || 0;
                return (
                  <option key={reasonKey} value={reasonKey}>
                    {REASON_METADATA[reasonKey].label} ({count})
                  </option>
                );
              })}
            </select>

            {/* Search Input */}
            <input
              type="text"
              className="text-input"
              placeholder="🔍 Search Record ID, Location, Details..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        <div className="controls-right">
          <button className="btn-export" onClick={exportToCSV} title="Download filtered audit report as CSV">
            📥 Export Audit CSV
          </button>
          <div className="stats-badge">
            <strong>{displayedResults.length}</strong> {displayedResults.length === 1 ? 'row' : 'rows'}
          </div>
        </div>
      </div>

      {/* Main Table Screen */}
      <div className="table-card">
        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th className="sortable" onClick={() => handleSort('reason')}>
                  Disagreement Reason {getSortIcon('reason')}
                </th>
                <th className="sortable" onClick={() => handleSort('record_id')}>
                  Record / Entry ID {getSortIcon('record_id')}
                </th>
                <th className="sortable" onClick={() => handleSort('location')}>
                  Location {getSortIcon('location')}
                </th>
                <th className="sortable" onClick={() => handleSort('a_value')} style={{ textAlign: 'right' }}>
                  System A Total {getSortIcon('a_value')}
                </th>
                <th className="sortable" onClick={() => handleSort('b_value')} style={{ textAlign: 'right' }}>
                  System B Value {getSortIcon('b_value')}
                </th>
                <th className="sortable" onClick={() => handleSort('difference')} style={{ textAlign: 'right' }}>
                  Difference {getSortIcon('difference')}
                </th>
                <th>Event / Recorded Date</th>
                <th>Audit Status</th>
                <th style={{ textAlign: 'center' }}>Inspect</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="9" style={{ textAlign: 'center', padding: '40px' }}>
                    <div style={{ color: 'var(--text-muted)' }}>Loading tenant reconciliation data...</div>
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td colSpan="9">
                    <div className="state-message">
                      <h3 style={{ color: 'var(--danger)' }}>Failed to load data</h3>
                      <p>{error}</p>
                      <button className="btn-retry" onClick={() => window.location.reload()}>
                        Retry
                      </button>
                    </div>
                  </td>
                </tr>
              ) : displayedResults.length === 0 ? (
                <tr>
                  <td colSpan="9">
                    <div className="state-message">
                      <h3>No Records Found</h3>
                      <p>
                        {selectedReason === 'ALL'
                          ? `No items matched the current filter for ${currentOrg}.`
                          : `No items matched the '${REASON_METADATA[selectedReason]?.label || selectedReason}' filter for ${currentOrg}.`}
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                displayedResults.map((row, idx) => {
                  const meta = REASON_METADATA[row.reason] || {
                    label: row.reason,
                    badgeClass: 'badge-voided',
                  };
                  const diffVal = parseFloat(String(row.difference || '0').replace('+', ''));
                  const actionStatus = auditActions[row.record_id] || (row.reason.startsWith('CLEAN_') ? 'Reconciled' : 'Pending Review');

                  return (
                    <tr
                      key={`${row.record_id}-${row.reason}-${idx}`}
                      className={selectedRecord?.record_id === row.record_id ? 'row-selected' : ''}
                      onClick={() => setSelectedRecord(row)}
                      style={{ cursor: 'pointer' }}
                    >
                      {/* Reason Badge */}
                      <td>
                        <span className={`badge ${meta.badgeClass}`}>
                          {meta.label}
                        </span>
                      </td>

                      {/* Record ID & Entry ID */}
                      <td>
                        <div className="mono-val" style={{ fontWeight: 600 }}>
                          {row.record_id || <span className="val-empty">—</span>}
                        </div>
                        {row.entry_id && (
                          <div className="record-sub">
                            Entry: {row.entry_id}
                          </div>
                        )}
                      </td>

                      {/* Location */}
                      <td>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                          <div>
                            <span className="location-tag">{row.location || '—'}</span>
                          </div>
                          {row.location_b && row.location_b !== row.location_a && (
                            <div>
                              {row.location_b === '[External Org]' ? (
                                <span className="location-masked" title="Foreign location masked for tenant isolation">
                                  🔒 [External Org]
                                </span>
                              ) : (
                                <span className="record-sub">B: {row.location_b}</span>
                              )}
                            </div>
                          )}
                        </div>
                      </td>

                      {/* System A Value */}
                      <td style={{ textAlign: 'right' }}>
                        {row.a_value !== null && row.a_value !== undefined ? (
                          <span className="mono-val">{formatCurrency(row.a_value)}</span>
                        ) : (
                          <span className="val-empty">—</span>
                        )}
                      </td>

                      {/* System B Value */}
                      <td style={{ textAlign: 'right' }}>
                        {row.b_value !== null && row.b_value !== undefined ? (
                          <span className="mono-val">{formatCurrency(row.b_value)}</span>
                        ) : (
                          <span className="val-empty">—</span>
                        )}
                      </td>

                      {/* Difference */}
                      <td style={{ textAlign: 'right' }}>
                        {row.difference ? (
                          <span
                            className={`mono-val ${
                              diffVal > 0
                                ? 'diff-positive'
                                : diffVal < 0
                                ? 'diff-negative'
                                : 'diff-neutral'
                            }`}
                          >
                            {formatDifference(row.difference)}
                          </span>
                        ) : (
                          <span className="val-empty">—</span>
                        )}
                      </td>

                      {/* Dates */}
                      <td>
                        <div style={{ fontSize: '12px' }}>
                          {row.a_date && <div>A: {row.a_date}</div>}
                          {row.b_date && <div style={{ color: 'var(--text-muted)' }}>B: {row.b_date}</div>}
                          {!row.a_date && !row.b_date && <span className="val-empty">—</span>}
                        </div>
                      </td>

                      {/* Audit Status Pill */}
                      <td>
                        <span
                          className={`status-pill ${
                            actionStatus === 'Reconciled'
                              ? 'status-reconciled'
                              : actionStatus === 'Adjustment Requested'
                              ? 'status-adjustment'
                              : actionStatus === 'Investigating'
                              ? 'status-investigating'
                              : 'status-pending'
                          }`}
                        >
                          {actionStatus}
                        </span>
                      </td>

                      {/* Inspect Button */}
                      <td style={{ textAlign: 'center' }}>
                        <button
                          className="btn-inspect"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedRecord(row);
                          }}
                        >
                          Inspect 🔍
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Interactive Audit Inspection Drawer / Modal */}
      {selectedRecord && (
        <div className="drawer-overlay" onClick={() => setSelectedRecord(null)}>
          <div className="drawer-content" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-header">
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <h2 style={{ fontSize: '18px', fontWeight: '700' }}>{selectedRecord.record_id}</h2>
                  <span className={`badge ${REASON_METADATA[selectedRecord.reason]?.badgeClass || 'badge-voided'}`}>
                    {REASON_METADATA[selectedRecord.reason]?.label || selectedRecord.reason}
                  </span>
                </div>
                <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                  Tenant: {currentOrg} • Primary Location: {selectedRecord.location}
                </p>
              </div>
              <button className="btn-close-drawer" onClick={() => setSelectedRecord(null)}>
                ✕
              </button>
            </div>

            <div className="drawer-body">
              {/* Financial Variance Overview Card */}
              <div className="drawer-card">
                <h4 className="drawer-section-title">Financial Summary & Variance</h4>
                <div className="variance-grid">
                  <div className="variance-box">
                    <span className="variance-label">System A Total</span>
                    <span className="variance-amount">{formatCurrency(selectedRecord.a_value) || '—'}</span>
                  </div>
                  <div className="variance-box">
                    <span className="variance-label">System B Value</span>
                    <span className="variance-amount">{formatCurrency(selectedRecord.b_value) || '—'}</span>
                  </div>
                  <div className="variance-box">
                    <span className="variance-label">Calculated Variance</span>
                    <span
                      className="variance-amount"
                      style={{
                        color: parseFloat(String(selectedRecord.difference || '0')) !== 0 ? 'var(--danger)' : 'var(--success)',
                      }}
                    >
                      {formatDifference(selectedRecord.difference) || '$0.00'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Side-by-Side Dual-Ledger Details */}
              <div className="drawer-side-by-side">
                <div className="system-detail-box system-a-box">
                  <h4 style={{ fontSize: '13px', fontWeight: '700', marginBottom: '8px', color: '#1e3a8a' }}>
                    System A Ledger
                  </h4>
                  <div className="kv-row">
                    <span>Record ID:</span> <strong>{selectedRecord.record_id || '—'}</strong>
                  </div>
                  <div className="kv-row">
                    <span>Location:</span> <strong>{selectedRecord.location_a || selectedRecord.location || '—'}</strong>
                  </div>
                  <div className="kv-row">
                    <span>Event Date:</span> <strong>{selectedRecord.a_date || '—'}</strong>
                  </div>
                  <div className="kv-row">
                    <span>Total Value:</span> <strong>{formatCurrency(selectedRecord.a_value) || '—'}</strong>
                  </div>
                </div>

                <div className="system-detail-box system-b-box">
                  <h4 style={{ fontSize: '13px', fontWeight: '700', marginBottom: '8px', color: '#065f46' }}>
                    System B Ledger
                  </h4>
                  <div className="kv-row">
                    <span>Entry ID:</span> <strong>{selectedRecord.entry_id || '—'}</strong>
                  </div>
                  <div className="kv-row">
                    <span>Location:</span> <strong>{selectedRecord.location_b || selectedRecord.location || '—'}</strong>
                  </div>
                  <div className="kv-row">
                    <span>Recorded Date:</span> <strong>{selectedRecord.b_date || '—'}</strong>
                  </div>
                  <div className="kv-row">
                    <span>Value Posted:</span> <strong>{formatCurrency(selectedRecord.b_value) || '—'}</strong>
                  </div>
                </div>
              </div>

              {/* Root Cause Analysis */}
              <div className="drawer-card" style={{ background: '#f8fafc' }}>
                <h4 className="drawer-section-title">🔍 Root Cause Explanation</h4>
                <p style={{ fontSize: '13px', color: '#334155', lineHeight: '1.5' }}>
                  {selectedRecord.details || REASON_METADATA[selectedRecord.reason]?.desc || 'Standard transaction.'}
                </p>
              </div>

              {/* Recommended Action */}
              <div className="drawer-card" style={{ background: '#eff6ff', borderColor: '#bfdbfe' }}>
                <h4 className="drawer-section-title" style={{ color: '#1d4ed8' }}>
                  💡 Recommended Accounting Action
                </h4>
                <p style={{ fontSize: '13px', color: '#1e40af', lineHeight: '1.5' }}>
                  {REASON_METADATA[selectedRecord.reason]?.action || 'Review transaction details.'}
                </p>
              </div>

              {/* Auditor Interactive Workflow Actions */}
              <div className="drawer-card">
                <h4 className="drawer-section-title">Interactive Audit Workflow</h4>
                <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '12px' }}>
                  Simulate resolution actions for client review (saved in session):
                </p>
                <div className="audit-action-buttons">
                  <button
                    className={`btn-action ${auditActions[selectedRecord.record_id] === 'Investigating' ? 'active-action' : ''}`}
                    onClick={() => handleAuditAction(selectedRecord.record_id, 'Investigating')}
                  >
                    🔍 Mark Investigating
                  </button>
                  <button
                    className={`btn-action ${auditActions[selectedRecord.record_id] === 'Adjustment Requested' ? 'active-action' : ''}`}
                    onClick={() => handleAuditAction(selectedRecord.record_id, 'Adjustment Requested')}
                  >
                    📝 Request Adjustment Voucher
                  </button>
                  <button
                    className={`btn-action ${auditActions[selectedRecord.record_id] === 'Reconciled' ? 'active-action' : ''}`}
                    onClick={() => handleAuditAction(selectedRecord.record_id, 'Reconciled')}
                  >
                    ✅ Mark as Reconciled
                  </button>
                </div>
                {auditActions[selectedRecord.record_id] && (
                  <div style={{ marginTop: '10px', fontSize: '12px', color: '#16a34a', fontWeight: '600' }}>
                    ✓ Current Status: {auditActions[selectedRecord.record_id]}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tenant Privacy & Security Guarantee Banner */}
      <footer className="security-banner">
        <div>
          <span className="security-dot"></span>
          <strong>Strict Multi-Tenant Isolation Active:</strong> All queries are scoped at the database level by{' '}
          <code>{currentOrg}</code>. Cross-organization location IDs are automatically masked to prevent data leakage.
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
          DealerOS v1.0 • Django REST Framework + React (Vite)
        </div>
      </footer>
    </div>
  );
}
