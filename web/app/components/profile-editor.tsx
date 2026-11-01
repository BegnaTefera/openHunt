'use client';

import { FormEvent, useEffect, useState } from 'react';
import { apiRequest, Profile, ProfileProject } from '../../lib/api';
import { useAuth } from './app-shell';

function splitLines(value: string): string[] {
  return value.split(/[\n,]/).map((part) => part.trim()).filter(Boolean);
}

// One project per line: "Name | what it does | https://link" (the last two parts are optional).
function projectsToText(projects: ProfileProject[] | undefined): string {
  return (projects ?? []).map((item) => [item.name, item.description, item.url].filter((part, index) => part || index === 0).join(' | ')).join('\n');
}

function textToProjects(value: string): ProfileProject[] {
  return value
    .split('\n')
    .map((line) => line.split('|').map((part) => part.trim()))
    .filter((parts) => parts[0])
    .map((parts) => ({ name: parts[0], description: parts[1] ?? '', url: parts[2] ?? '' }));
}

const emptyProfile: Profile = {
  skills: [],
  target_roles: ['backend', 'full-stack'],
  seniority: null,
  country: null,
  timezones: [],
  work_authorizations: [],
  allowed_seniority: [],
  full_name: null,
  headline: null,
  summary: null,
  projects: [],
};

export default function ProfileEditor() {
  const { token } = useAuth();
  const [profile, setProfile] = useState<Profile>(emptyProfile);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [projectsText, setProjectsText] = useState('');

  useEffect(() => {
    apiRequest<Profile>('/profile', token)
      .then((loaded) => {
        setProfile(loaded);
        setProjectsText(projectsToText(loaded.projects));
      })
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : 'Could not load profile.'))
      .finally(() => setLoading(false));
  }, [token]);

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const saved = await apiRequest<Profile>('/profile', token, {
        method: 'PUT',
        body: JSON.stringify({ ...profile, projects: textToProjects(projectsText) }),
      });
      setProfile(saved);
      setProjectsText(projectsToText(saved.projects));
      setMessage('Profile saved. New scores will use these preferences.');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save profile.');
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="empty-state">Loading profile…</div>;

  return (
    <>
      <section className="page-heading">
        <div><p className="eyebrow">Make it yours</p><h1>Your profile</h1><p className="muted">Tune your match scoring and eligibility rules.</p></div>
      </section>
      <form className="content-panel profile-form" onSubmit={saveProfile}>
        <div className="form-section-heading"><h2>What you do</h2><p>These details help rank roles that fit your background.</p></div>
        <label>Skills <textarea rows={3} value={profile.skills.join(', ')} onChange={(event) => setProfile({ ...profile, skills: splitLines(event.target.value) })} placeholder="Python, TypeScript, PostgreSQL" /></label>
        <label>Target roles <textarea rows={2} value={profile.target_roles.join(', ')} onChange={(event) => setProfile({ ...profile, target_roles: splitLines(event.target.value) })} placeholder="backend, full-stack" /></label>
        <label>Preferred seniority <input value={profile.seniority ?? ''} onChange={(event) => setProfile({ ...profile, seniority: event.target.value || null })} placeholder="Mid-level" /></label>
        <div className="form-section-heading"><h2>Eligibility</h2><p>Only explicitly stated restrictions are compared. Leave a field empty if you don’t want it checked.</p></div>
        <label>Your country <input value={profile.country ?? ''} onChange={(event) => setProfile({ ...profile, country: event.target.value || null })} placeholder="e.g. Kenya" /></label>
        <label>Your timezones <textarea rows={2} value={profile.timezones.join(', ')} onChange={(event) => setProfile({ ...profile, timezones: splitLines(event.target.value) })} placeholder="EAT, UTC+3" /></label>
        <label>Work authorizations <textarea rows={2} value={profile.work_authorizations.join(', ')} onChange={(event) => setProfile({ ...profile, work_authorizations: splitLines(event.target.value) })} placeholder="Kenya, United Kingdom" /></label>
        <label>Allow seniority levels <textarea rows={2} value={profile.allowed_seniority.join(', ')} onChange={(event) => setProfile({ ...profile, allowed_seniority: splitLines(event.target.value) })} placeholder="senior, staff, principal, lead" /></label>
        <div className="form-section-heading"><h2>For application drafts</h2><p>Cover letters only use what you write here. Nothing is invented.</p></div>
        <label>Full name <input value={profile.full_name ?? ''} onChange={(event) => setProfile({ ...profile, full_name: event.target.value || null })} placeholder="Used to sign your letters" /></label>
        <label>Headline <input value={profile.headline ?? ''} onChange={(event) => setProfile({ ...profile, headline: event.target.value || null })} placeholder="Backend developer focused on Python APIs" /></label>
        <label>Short summary <textarea rows={3} value={profile.summary ?? ''} onChange={(event) => setProfile({ ...profile, summary: event.target.value || null })} placeholder="Two or three honest sentences about your background" /></label>
        <label>Projects <textarea rows={4} value={projectsText} onChange={(event) => setProjectsText(event.target.value)} placeholder="One per line: Name | what it does | https://link" /></label>
        {error && <p className="error-message" role="alert">{error}</p>}
        {message && <p className="success-message" role="status">{message}</p>}
        <button className="button button-primary form-submit" disabled={saving}>{saving ? 'Saving…' : 'Save profile'}</button>
      </form>
    </>
  );
}
