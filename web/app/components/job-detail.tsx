'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import {
  apiRequest,
  cacheCompleteJobDetail,
  getCachedJobDetail,
  Job,
  JobDetail,
  JobStatus,
} from '../../lib/api';
import { useAuth } from './app-shell';
import DraftPanel from './draft-panel';

export default function JobDetailView({ jobId }: { jobId: string }) {
  const { token, user } = useAuth();
  const [job, setJob] = useState<JobDetail | null>(
    () => getCachedJobDetail(user.id, jobId)?.job ?? null,
  );
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (refresh = false) => {
    const cached = getCachedJobDetail(user.id, jobId);
    if (cached) setJob(cached.job);
    if (cached?.complete && !refresh) {
      setError('');
      return;
    }
    try {
      setError('');
      const loaded = await apiRequest<JobDetail>(`/jobs/${jobId}`, token);
      setJob(loaded);
      cacheCompleteJobDetail(user.id, loaded);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load this job.');
    }
  }, [jobId, token, user.id]);

  useEffect(() => { void load(); }, [load]);

  async function updateStatus(status: JobStatus) {
    setBusy(true);
    setError('');
    try {
      const updated = await apiRequest<Job>(`/jobs/${jobId}/status`, token, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      });
      const next = { ...job, ...updated };
      setJob(next);
      cacheCompleteJobDetail(user.id, next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not update application status.');
    } finally {
      setBusy(false);
    }
  }

  if (error && !job) return <div className="notice error-message" role="alert">{error}</div>;
  if (!job) return <div className="empty-state">Loading job details…</div>;

  return (
    <>
      <Link className="back-link" href="/">← Back to jobs</Link>
      {error && <div className="notice error-message" role="alert">{error}</div>}
      <article className="detail-layout">
        <section className="detail-main">
          <div className="detail-heading">
            <span className="source-label">{job.source}</span>
            <span className={`status-pill status-${job.status}`}>{job.status}</span>
            <h1>{job.title}</h1>
            <p className="job-company">{job.company ?? 'Company not matched'} <span>·</span> {job.location ?? 'Location not listed'}</p>
            <div className="detail-tags">
              {job.seniority && <span>{job.seniority}</span>}
              {job.employment_type && <span>{job.employment_type}</span>}
              {job.salary_text && <span>{job.salary_text}</span>}
            </div>
          </div>
          <section className="content-panel">
            <h2>About the role</h2>
            <p className="description-text">{job.description || 'No description was provided by the source.'}</p>
          </section>
          <DraftPanel jobId={jobId} onDrafted={() => void load(true)} />
          <section className="content-panel">
            <h2>Skills and tags</h2>
            <div className="detail-tags">
              {job.tags.map((tag) => <span key={tag}>{tag}</span>)}
              {job.tags.length === 0 && <span>No tags provided</span>}
            </div>
          </section>
        </section>
        <aside className="detail-side">
          <div className="match-panel">
            <div className="match-score">{job.score}<small>/100</small></div>
            <h2>Match score</h2>
            <ul className="reason-list">
              {job.score_reasons.map((reason) => <li key={reason}>{reason}</li>)}
              {job.score_reasons.length === 0 && <li>Profile rules excluded this role or no fit signals were found.</li>}
            </ul>
          </div>
          <div className="action-panel">
            <h2>Your next step</h2>
            <button className={`button ${job.status === 'shortlisted' ? 'button-selected' : 'button-primary'}`} disabled={busy} onClick={() => void updateStatus('shortlisted')}>
              Shortlist
            </button>
            <button className={`button ${job.status === 'skipped' ? 'button-selected' : 'button-secondary'}`} disabled={busy} onClick={() => void updateStatus('skipped')}>
              Skip
            </button>
            <button className={`button ${job.status === 'applied' ? 'button-selected' : 'button-secondary'}`} disabled={busy} onClick={() => void updateStatus('applied')}>
              Mark applied
            </button>
            <a className="external-link" href={job.url} target="_blank" rel="noreferrer">Open original listing ↗</a>
          </div>
        </aside>
      </article>
    </>
  );
}
