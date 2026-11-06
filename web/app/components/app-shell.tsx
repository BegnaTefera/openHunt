'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { ReactNode, createContext, useCallback, useContext, useEffect, useState } from 'react';
import { AuthSession, User, logOut, refreshSession, subscribeToSession } from '../../lib/api';
import AuthScreen from './auth-screen';

type AuthContextValue = {
  // The real access token is kept in memory by lib/api; this stays constant on purpose so
  // pages do not reload their data every time the session quietly renews.
  token: string;
  user: User;
  setUser: (user: User) => void;
  signOut: () => Promise<void>;
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
  { href: '/account', label: 'Account' },
];

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [phase, setPhase] = useState<'loading' | 'out' | 'in'>('loading');
  const [user, setUser] = useState<User | null>(null);
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(true), 4000);
    refreshSession().then((session) => {
      if (session) {
        setUser(session.user);
        setPhase('in');
      } else {
        setPhase('out');
      }
    });
    const unsubscribe = subscribeToSession((next) => {
      if (!next) {
        setUser(null);
        setPhase('out');
      }
    });
    return () => {
      window.clearTimeout(timer);
      unsubscribe();
    };
  }, []);

  const needsOnboarding = phase === 'in' && user !== null && !user.onboarding_completed && pathname !== '/onboarding';

  useEffect(() => {
    if (needsOnboarding) router.replace('/onboarding');
  }, [needsOnboarding, router]);

  const signOut = useCallback(async () => {
    await logOut();
    setUser(null);
    setPhase('out');
    router.replace('/');
  }, [router]);

  function handleSignedIn(session: AuthSession) {
    setUser(session.user);
    setPhase('in');
  }

  if (phase === 'loading' || needsOnboarding) {
    return (
      <main className="loading-screen">
        <div>Loading openHunt…{slow && <p className="muted small-note">Waking up the free server. This can take up to a minute.</p>}</div>
      </main>
    );
  }

  if (phase === 'out' || !user) return <AuthScreen onSignedIn={handleSignedIn} />;

  const context: AuthContextValue = { token: 'session', user, setUser, signOut };

  if (pathname === '/onboarding') {
    return (
      <AuthContext.Provider value={context}>
        <main className="onboarding-screen">{children}</main>
      </AuthContext.Provider>
    );
  }

  return (
    <AuthContext.Provider value={context}>
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
            <button className="sign-out" onClick={() => void signOut()}>Sign out</button>
          </div>
        </aside>
        <main className="main-area">
          <header className="topbar">
            <div className="mobile-brand"><span className="brand-mark">oh</span> openHunt</div>
            <div className="topbar-note">Your next move, made clearer.</div>
            <button className="topbar-signout" onClick={() => void signOut()}>Sign out</button>
            <Link className="avatar" href="/account" aria-label={`Account: ${user.email}`}>{user.email.slice(0, 1).toUpperCase()}</Link>
          </header>
          <div className="page-content">{children}</div>
        </main>
      </div>
    </AuthContext.Provider>
  );
}
