'use client';

import { FormEvent, useCallback, useEffect, useState } from 'react';
import {
  changePassword,
  deleteAccount,
  disconnectGmail,
  getGmailApplications,
  getGmailAuthorizationUrl,
  getGmailStatus,
  getGmailThreads,
  GmailApplication,
  GmailStatus,
  GmailThread,
  logOutEverywhere,
  trackGmailThread,
  untrackGmailThread,
} from '../../lib/api';
import { useAuth } from './app-shell';

export default function AccountPage() {
  const { user, signOut } = useAuth();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [deletePassword, setDeletePassword] = useState('');
  const [confirmText, setConfirmText] = useState('');
  const [deleteError, setDeleteError] = useState('');
  const [gmailStatus, setGmailStatus] = useState<GmailStatus | null>(null);
  const [gmailThreads, setGmailThreads] = useState<GmailThread[]>([]);
  const [gmailApplications, setGmailApplications] = useState<GmailApplication[]>([]);
  const [selectedApplications, setSelectedApplications] = useState<Record<string, string>>({});
  const [integrationError, setIntegrationError] = useState('');
  const [integrationMessage, setIntegrationMessage] = useState('');
  const [integrationBusy, setIntegrationBusy] = useState(false);

  const loadGmail = useCallback(async () => {
    setIntegrationError('');
    try {
      const current = await getGmailStatus();
      setGmailStatus(current);
      if (current.connected) {
        const [threads, applications] = await Promise.all([
          getGmailThreads(),
          getGmailApplications(),
        ]);
        setGmailThreads(threads);
        setGmailApplications(applications);
        setSelectedApplications((previous) => {
          const next = { ...previous };
          threads.forEach((thread) => {
            if (thread.application_id) next[thread.thread_id] = String(thread.application_id);
          });
          return next;
        });
      } else {
        setGmailThreads([]);
        setGmailApplications([]);
      }
    } catch (cause) {
      setIntegrationError(cause instanceof Error ? cause.message : 'Could not load integrations.');
    }
  }, []);

  useEffect(() => {
    void loadGmail();
    const callback = new URLSearchParams(window.location.search).get('gmail');
    if (callback) {
      setIntegrationMessage(callback === 'connected'
        ? 'Gmail is connected. Choose a sent thread below to start tracking replies.'
        : 'Gmail could not be connected. Check the OAuth settings and try again.');
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, [loadGmail]);

  async function connectGmail() {
    setIntegrationBusy(true);
    setIntegrationError('');
    try {
      const result = await getGmailAuthorizationUrl();
      window.location.assign(result.authorization_url);
    } catch (cause) {
      setIntegrationError(cause instanceof Error ? cause.message : 'Could not start Gmail authorization.');
      setIntegrationBusy(false);
    }
  }

  async function disconnectGmailAccount() {
    setIntegrationBusy(true);
    setIntegrationError('');
    try {
      await disconnectGmail();
      setIntegrationMessage('Gmail was disconnected and imported message metadata was removed.');
      await loadGmail();
    } catch (cause) {
      setIntegrationError(cause instanceof Error ? cause.message : 'Could not disconnect Gmail.');
    } finally {
      setIntegrationBusy(false);
    }
  }

  async function linkThread(threadId: string) {
    const applicationId = Number(selectedApplications[threadId]);
    if (!applicationId) return;
    setIntegrationBusy(true);
    setIntegrationError('');
    try {
      await trackGmailThread(threadId, applicationId);
      setIntegrationMessage('Thread linked. New replies will update the application and send a Telegram alert.');
      await loadGmail();
    } catch (cause) {
      setIntegrationError(cause instanceof Error ? cause.message : 'Could not track this thread.');
    } finally {
      setIntegrationBusy(false);
    }
  }

  async function unlinkThread(trackedId: number) {
    setIntegrationBusy(true);
    setIntegrationError('');
    try {
      await untrackGmailThread(trackedId);
      setIntegrationMessage('Thread tracking stopped.');
      await loadGmail();
    } catch (cause) {
      setIntegrationError(cause instanceof Error ? cause.message : 'Could not stop tracking this thread.');
    } finally {
      setIntegrationBusy(false);
    }
  }

  async function updatePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setMessage('');
    if (next !== repeat) return setError('The two new passwords do not match.');
    setBusy(true);
    try {
      await changePassword(current, next);
      setCurrent('');
      setNext('');
      setRepeat('');
      setMessage('Password changed. You were signed out on all your other devices.');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not change the password.');
    } finally {
      setBusy(false);
    }
  }

  async function signOutEverywhere() {
    try {
      await logOutEverywhere();
    } finally {
      await signOut();
    }
  }

  async function removeAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setDeleteError('');
    setBusy(true);
    try {
      await deleteAccount(deletePassword);
      await signOut();
    } catch (cause) {
      setDeleteError(cause instanceof Error ? cause.message : 'Could not delete the account.');
      setBusy(false);
    }
  }

  return (
    <>
      <section className="page-heading">
        <div><p className="eyebrow">Security</p><h1>Your account</h1><p className="muted">Signed in as {user.email}{user.is_admin ? ' · admin' : ''}</p></div>
      </section>
      <div className="settings-layout">
        <section className="content-panel integration-panel">
          <div className="section-heading">
            <div>
              <h2>Gmail replies &amp; Telegram alerts</h2>
              <p className="muted">
                Connect Gmail to monitor sent application threads. A linked thread starts tracking from now;
                older messages are not imported as new replies.
              </p>
            </div>
          </div>
          <div className="inline-actions">
            {!gmailStatus?.connected ? (
              <button
                className="button button-primary"
                disabled={!gmailStatus?.oauth_configured || integrationBusy}
                onClick={() => void connectGmail()}
              >
                Connect Gmail
              </button>
            ) : (
              <>
                <span className="muted">Connected as {gmailStatus.gmail_address}</span>
                <button className="button button-secondary" disabled={integrationBusy} onClick={() => void loadGmail()}>
                  Refresh sent threads
                </button>
                <button className="button button-secondary" disabled={integrationBusy} onClick={() => void disconnectGmailAccount()}>
                  Disconnect Gmail
                </button>
              </>
            )}
          </div>
          {gmailStatus && !gmailStatus.oauth_configured && (
            <p className="muted small-note">Gmail OAuth is not configured by the server administrator.</p>
          )}
          {gmailStatus && (
            <p className="muted small-note">
              Telegram alerts are {gmailStatus.telegram_alerts_enabled ? 'enabled' : 'not configured'}.
              {gmailStatus.telegram_alerts_enabled
                ? ' This workspace sends alerts from all accounts to the same configured chat.'
                : ' The server administrator must configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.'}
            </p>
          )}
          {integrationError && <p className="error-message" role="alert">{integrationError}</p>}
          {integrationMessage && <p className="success-message" role="status">{integrationMessage}</p>}
          {gmailStatus?.connected && (
            <div className="gmail-thread-list">
              <p className="results-label">{gmailStatus.tracked_threads} tracked thread(s)</p>
              {gmailThreads.length === 0 && <p className="muted">No recent sent threads found in Gmail.</p>}
              {gmailThreads.map((thread) => (
                <div className="gmail-thread-row" key={thread.thread_id}>
                  <div>
                    <strong>{thread.subject}</strong>
                    <p className="muted small-note">
                      {new Date(thread.last_message_at).toLocaleString()}
                      {thread.tracked ? ' · tracking replies' : ''}
                    </p>
                  </div>
                  {thread.tracked && thread.tracked_id ? (
                    <button className="button button-secondary" disabled={integrationBusy} onClick={() => void unlinkThread(thread.tracked_id!)}>
                      Stop tracking
                    </button>
                  ) : (
                    <div className="gmail-track-controls">
                      <select
                        aria-label={`Application for ${thread.subject}`}
                        value={selectedApplications[thread.thread_id] ?? ''}
                        onChange={(event) => setSelectedApplications((current) => ({
                          ...current,
                          [thread.thread_id]: event.target.value,
                        }))}
                      >
                        <option value="">Choose application</option>
                        {gmailApplications.map((application) => (
                          <option key={application.id} value={application.id}>
                            {application.title} · {application.company ?? 'Company'}
                          </option>
                        ))}
                      </select>
                      <button
                        className="button button-secondary"
                        disabled={integrationBusy || !selectedApplications[thread.thread_id]}
                        onClick={() => void linkThread(thread.thread_id)}
                      >
                        Track thread
                      </button>
                    </div>
                  )}
                </div>
              ))}
              {gmailApplications.length === 0 && (
                <p className="muted small-note">Mark an application as applied to make it available for thread linking.</p>
              )}
            </div>
          )}
        </section>
        <form className="content-panel profile-form" onSubmit={(event) => void updatePassword(event)}>
          <div className="section-heading"><div><h2>Change password</h2><p className="muted">At least 10 characters. Changing it signs you out everywhere else.</p></div></div>
          <label>Current password <input type="password" autoComplete="current-password" value={current} onChange={(event) => setCurrent(event.target.value)} required /></label>
          <label>New password <input type="password" autoComplete="new-password" minLength={10} value={next} onChange={(event) => setNext(event.target.value)} required /></label>
          <label>Repeat new password <input type="password" autoComplete="new-password" value={repeat} onChange={(event) => setRepeat(event.target.value)} required /></label>
          {error && <p className="error-message" role="alert">{error}</p>}
          {message && <p className="success-message" role="status">{message}</p>}
          <button className="button button-primary" disabled={busy}>Change password</button>
        </form>
        <section className="content-panel">
          <div className="section-heading"><div><h2>Sessions</h2><p className="muted">Lost a device, or used a shared computer? End every session.</p></div></div>
          <div className="inline-actions">
            <button className="button button-secondary" onClick={() => void signOut()}>Sign out here</button>
            <button className="button button-secondary" onClick={() => void signOutEverywhere()}>Sign out everywhere</button>
          </div>
        </section>
        <form className="content-panel profile-form danger-zone" onSubmit={(event) => void removeAccount(event)}>
          <div className="section-heading"><div><h2>Delete account</h2><p className="muted">Permanently removes your profile, CV, drafts and application history. This cannot be undone.</p></div></div>
          <label>Your password <input type="password" autoComplete="current-password" value={deletePassword} onChange={(event) => setDeletePassword(event.target.value)} required /></label>
          <label>Type DELETE to confirm <input value={confirmText} onChange={(event) => setConfirmText(event.target.value)} /></label>
          {deleteError && <p className="error-message" role="alert">{deleteError}</p>}
          <button className="button button-danger" disabled={busy || confirmText !== 'DELETE'}>Delete my account</button>
        </form>
      </div>
    </>
  );
}
