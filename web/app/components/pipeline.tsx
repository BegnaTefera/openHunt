'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { apiRequest, Job, JobStatus } from '../../lib/api';
import { useAuth } from './app-shell';

const columns: { status: JobStatus; label: string }[] = [
  { status: 'new', label: 'New' },
  { status: 'shortlisted', label: 'Shortlisted' },
  { status: 'drafted', label: 'Drafted' },
  { status: 'applied', label: 'Applied' },
  { status: 'replied', label: 'Replied' },
  { status: 'interview', label: 'Interview' },
  { status: 'offer', label: 'Offer' },
  { status: 'rejected', label: 'Rejected' },
  { status: 'skipped', label: 'Skipped' },
];

export default function Pipeline() {
  const { token } = useAuth();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    apiRequest<Job[]>('/jobs', token)
      .then(setJobs)
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : 'Could not load pipeline.'));
  }, [token]);

  return (
    <>
      <section className="page-heading">
        <div><p className="eyebrow">Keep momentum</p><h1>Your pipeline</h1><p className="muted">Every opportunity, organized by your next step.</p></div>
        <div className="heading-quick-stat"><strong>{jobs.length}</strong><span>in your pipeline</span></div>
      </section>
      {error && <div className="notice error-message" role="alert">{error}</div>}
      <section className="kanban" aria-label="Application pipeline">
        {columns.map((column) => {
          const items = jobs.filter((job) => job.status === column.status);
          return (
            <div className="kanban-column" key={column.status}>
              <header><h2>{column.label}</h2><span>{items.length}</span></header>
              <div className="kanban-cards">
                {items.map((job) => (
                  <Link className="pipeline-card" href={`/jobs/${job.id}`} key={job.id}>
                    <span className="source-label">{job.source}</span>
                    <h3>{job.title}</h3>
                    <p>{job.company ?? 'Company not matched'}</p>
                    <strong>{job.score} <small>match</small></strong>
                  </Link>
                ))}
                {items.length === 0 && <p className="column-empty">Nothing here yet</p>}
              </div>
            </div>
          );
        })}
      </section>
    </>
  );
}
