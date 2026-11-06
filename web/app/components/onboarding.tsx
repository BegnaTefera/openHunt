'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { apiRequest, completeOnboarding, CvSuggestions, Profile, ProfileProject, RoleFamily } from '../../lib/api';
import { useAuth } from './app-shell';
import CvPanel from './cv-panel';
import ListField from './list-field';
import RolePicker, { RoleMode } from './role-picker';

const steps = ['Your CV', 'Roles', 'Level and location', 'About you'];
const seniorityLevels = ['senior', 'staff', 'principal', 'lead'];
const experienceOptions = [
  { label: 'Just starting out (entry-level or junior)', value: 'Junior', allowed: [] as string[] },
  { label: 'Some experience (mid-level)', value: 'Mid-level', allowed: [] as string[] },
  { label: 'Experienced (senior)', value: 'Senior', allowed: ['senior'] },
  { label: 'Very experienced (lead, staff or principal)', value: 'Lead', allowed: ['senior', 'staff', 'principal', 'lead'] },
];

const blankProfile: Profile = {
  skills: [], target_roles: [], seniority: null, country: null, timezones: [], work_authorizations: [],
  allowed_seniority: [], custom_title_keywords: [], full_name: null, headline: null, summary: null, projects: [],
};

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

export default function Onboarding() {
  const { token, user, setUser } = useAuth();
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [profile, setProfile] = useState<Profile>(blankProfile);
  const [families, setFamilies] = useState<RoleFamily[]>([]);
  const [mode, setMode] = useState<RoleMode>('all');
  const [projectsText, setProjectsText] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([apiRequest<Profile>('/profile', token), apiRequest<RoleFamily[]>('/roles', token)])
      .then(([loaded, roles]) => {
        setProfile({ ...blankProfile, ...loaded });
        setFamilies(roles);
        setMode(loaded.target_roles.length > 0 ? 'specific' : 'all');
        setProjectsText(projectsToText(loaded.projects));
      })
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : 'Could not load your profile.'))
      .finally(() => setLoading(false));
  }, [token]);

  function applySuggestions(suggestions: CvSuggestions) {
    setProfile((current) => ({
      ...current,
      full_name: current.full_name || suggestions.full_name,
      skills: Array.from(new Set([...current.skills, ...suggestions.skills])),
    }));
  }

  function currentProfile(): Profile {
    return {
      ...profile,
      target_roles: mode === 'all' ? [] : profile.target_roles,
      projects: textToProjects(projectsText),
    };
  }

  async function save(): Promise<boolean> {
    setSaving(true);
    setError('');
    try {
      const saved = await apiRequest<Profile>('/profile', token, { method: 'PUT', body: JSON.stringify(currentProfile()) });
      setProfile({ ...blankProfile, ...saved });
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save your profile.');
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function next() {
    if (step === 1 && mode === 'specific' && profile.target_roles.length === 0 && (profile.custom_title_keywords ?? []).length === 0) {
      setError('Pick at least one role type, or choose "Every tech role".');
      return;
    }
    if (!(await save())) return;
    setStep((value) => value + 1);
  }

  async function finish() {
    if (!(await save())) return;
    try {
      setUser(await completeOnboarding());
      router.replace('/');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not finish setup.');
    }
  }

  function chooseExperience(value: string) {
    const option = experienceOptions.find((item) => item.value === value);
    setProfile({ ...profile, seniority: option ? option.value : null, allowed_seniority: option ? option.allowed : profile.allowed_seniority });
  }

  function toggleSeniority(level: string) {
    const current = profile.allowed_seniority;
    setProfile({ ...profile, allowed_seniority: current.includes(level) ? current.filter((item) => item !== level) : [...current, level] });
  }

  if (loading) return <div className="loading-screen">Preparing your setup…</div>;

  const last = step === steps.length - 1;

  return (
    <div className="onboarding-card">
      <div className="brand-mark">oh</div>
      <p className="eyebrow">Welcome, {user.email}</p>
      <h1>Let’s set up your search</h1>
      <p className="muted">Four quick steps. You can change everything later on the Profile page.</p>
      <ol className="step-dots" aria-label="Progress">
        {steps.map((label, index) => (
          <li key={label} className={`step-dot${index === step ? ' current' : ''}${index < step ? ' done' : ''}`}>
            <span>{index + 1}</span>{label}
          </li>
        ))}
      </ol>

      {step === 0 && (
        <section className="onboarding-step">
          <h2>Add your CV</h2>
          <p className="muted">We read it on our side to prefill your name and skills, and keep it so you can reuse it. You can skip this and add it later.</p>
          <CvPanel autoApply onSuggestions={applySuggestions} />
        </section>
      )}

      {step === 1 && (
        <section className="onboarding-step">
          <h2>Which jobs do you want to see?</h2>
          <p className="muted">openHunt covers remote tech jobs of all kinds, not only developer roles.</p>
          <RolePicker
            families={families}
            mode={mode}
            onModeChange={setMode}
            selected={profile.target_roles}
            onSelectedChange={(keys) => setProfile({ ...profile, target_roles: keys })}
            keywords={profile.custom_title_keywords ?? []}
            onKeywordsChange={(words) => setProfile({ ...profile, custom_title_keywords: words })}
          />
        </section>
      )}

      {step === 2 && (
        <section className="onboarding-step profile-form">
          <h2>Your level and where you can work</h2>
          <label className="field-label">How experienced are you?
            <select value={profile.seniority ?? ''} onChange={(event) => chooseExperience(event.target.value)}>
              <option value="">Choose one</option>
              {experienceOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <fieldset className="checkbox-row">
            <legend>Also show jobs with these words in the title</legend>
            {seniorityLevels.map((level) => (
              <label key={level}><input type="checkbox" checked={profile.allowed_seniority.includes(level)} onChange={() => toggleSeniority(level)} /> {level}</label>
            ))}
            <small className="hint">Titles containing these words are hidden unless ticked.</small>
          </fieldset>
          <label className="field-label">Your country <input value={profile.country ?? ''} onChange={(event) => setProfile({ ...profile, country: event.target.value || null })} placeholder="e.g. Kenya" /></label>
          <label className="field-label">Your timezones <ListField value={profile.timezones} onChange={(value) => setProfile({ ...profile, timezones: value })} placeholder="EAT, UTC+3" /></label>
          <label className="field-label">Where you are allowed to work <ListField value={profile.work_authorizations} onChange={(value) => setProfile({ ...profile, work_authorizations: value })} placeholder="Kenya, United Kingdom" /></label>
          <p className="hint">Jobs that clearly require a different country, timezone or work permit are ranked as not eligible. Leave a field empty to skip that check.</p>
        </section>
      )}

      {step === 3 && (
        <section className="onboarding-step profile-form">
          <h2>About you</h2>
          <p className="muted">Cover letters only use what you write here and in your CV. Nothing is invented.</p>
          <label className="field-label">Full name <input value={profile.full_name ?? ''} onChange={(event) => setProfile({ ...profile, full_name: event.target.value || null })} /></label>
          <label className="field-label">Headline <input value={profile.headline ?? ''} onChange={(event) => setProfile({ ...profile, headline: event.target.value || null })} placeholder="Backend developer focused on Python APIs" /></label>
          <label className="field-label">Skills <ListField value={profile.skills} onChange={(value) => setProfile({ ...profile, skills: value })} rows={3} placeholder="Python, TypeScript, PostgreSQL" /></label>
          <label className="field-label">Short summary <textarea rows={3} value={profile.summary ?? ''} onChange={(event) => setProfile({ ...profile, summary: event.target.value || null })} placeholder="Two or three honest sentences about your background" /></label>
          <label className="field-label">Projects <textarea rows={3} value={projectsText} onChange={(event) => setProjectsText(event.target.value)} placeholder="One per line: Name | what it does | https://link" /></label>
        </section>
      )}

      {error && <p className="error-message" role="alert">{error}</p>}
      <div className="onboarding-actions">
        {step > 0 ? <button type="button" className="button button-secondary" disabled={saving} onClick={() => { setError(''); setStep(step - 1); }}>Back</button> : <span />}
        {last
          ? <button type="button" className="button button-primary" disabled={saving} onClick={() => void finish()}>{saving ? 'Saving…' : 'Finish setup'}</button>
          : <button type="button" className="button button-primary" disabled={saving} onClick={() => void next()}>{saving ? 'Saving…' : step === 0 ? 'Continue' : 'Next'}</button>}
      </div>
    </div>
  );
}
