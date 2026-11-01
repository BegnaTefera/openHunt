'use client';

import { useCallback, useEffect, useState } from 'react';
import { apiRequest, Draft } from '../../lib/api';
import { useAuth } from './app-shell';

const answerLabels: Record<string, string> = {
  why_this_role: 'Why this role',
  relevant_experience: 'Relevant experience',
};

export default function DraftPanel({ jobId, onDrafted }: { jobId: string; onDrafted: () => void }) {
  const { token } = useAuth();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [letter, setLetter] = useState('');
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const apply = useCallback((value: Draft) => {
    setDraft(value);
    setLetter(value.cover_letter);
    setAnswers(value.answers);
  }, []);

  useEffect(() => {
    apiRequest<Draft>(`/jobs/${jobId}/draft`, token)
      .then(apply)
      .catch(() => setDraft(null)); // 404 simply means there is no draft yet
  }, [jobId, token, apply]);

  async function generate(useAi: boolean) {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      apply(await apiRequest<Draft>(`/jobs/${jobId}/draft?use_ai=${useAi}`, token, { method: 'POST' }));
      onDrafted();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not write a draft.');
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      apply(await apiRequest<Draft>(`/jobs/${jobId}/draft`, token, {
        method: 'PUT',
        body: JSON.stringify({ cover_letter: letter, answers }),
      }));
      setMessage('Saved.');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save the draft.');
    } finally {
      setBusy(false);
    }
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setMessage('Copied to the clipboard.');
    } catch {
      setError('Copying is not available in this browser. Select the text and copy it manually.');
    }
  }

  return (
    <section className="content-panel">
      <h2>Application draft</h2>
      <p className="muted small-note">Drafts only use facts from your Profile. Always read and edit before sending anything.</p>
      <div className="draft-actions">
        <button className="button button-primary" disabled={busy} onClick={() => void generate(true)}>
          {busy ? 'Working…' : draft ? 'Rewrite draft' : 'Write draft'}
        </button>
        <button className="button button-secondary" disabled={busy} onClick={() => void generate(false)}>
          Use template only
        </button>
      </div>
      {error && <p className="error-message" role="alert">{error}</p>}
      {message && <p className="success-message" role="status">{message}</p>}
      {draft && (
        <>
          <p className="muted small-note">Written by: {draft.generated_by}</p>
          {draft.warnings.length > 0 && (
            <ul className="warning-list">
              {draft.warnings.map((warning) => <li key={warning}>{warning}</li>)}
            </ul>
          )}
          <label className="draft-field">Cover letter
            <textarea className="draft-textarea" rows={14} value={letter} onChange={(event) => setLetter(event.target.value)} />
          </label>
          {Object.entries(answers).map(([key, value]) => (
            <label className="draft-field" key={key}>{answerLabels[key] ?? key}
              <textarea className="draft-textarea" rows={3} value={value} onChange={(event) => setAnswers({ ...answers, [key]: event.target.value })} />
            </label>
          ))}
          <div className="draft-actions">
            <button className="button button-primary" disabled={busy} onClick={() => void save()}>Save edits</button>
            <button className="button button-secondary" onClick={() => void copy(letter)}>Copy letter</button>
          </div>
        </>
      )}
    </section>
  );
}
