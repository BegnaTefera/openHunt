'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { apiRequest, Company, Job } from '../../lib/api';
import { useAuth } from './app-shell';

const sources = [
  'greenhouse',
  'lever',
  'ashby',
  'remotiko',
  'trulyremotework',
  'dynamitejobs',
];

function JobCard({ job }: { job: Job }) {
  return (
    <Link className="job-card" href={`/jobs/${job.id}`}>
      <div className="job-card-top">
        <span className="source-label">{job.source}</span>
        <span className="score-badge"><strong>{job.score}</strong><small>match</small></span>
      </div>
      <h3>{job.title}</h3>
      <p className="job-company">{job.company ?? 'Company not matched'} <span>·</span> {job.location ?? 'Location not listed'}</p>
      <div className="job-card-bottom">
        <span>{job.seniority ?? 'Seniority not listed'}</span>
        <span>{new Date(job.first_seen_at).toLocaleDateString()}</span>
      </div>
    </Link>
  );
}

export default function JobsDashboard() {
  const { token } = useAuth();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [source, setSource] = useState('');
  const [companyId, setCompanyId] = useState('');
  const [seniority, setSeniority] = useState('');
  const [newToday, setNewToday] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    setError('');
    const params = new URLSearchParams();
    if (source) params.set('source', source);
    if (companyId) params.set('company_id', companyId);
    if (seniority) params.set('seniority', seniority);
    if (newToday) params.set('new_today', 'true');
    Promise.all([
      apiRequest<Job[]>(`/jobs${params.size ? `?${params.toString()}` : ''}`, token),
      apiRequest<Company[]>('/companies', token),
    ]).then(([jobRows, companyRows]) => {
      if (!cancelled) {
        setJobs(jobRows);
        setCompanies(companyRows);
      }
    }).catch((cause: unknown) => {
      if (!cancelled) setError(cause instanceof Error ? cause.message : 'Could not load jobs.');
    }).finally(() => {
      if (!cancelled) setBusy(false);
    });
    return () => { cancelled = true; };
  }, [token, source, companyId, seniority, newToday]);

  const label = useMemo(() => {
    if (!jobs.length) return 'No opportunities found';
    return `${jobs.length} ${jobs.length === 1 ? 'opportunity' : 'opportunities'} ranked by fit`;
  }, [jobs.length]);

  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Discover</p>
          <h1>Your opportunities</h1>
          <p className="muted">The strongest matches are ready for your review.</p>
        </div>
        <div className="heading-quick-stat"><strong>{jobs.length}</strong><span>active matches</span></div>
      </section>
      <section className="filter-bar" aria-label="Job filters">
        <label>Source
          <select value={source} onChange={(event) => setSource(event.target.value)}>
            <option value="">All sources</option>
            {sources.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label>Company
          <select value={companyId} onChange={(event) => setCompanyId(event.target.value)}>
            <option value="">All companies</option>
            {companies.map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}
          </select>
        </label>
        <label>Seniority
          <select value={seniority} onChange={(event) => setSeniority(event.target.value)}>
            <option value="">All levels</option>
            {['junior', 'mid', 'senior', 'staff', 'principal', 'lead'].map((level) => (
              <option key={level} value={level}>{level}</option>
            ))}
          </select>
        </label>
        <label className="check-filter">
          <input type="checkbox" checked={newToday} onChange={(event) => setNewToday(event.target.checked)} />
          New today
        </label>
      </section>
      <div className="results-label">{label}</div>
      {error && <div className="notice error-message" role="alert">{error}</div>}
      {busy ? <div className="empty-state">Loading your jobs…</div> : (
        <section className="jobs-grid">
          {jobs.map((job) => <JobCard key={job.id} job={job} />)}
          {jobs.length === 0 && !error && (
            <div className="empty-state">
              <span className="empty-icon">✳</span>
              <h2>No matches yet</h2>
              <p>Try adjusting your filters or add company boards to start collecting jobs.</p>
              <Link className="button button-primary" href="/companies">Set up companies</Link>
            </div>
          )}
        </section>
      )}
    </>
  );
}
