'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { FormEvent, ReactNode, createContext, useContext, useEffect, useState } from 'react';
import { login } from '../../lib/api';

type AuthContextValue = {
  token: string;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AppShell');
  return value;
}

const navigation = [
  { href: '/', label: 'Jobs' },
  { href: '/pipeline', label: 'Pipeline' },
  { href: '/stats', label: 'Stats' },
  { href: '/profile', label: 'Profile' },
  { href: '/companies', label: 'Companies' },
  { href: '/discovery', label: 'Discovery' },
];

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [token, setToken] = useState('');
  const [ready, setReady] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setToken(window.localStorage.getItem('openhunt-token') ?? '');
    setReady(true);
  }, []);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const accessToken = await login(username, password);
      window.localStorage.setItem('openhunt-token', accessToken);
      setToken(accessToken);
      setPassword('');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not sign in.');
    } finally {
      setBusy(false);
    }
  }

  function signOut() {
    window.localStorage.removeItem('openhunt-token');
    setToken('');
  }

  if (!ready) {
    return <main className="loading-screen">Loading openHunt…</main>;
  }

  if (!token) {
    return (
      <main className="auth-screen">
        <form className="auth-card" onSubmit={handleLogin}>
          <div className="brand-mark">oh</div>
          <p className="eyebrow">Your focused job search</p>
          <h1>Welcome back.</h1>
          <p className="muted">Sign in to review your matched opportunities.</p>
          <label>
            Username
            <input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required />
          </label>
          <label>
            Password
            <input
              autoComplete="current-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          {error && <p className="error-message" role="alert">{error}</p>}
          <button className="button button-primary" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </main>
    );
  }

  return (
    <AuthContext.Provider value={{ token }}>
      <div className="app-frame">
        <aside className="sidebar">
          <Link className="brand" href="/">
            <span className="brand-mark">oh</span>
            <span>openHunt</span>
          </Link>
          <p className="nav-label">Workspace</p>
          <nav className="main-nav" aria-label="Main navigation">
            {navigation.map((item) => (
              <Link
                className={`nav-link${pathname === item.href ? ' active' : ''}`}
                href={item.href}
                key={item.href}
              >
                <span className="nav-dot" />
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <span className="online-dot" /> Collectors running
            <button className="sign-out" onClick={signOut}>Sign out</button>
          </div>
        </aside>
        <main className="main-area">
          <header className="topbar">
            <div className="mobile-brand"><span className="brand-mark">oh</span> openHunt</div>
            <div className="topbar-note">Your next move, made clearer.</div>
            <button className="topbar-signout" onClick={signOut}>Sign out</button>
            <div className="avatar" aria-label="Account">Y</div>
          </header>
          <div className="page-content">{children}</div>
        </main>
      </div>
    </AuthContext.Provider>
  );
}
