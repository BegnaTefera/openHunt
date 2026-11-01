'use client';

import { useEffect, useState } from 'react';
import { apiRequest, DiscoveryStatus, ProviderBudget } from '../../lib/api';
import { useAuth } from './app-shell';

function budgetLine(provider: ProviderBudget): string {
  if (!provider.configured) return 'Not configured';
  const parts: string[] = [];
  if (provider.daily_cap !== null) parts.push(`${provider.used_today}/${provider.daily_cap} today`);
  if (provider.monthly_cap !== null) parts.push(`${provider.used_this_month}/${provider.monthly_cap} this month`);
  if (provider.total_cap !== null) parts.push(`${provider.used_total}/${provider.total_cap} in total`);
  if (parts.length === 0) parts.push(`${provider.used_total} requests so far, no key or cap needed`);
  return parts.join(' · ');
}

function formatTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : 'never';
}

export default function DiscoveryPage() {
  const { token } = useAuth();
  const [status, setStatus] = useState<DiscoveryStatus | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    apiRequest<DiscoveryStatus>('/discovery', token)
      .then(setStatus)
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : 'Could not load discovery.'));
  }, [token]);

  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Find more employers</p>
          <h1>Discovery</h1>
          <p className="muted">Finds new company job boards on free sources and adds the ones hiring backend or full-stack roles.</p>
        </div>
        {status && <div className="heading-quick-stat"><strong>{status.added_total}</strong><span>companies added</span></div>}
      </section>
      {error && <div className="notice error-message" role="alert">{error}</div>}
      {!status ? <div className="empty-state">Loading discovery…</div> : (
        <>
          <section className="content-panel">
            <div className="section-heading"><div><h2>Free-tier budgets</h2><p className="muted">Each source stops before its free quota runs out.</p></div></div>
            <div className="connected-companies">
              {status.providers.map((provider) => (
                <article className="connected-company" key={provider.name}>
                  <span className="company-initial">{provider.name.slice(0, 1).toUpperCase()}</span>
                  <div><strong>{provider.name}</strong><span>{budgetLine(provider)}</span></div>
                  <span className="connection-status"><i /> {provider.configured ? 'Active' : 'Off'}</span>
                </article>
              ))}
            </div>
          </section>
          <section className="content-panel">
            <div className="section-heading"><div><h2>Last run</h2><p className="muted">Runs on the schedule. To run it now, use “Run workflow” on the Collect jobs action in GitHub.</p></div></div>
            {status.last_run ? (
              <>
                <p className="muted">{formatTime(status.last_run_at)} · {status.last_run.urls_seen ?? 0} URLs seen · {status.last_run.candidates ?? 0} candidates · {status.last_run.validated ?? 0} checked · {status.last_run.added ?? 0} added · {status.last_run.rejected ?? 0} rejected · {status.last_run.deferred ?? 0} waiting</p>
                {(status.last_run.errors ?? []).length > 0 && (
                  <ul className="warning-list">
                    {(status.last_run.errors ?? []).slice(0, 6).map((message) => <li key={message}>{message}</li>)}
                  </ul>
                )}
              </>
            ) : <p className="empty-inline">No discovery run has finished yet.</p>}
          </section>
          <section className="content-panel stats-table-panel">
            <div className="section-heading"><div><h2>Recent boards</h2><p className="muted">{status.added_total} added, {status.rejected_total} rejected so far.</p></div></div>
            <div className="table-scroll">
              <table>
                <thead><tr><th>Board</th><th>ATS</th><th>Found by</th><th>Result</th><th>Details</th></tr></thead>
                <tbody>
                  {status.recent_candidates.map((item) => (
                    <tr key={`${item.ats_type}-${item.ats_slug}`}>
                      <td>{item.ats_slug}</td>
                      <td><span className="source-label">{item.ats_type}</span></td>
                      <td>{item.source}</td>
                      <td><span className={`status-pill ${item.status === 'added' ? 'status-shortlisted' : 'status-skipped'}`}>{item.status}</span></td>
                      <td>{item.reason ?? ''}</td>
                    </tr>
                  ))}
                  {status.recent_candidates.length === 0 && <tr><td colSpan={5} className="table-empty">Nothing found yet. Discovery fills this in after its first run.</td></tr>}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  );
}
