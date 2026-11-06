'use client';

import { ChangeEvent, useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, apiRequest, CvInfo, CvSuggestions, downloadCv, uploadCv } from '../../lib/api';
import { useAuth } from './app-shell';

function formatSize(bytes: number): string {
  return bytes > 1_000_000 ? `${(bytes / 1_000_000).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1000))} KB`;
}

export default function CvPanel({
  autoApply = false,
  onSuggestions,
}: {
  autoApply?: boolean;
  onSuggestions?: (suggestions: CvSuggestions) => void;
}) {
  const { token } = useAuth();
  const input = useRef<HTMLInputElement>(null);
  const [cv, setCv] = useState<CvInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const load = useCallback(async () => {
    try {
      setCv(await apiRequest<CvInfo | null>('/profile/cv', token));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load your CV.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const saved = await uploadCv(file);
      setCv(saved);
      const found = saved.suggestions.skills.length;
      if (autoApply && onSuggestions) {
        onSuggestions(saved.suggestions);
        setMessage(found ? `Read your CV and found ${found} skills. You can review them in the next steps.` : 'Read your CV. No skills were detected, so add them in the next steps.');
      } else {
        setMessage(found ? `Uploaded. ${found} skills were detected in it.` : 'Uploaded.');
      }
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not upload the file. Try again.');
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm('Remove your CV from openHunt?')) return;
    setBusy(true);
    setError('');
    try {
      await apiRequest<void>('/profile/cv', token, { method: 'DELETE' });
      setCv(null);
      setMessage('Your CV was removed.');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not remove the CV.');
    } finally {
      setBusy(false);
    }
  }

  async function download() {
    if (!cv) return;
    try {
      await downloadCv(cv.filename);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not download the CV.');
    }
  }

  if (loading) return <p className="muted">Checking for your CV…</p>;

  return (
    <div className="cv-panel">
      {cv ? (
        <div className="cv-summary">
          <div><strong>{cv.filename}</strong><span>{formatSize(cv.size_bytes)} · uploaded {new Date(cv.uploaded_at).toLocaleDateString()}</span></div>
          <div className="inline-actions">
            <button type="button" className="button button-secondary" onClick={() => void download()}>Download</button>
            <button type="button" className="button button-secondary" disabled={busy} onClick={() => input.current?.click()}>Replace</button>
            <button type="button" className="button button-secondary" disabled={busy} onClick={() => void remove()}>Remove</button>
          </div>
        </div>
      ) : (
        <button type="button" className="file-drop" disabled={busy} onClick={() => input.current?.click()}>
          <strong>{busy ? 'Reading your CV…' : 'Upload your CV'}</strong>
          <span>PDF, Word (.docx) or plain text, up to 3 MB</span>
        </button>
      )}
      <input ref={input} type="file" hidden accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain" onChange={(event) => void handleFile(event)} />
      {cv && !autoApply && onSuggestions && cv.suggestions.skills.length > 0 && (
        <button type="button" className="button button-secondary" onClick={() => { onSuggestions(cv.suggestions); setMessage('Detected skills were added to the form. Save your profile to keep them.'); }}>
          Add {cv.suggestions.skills.length} detected skills to my profile
        </button>
      )}
      {error && <p className="error-message" role="alert">{error}</p>}
      {message && <p className="success-message" role="status">{message}</p>}
      <p className="hint">Your CV is stored privately for your account. Drafts never send your email or phone number to any AI service.</p>
    </div>
  );
}
