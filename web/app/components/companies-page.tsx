'use client';

import { FormEvent, useCallback, useEffect, useState } from 'react';
import { apiRequest, Company } from '../../lib/api';
import { useAuth } from './app-shell';

type ATS = Company['ats_type'];

export default function CompaniesPage() {
  const { token, user } = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [name, setName] = useState('');
  const [atsType, setAtsType] = useState<ATS>('greenhouse');
  const [atsSlug, setAtsSlug] = useState('');
  const [website, setWebsite] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const loadCompanies = useCallback(async () => {
    setCompanies(await apiRequest<Company[]>('/companies', token));
  }, [token]);

  useEffect(() => {
    loadCompanies().catch((cause: unknown) => setError(cause instanceof Error ? cause.message : 'Could not load companies.'));
  }, [loadCompanies]);

  async function addCompany(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await apiRequest<Company>('/companies', token, {
        method: 'POST',
        body: JSON.stringify({ name, ats_type: atsType, ats_slug: atsSlug, website: website || null }),
      });
      setName('');
      setAtsSlug('');
      setWebsite('');
      await loadCompanies();
      setMessage('Company added. Its public jobs will be picked up by the worker.');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not add company.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section className="page-heading">
        <div><p className="eyebrow">Your sources</p><h1>Companies</h1><p className="muted">Manage employer boards that the collectors watch for new roles.</p></div>
        <div className="heading-quick-stat"><strong>{companies.length}</strong><span>configured</span></div>
      </section>
      <div className="settings-layout">
        <section className="content-panel">
          <div className="section-heading"><div><h2>Connected boards</h2><p className="muted">Jobs from these companies are matched into your feed.</p></div></div>
          <div className="connected-companies">
            {companies.map((company) => (
              <article className="connected-company" key={company.id}>
                <span className="company-initial">{company.name.slice(0, 1).toUpperCase()}</span>
                <div><strong>{company.name}</strong><span>{company.ats_type} · {company.ats_slug}</span></div>
                <span className="connection-status"><i /> Active</span>
              </article>
            ))}
            {companies.length === 0 && <p className="empty-inline">No boards connected yet.</p>}
          </div>
        </section>
        {!user.is_admin ? (
          <section className="content-panel">
            <div className="section-heading"><div><h2>Shared company list</h2><p className="muted">These boards are shared by everyone on this server and are managed by the admin. New boards are also found automatically by Discovery.</p></div></div>
          </section>
        ) : (
        <form className="content-panel company-add-form" onSubmit={addCompany}>
          <div className="section-heading"><div><h2>Add a company</h2><p className="muted">Connect a public ATS job board.</p></div></div>
          <label>Company name<input value={name} onChange={(event) => setName(event.target.value)} required /></label>
          <label>ATS platform
            <select value={atsType} onChange={(event) => setAtsType(event.target.value as ATS)}>
              <option value="greenhouse">Greenhouse</option><option value="lever">Lever</option><option value="ashby">Ashby</option><option value="workable">Workable</option>
            </select>
          </label>
          <label>Board slug<input value={atsSlug} onChange={(event) => setAtsSlug(event.target.value)} pattern="[A-Za-z0-9._-]{1,255}" placeholder="company-board" required /></label>
          <label>Website <span className="optional">(optional)</span><input type="url" value={website} onChange={(event) => setWebsite(event.target.value)} placeholder="https://company.com" /></label>
          {atsType === 'workable' && <p className="muted small-note">Workable job collection requires an account token and is currently disabled.</p>}
          {error && <p className="error-message" role="alert">{error}</p>}
          {message && <p className="success-message" role="status">{message}</p>}
          <button className="button button-primary" disabled={busy}>{busy ? 'Adding…' : 'Add board'}</button>
        </form>
        )}
      </div>
    </>
  );
}
