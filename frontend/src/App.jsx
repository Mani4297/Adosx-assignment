import React, { useState, useEffect, useMemo } from 'react';

const REASON_METADATA = {
  VALUE_MISMATCH: {
    label: 'Value Mismatch',
    badgeClass: 'badge-value-mismatch',
    desc: 'System B value differs from System A total, or B value is missing/blank.',
  },
  MISSING_IN_B: {
    label: 'Missing in B',
    badgeClass: 'badge-missing',
    desc: 'Record exists in System A but has no entry in System B.',
  },
  ORPHAN_IN_B: {
    label: 'Orphan in B',
    badgeClass: 'badge-orphan',
    desc: 'System B entry references a record that does not exist in System A.',
  },
  DUPLICATE_IN_B: {
    label: 'Duplicate in B',
    badgeClass: 'badge-duplicate',
    desc: 'Multiple B entries for one record that do not add up to A total.',
  },
  LOCATION_MISMATCH: {
    label: 'Location Mismatch',
    badgeClass: 'badge-location',
    desc: 'Location recorded in System A differs from System B.',
  },
  DATE_MISMATCH: {
    label: 'Date Mismatch',
    badgeClass: 'badge-date',
    desc: 'Event date in System A differs from recorded date in System B.',
  },
  RECORD_VOIDED: {
    label: 'Record Voided',
    badgeClass: 'badge-voided',
    desc: 'Transaction marked VOIDED in System A, but System B maintains an entry.',
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
  const formatted = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
  }).format(Math.abs(num));
  return num > 0 ? `+${formatted}` : `-${formatted}`;
}

export default function App() {
  const [currentOrg, setCurrentOrg] = useState('ORG-A');
  const [selectedReason, setSelectedReason] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortField, setSortField] = useState('-value');
  const [data, setData] = useState({
    total: 0,
    counts_by_reason: {},
    results: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch data whenever tenant, reason, or sort changes
  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);

    const params = new URLSearchParams();
    params.set('org', currentOrg);
    if (selectedReason && selectedReason !== 'ALL') {
      params.set('reason', selectedReason);
    }
    if (sortField) {
      params.set('sort', sortField);
    }
    if (searchQuery.trim()) {
      params.set('search', searchQuery.trim());
    }

    const apiUrl = `/api/disagreements/?${params.toString()}`;

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
  }, [currentOrg, selectedReason, sortField, searchQuery]);

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

  const totalDisagreementsCount = useMemo(() => {
    return Object.values(data.counts_by_reason || {}).reduce((a, b) => a + b, 0);
  }, [data.counts_by_reason]);

  return (
    <div className="app-container">
      {/* Top Header & Tenant Selector */}
      <header className="app-header">
        <div className="brand-section">
          <div className="brand-logo">D</div>
          <div className="brand-info">
            <h1>DealerOS Reconciliation</h1>
            <p>Dual-Ledger Audit & Disagreement Detection</p>
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
              }}
            >
              ORG-A (Loc 101–103)
            </button>
            <button
              className={`tenant-btn ${currentOrg === 'ORG-B' ? 'active' : ''}`}
              onClick={() => {
                setCurrentOrg('ORG-B');
                setSelectedReason('ALL');
              }}
            >
              ORG-B (Loc 201–202)
            </button>
          </div>
        </div>
      </header>

      {/* KPI Cards / Reason Summary */}
      <section className="kpi-grid">
        <div
          className={`kpi-card ${selectedReason === 'ALL' ? 'selected' : ''}`}
          onClick={() => setSelectedReason('ALL')}
        >
          <div className="kpi-title">Total Disagreements</div>
          <div className="kpi-value">{totalDisagreementsCount}</div>
          <div className="kpi-desc">Across all disagreement types</div>
        </div>

        <div
          className={`kpi-card ${selectedReason === 'VALUE_MISMATCH' ? 'selected' : ''}`}
          onClick={() => setSelectedReason('VALUE_MISMATCH')}
        >
          <div className="kpi-title">Value Mismatches</div>
          <div className="kpi-value" style={{ color: 'var(--danger)' }}>
            {data.counts_by_reason?.VALUE_MISMATCH || 0}
          </div>
          <div className="kpi-desc">Base vs total or blank values</div>
        </div>

        <div
          className={`kpi-card ${selectedReason === 'MISSING_IN_B' ? 'selected' : ''}`}
          onClick={() => setSelectedReason('MISSING_IN_B')}
        >
          <div className="kpi-title">Missing in B</div>
          <div className="kpi-value" style={{ color: 'var(--warning)' }}>
            {data.counts_by_reason?.MISSING_IN_B || 0}
          </div>
          <div className="kpi-desc">Unrecorded System A records</div>
        </div>

        <div
          className={`kpi-card ${selectedReason === 'DUPLICATE_IN_B' ? 'selected' : ''}`}
          onClick={() => setSelectedReason('DUPLICATE_IN_B')}
        >
          <div className="kpi-title">Duplicates in B</div>
          <div className="kpi-value" style={{ color: 'var(--purple)' }}>
            {data.counts_by_reason?.DUPLICATE_IN_B || 0}
          </div>
          <div className="kpi-desc">Double-posted entries (splits excluded)</div>
        </div>

        <div
          className={`kpi-card ${selectedReason === 'ORPHAN_IN_B' ? 'selected' : ''}`}
          onClick={() => setSelectedReason('ORPHAN_IN_B')}
        >
          <div className="kpi-title">Orphan Entries</div>
          <div className="kpi-value" style={{ color: 'var(--cyan)' }}>
            {data.counts_by_reason?.ORPHAN_IN_B || 0}
          </div>
          <div className="kpi-desc">B entries with unknown record_id</div>
        </div>
      </section>

      {/* Control Bar: Reason Filter & Search */}
      <div className="controls-card">
        <div className="filter-group">
          <label className="control-label" htmlFor="reason-select">Filter by Reason:</label>
          <select
            id="reason-select"
            className="select-input"
            value={selectedReason}
            onChange={(e) => setSelectedReason(e.target.value)}
          >
            <option value="ALL">All Disagreements ({totalDisagreementsCount})</option>
            {Object.keys(REASON_METADATA).map((reasonKey) => {
              const count = data.counts_by_reason?.[reasonKey] || 0;
              return (
                <option key={reasonKey} value={reasonKey}>
                  {REASON_METADATA[reasonKey].label} ({count})
                </option>
              );
            })}
          </select>

          <input
            type="text"
            className="text-input"
            placeholder="Search Record ID, Location, Details..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="stats-badge">
          Showing <strong>{data.results?.length || 0}</strong> {data.results?.length === 1 ? 'record' : 'records'} for{' '}
          <strong>{currentOrg}</strong>
        </div>
      </div>

      {/* Main Table Screen */}
      <div className="table-card">
        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th
                  className="sortable"
                  onClick={() => handleSort('reason')}
                >
                  Disagreement Reason {getSortIcon('reason')}
                </th>
                <th
                  className="sortable"
                  onClick={() => handleSort('record_id')}
                >
                  Record / Entry ID {getSortIcon('record_id')}
                </th>
                <th
                  className="sortable"
                  onClick={() => handleSort('location')}
                >
                  Location {getSortIcon('location')}
                </th>
                <th
                  className="sortable"
                  onClick={() => handleSort('a_value')}
                  style={{ textAlign: 'right' }}
                >
                  System A Total {getSortIcon('a_value')}
                </th>
                <th
                  className="sortable"
                  onClick={() => handleSort('b_value')}
                  style={{ textAlign: 'right' }}
                >
                  System B Value {getSortIcon('b_value')}
                </th>
                <th
                  className="sortable"
                  onClick={() => handleSort('difference')}
                  style={{ textAlign: 'right' }}
                >
                  Difference {getSortIcon('difference')}
                </th>
                <th>Event Date / Recorded On</th>
                <th>Audit Details</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="8" style={{ textAlign: 'center', padding: '40px' }}>
                    <div style={{ color: 'var(--text-muted)' }}>Loading tenant reconciliation data...</div>
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td colSpan="8">
                    <div className="state-message">
                      <h3 style={{ color: 'var(--danger)' }}>Failed to load data</h3>
                      <p>{error}</p>
                      <button className="btn-retry" onClick={() => window.location.reload()}>
                        Retry
                      </button>
                    </div>
                  </td>
                </tr>
              ) : data.results?.length === 0 ? (
                <tr>
                  <td colSpan="8">
                    <div className="state-message">
                      <h3>No Disagreements Found</h3>
                      <p>
                        {selectedReason === 'ALL'
                          ? `All transactions for ${currentOrg} match cleanly between System A and System B!`
                          : `No items matched the '${REASON_METADATA[selectedReason]?.label || selectedReason}' filter for ${currentOrg}.`}
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                data.results.map((row, idx) => {
                  const meta = REASON_METADATA[row.reason] || {
                    label: row.reason,
                    badgeClass: 'badge-voided',
                  };
                  const diffVal = parseFloat(String(row.difference || '0').replace('+', ''));

                  return (
                    <tr key={`${row.record_id}-${row.reason}-${idx}`}>
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

                      {/* Audit Details */}
                      <td className="details-cell">
                        {row.details || '—'}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Tenant Privacy & Security Guarantee Banner */}
      <footer className="security-banner">
        <div>
          <span className="security-dot"></span>
          <strong>Strict Multi-Tenant Isolation Active:</strong> All queries are scoped at the database level by{' '}
          <code>{currentOrg}</code>. Cross-organization location IDs are automatically masked to prevent data leakage.
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
          DealerOS v1.0 • Django + React
        </div>
      </footer>
    </div>
  );
}
