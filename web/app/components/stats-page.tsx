'use client';

import { useEffect, useState } from 'react';
import { apiRequest, Stats } from '../../lib/api';
import { useAuth } from './app-shell';

export default function StatsPage() {
  const { token } = useAuth();
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    apiRequest<Stats>('/stats', token)
      .then(setStats)
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : 'Could not load stats.'));
  }, [token]);

  return (
    <>
      <section className="page-heading">
        <div><p className="eyebrow">A little perspective</p><h1>Your search, in numbers</h1><p className="muted">Track progress across every source.</p></div>
      </section>
      {error && <div className="notice error-message" role="alert">{error}</div>}
      {!stats ? <div className="empty-state">Loading your stats…</div> : (
        <>
          <section className="stats-grid">
            {[
              ['Jobs found', stats.jobs_found, 'Collected opportunities'],
              ['Applied', stats.applied, 'Applications sent'],
              ['Replies', stats.replies, 'Conversations started'],
              ['Interviews', stats.interviews, 'Interview-stage roles'],
            ].map(([label, value, caption]) => (
              <article className="stat-card" key={label}>
                <span>{label}</span><strong>{value}</strong><small>{caption}</small>
              </article>
            ))}
          </section>
          <section className="content-panel stats-table-panel">
            <div className="section-heading"><div><h2>By source</h2><p className="muted">See where your opportunities are coming from.</p></div></div>
            <div className="table-scroll">
              <table>
                <thead><tr><th>Source</th><th>Jobs found</th><th>Applied</th><th>Replies</th><th>Interviews</th></tr></thead>
                <tbody>
                  {stats.by_source.map((row) => (
                    <tr key={row.source}>
                      <td><span className="source-label">{row.source}</span></td>
                      <td>{row.jobs_found}</td><td>{row.applied}</td><td>{row.replies}</td><td>{row.interviews}</td>
                    </tr>
                  ))}
                  {stats.by_source.length === 0 && <tr><td colSpan={5} className="table-empty">Stats will appear after jobs are collected.</td></tr>}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  );
}
