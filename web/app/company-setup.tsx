'use client';

import { FormEvent, useCallback, useEffect, useState } from 'react';

type ATS = 'greenhouse' | 'lever' | 'ashby' | 'workable';

type Company = {
  id: number;
  name: string;
  ats_type: ATS;
  ats_slug: string;
  website: string | null;
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export default function CompanySetup() {
  const [token, setToken] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [companies, setCompanies] = useState<Company[]>([]);
  const [name, setName] = useState('');
  const [atsType, setAtsType] = useState<ATS>('greenhouse');
  const [atsSlug, setAtsSlug] = useState('');
  const [website, setWebsite] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const loadCompanies = useCallback(async (accessToken: string) => {
    const response = await fetch(`${apiUrl}/companies`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!response.ok) {
      throw new Error(`Could not load companies (${response.status})`);
    }
    setCompanies((await response.json()) as Company[]);
  }, []);

  useEffect(() => {
    const savedToken = window.localStorage.getItem('openhunt-token');
    if (!savedToken) return;
    setToken(savedToken);
    void loadCompanies(savedToken).catch((error: Error) => setMessage(error.message));
  }, [loadCompanies]);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage('');
    try {
      const response = await fetch(`${apiUrl}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (!response.ok) throw new Error(`Login failed (${response.status})`);
      const result = (await response.json()) as { access_token: string };
      window.localStorage.setItem('openhunt-token', result.access_token);
      setToken(result.access_token);
      setPassword('');
      await loadCompanies(result.access_token);
      setMessage('Signed in.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Login failed.');
    } finally {
      setBusy(false);
    }
  }

  async function handleAddCompany(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage('');
    try {
      const response = await fetch(`${apiUrl}/companies`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name,
          ats_type: atsType,
          ats_slug: atsSlug,
          website: website || null,
        }),
      });
      if (!response.ok) {
        const detail = (await response.json()) as { detail?: string };
        throw new Error(detail.detail ?? `Could not add company (${response.status})`);
      }
      setName('');
      setAtsSlug('');
      setWebsite('');
      await loadCompanies(token);
      setMessage('Company added. The worker will collect its published jobs.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not add company.');
    } finally {
      setBusy(false);
    }
  }

  function signOut() {
    window.localStorage.removeItem('openhunt-token');
    setToken('');
    setCompanies([]);
    setMessage('Signed out.');
  }

  return (
    <section className="setup">
      {!token ? (
        <form className="panel" onSubmit={handleLogin}>
          <h2>Sign in</h2>
          <label>
            Username
            <input value={username} onChange={(event) => setUsername(event.target.value)} required />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          <button disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        </form>
      ) : (
        <>
          <div className="setup-heading">
            <div>
              <h2>Job boards</h2>
              <p>Add a company’s ATS board to the scheduled public collector.</p>
            </div>
            <button className="secondary" onClick={signOut}>Sign out</button>
          </div>
          <form className="panel company-form" onSubmit={handleAddCompany}>
            <label>
              Company name
              <input value={name} onChange={(event) => setName(event.target.value)} required />
            </label>
            <label>
              ATS
              <select value={atsType} onChange={(event) => setAtsType(event.target.value as ATS)}>
                <option value="greenhouse">Greenhouse</option>
                <option value="lever">Lever</option>
                <option value="ashby">Ashby</option>
                <option value="workable">Workable (detection only)</option>
              </select>
            </label>
            <label>
              Board slug
              <input
                value={atsSlug}
                onChange={(event) => setAtsSlug(event.target.value)}
                placeholder="company-board"
                pattern="[A-Za-z0-9._-]{1,255}"
                required
              />
            </label>
            <label>
              Company website (optional)
              <input type="url" value={website} onChange={(event) => setWebsite(event.target.value)} />
            </label>
            <button disabled={busy}>{busy ? 'Saving…' : 'Add company'}</button>
            {atsType === 'workable' && (
              <p className="note">
                Workable apply URLs can be detected, but public collection is disabled because
                Workable’s documented jobs API requires an account token.
              </p>
            )}
          </form>
          <div className="company-list">
            {companies.map((company) => (
              <article className="company-item" key={company.id}>
                <strong>{company.name}</strong>
                <span>{company.ats_type} / {company.ats_slug}</span>
              </article>
            ))}
            {companies.length === 0 && <p>No companies configured yet.</p>}
          </div>
        </>
      )}
      {message && <p className="status-message" role="status">{message}</p>}
    </section>
  );
}
