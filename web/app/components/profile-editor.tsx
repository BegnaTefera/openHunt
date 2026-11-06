'use client';

import { FormEvent, useEffect, useState } from 'react';
import { apiRequest, CvSuggestions, Profile, ProfileProject, RoleFamily } from '../../lib/api';
import CvPanel from './cv-panel';
import ListField from './list-field';
import RolePicker, { RoleMode } from './role-picker';
import { useAuth } from './app-shell';

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
  target_roles: [],
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
  const [families, setFamilies] = useState<RoleFamily[]>([]);
  const [mode, setMode] = useState<RoleMode>('all');

  useEffect(() => {
    Promise.all([apiRequest<Profile>('/profile', token), apiRequest<RoleFamily[]>('/roles', token)])
      .then(([loaded, roles]) => {
        setProfile(loaded);
        setFamilies(roles);
        setMode(loaded.target_roles.length > 0 ? 'specific' : 'all');
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
        body: JSON.stringify({ ...profile, target_roles: mode === 'all' ? [] : profile.target_roles, projects: textToProjects(projectsText) }),
      });
      setProfile(saved);
      setMode(saved.target_roles.length > 0 ? 'specific' : 'all');
      setProjectsText(projectsToText(saved.projects));
      setMessage('Profile saved. New scores will use these preferences.');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save profile.');
    } finally {
      setSaving(false);
    }
  }

  function applySuggestions(suggestions: CvSuggestions) {
    setProfile((current) => ({
      ...current,
      full_name: current.full_name || suggestions.full_name,
      skills: Array.from(new Set([...current.skills, ...suggestions.skills])),
    }));
  }

  if (loading) return <div className="empty-state">Loading profile…</div>;

  return (
    <>
      <section className="page-heading">
        <div><p className="eyebrow">Make it yours</p><h1>Your profile</h1><p className="muted">Tune your match scoring and eligibility rules.</p></div>
      </section>
      <section className="content-panel">
        <div className="section-heading"><div><h2>Your CV</h2><p className="muted">Upload or replace your CV. Detected skills can be added to the form below.</p></div></div>
        <CvPanel onSuggestions={applySuggestions} />
      </section>
      <form className="content-panel profile-form" onSubmit={saveProfile}>
        <div className="form-section-heading"><h2>What you do</h2><p>These details help rank roles that fit your background.</p></div>
        <label>Skills <ListField value={profile.skills} onChange={(value) => setProfile({ ...profile, skills: value })} rows={3} placeholder="Python, TypeScript, PostgreSQL" /></label>
        <div className="form-section-heading"><h2>Jobs you want to see</h2><p>Choose every tech role, or only the types you care about.</p></div>
        <RolePicker
          families={families}
          mode={mode}
          onModeChange={setMode}
          selected={profile.target_roles}
          onSelectedChange={(keys) => setProfile({ ...profile, target_roles: keys })}
          keywords={profile.custom_title_keywords ?? []}
          onKeywordsChange={(words) => setProfile({ ...profile, custom_title_keywords: words })}
        />
        <label>Preferred seniority <input value={profile.seniority ?? ''} onChange={(event) => setProfile({ ...profile, seniority: event.target.value || null })} placeholder="Mid-level" /></label>
        <div className="form-section-heading"><h2>Eligibility</h2><p>Only explicitly stated restrictions are compared. Leave a field empty if you don’t want it checked.</p></div>
        <label>Your country <input value={profile.country ?? ''} onChange={(event) => setProfile({ ...profile, country: event.target.value || null })} placeholder="e.g. Kenya" /></label>
        <label>Your timezones <ListField value={profile.timezones} onChange={(value) => setProfile({ ...profile, timezones: value })} placeholder="EAT, UTC+3" /></label>
        <label>Work authorizations <ListField value={profile.work_authorizations} onChange={(value) => setProfile({ ...profile, work_authorizations: value })} placeholder="Kenya, United Kingdom" /></label>
        <label>Allow seniority levels <ListField value={profile.allowed_seniority} onChange={(value) => setProfile({ ...profile, allowed_seniority: value })} placeholder="senior, staff, principal, lead" /></label>
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
