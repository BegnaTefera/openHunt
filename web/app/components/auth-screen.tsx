'use client';

import { FormEvent, useEffect, useState } from 'react';
import { ApiError, AuthSession, logIn, signUp, warmUpServer } from '../../lib/api';

export default function AuthScreen({ onSignedIn }: { onSignedIn: (session: AuthSession) => void }) {
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    warmUpServer(); // wakes a sleeping free server while the person types
  }, []);

  function switchMode(next: 'login' | 'signup') {
    setMode(next);
    setError('');
    setPassword('');
    setConfirm('');
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    if (mode === 'signup') {
      if (password.length < 10) return setError('Use a password with at least 10 characters.');
      if (password !== confirm) return setError('The two passwords do not match.');
    }
    setBusy(true);
    const timer = window.setTimeout(() => setSlow(true), 5000);
    try {
      const session = mode === 'signup' ? await signUp(email, password) : await logIn(email, password);
      setPassword('');
      setConfirm('');
      onSignedIn(session);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not reach the server. Check your connection and try again.');
    } finally {
      window.clearTimeout(timer);
      setSlow(false);
      setBusy(false);
    }
  }

  const signup = mode === 'signup';

  return (
    <main className="auth-screen">
      <form className="auth-card" onSubmit={(event) => void submit(event)}>
        <div className="brand-mark">oh</div>
        <p className="eyebrow">Your focused job search</p>
        <h1>{signup ? 'Create your account.' : 'Welcome back.'}</h1>
        <p className="muted">{signup ? 'Set up your profile once and let openHunt do the searching.' : 'Sign in to review your matched opportunities.'}</p>
        <div className="auth-tabs" role="tablist">
          <button type="button" role="tab" aria-selected={!signup} className={`auth-tab${!signup ? ' active' : ''}`} onClick={() => switchMode('login')}>Sign in</button>
          <button type="button" role="tab" aria-selected={signup} className={`auth-tab${signup ? ' active' : ''}`} onClick={() => switchMode('signup')}>Create account</button>
        </div>
        <label>Email
          <input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </label>
        <label>Password
          <input type="password" autoComplete={signup ? 'new-password' : 'current-password'} value={password} onChange={(event) => setPassword(event.target.value)} minLength={signup ? 10 : undefined} required />
        </label>
        {signup && (
          <label>Repeat password
            <input type="password" autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} required />
          </label>
        )}
        {signup && <p className="hint">At least 10 characters. A few random words make a strong, easy password.</p>}
        {error && <p className="error-message" role="alert">{error}</p>}
        {slow && <p className="muted small-note">Waking up the free server. This can take up to a minute the first time.</p>}
        <button className="button button-primary" disabled={busy}>
          {busy ? (signup ? 'Creating account…' : 'Signing in…') : signup ? 'Create account' : 'Sign in'}
        </button>
      </form>
    </main>
  );
}
