export type JobStatus =
  | 'new'
  | 'shortlisted'
  | 'drafted'
  | 'applied'
  | 'replied'
  | 'interview'
  | 'rejected'
  | 'offer'
  | 'skipped';

export type Job = {
  id: number;
  title: string;
  source: string;
  url: string;
  company: string | null;
  company_id: number | null;
  location: string | null;
  seniority: string | null;
  description: string | null;
  tags: string[];
  posted_at: string | null;
  first_seen_at: string;
  score: number;
  score_reasons: string[];
  status: JobStatus;
};

export type JobDetail = Job & {
  employment_type: string | null;
  salary_text: string | null;
};

type CachedJobDetail = {
  job: JobDetail;
  complete: boolean;
  expiresAt: number;
};

const jobDetailCache = new Map<string, CachedJobDetail>();
const JOB_DETAIL_CACHE_TTL_MS = 30_000;
const MAX_CACHED_JOB_DETAILS = 100;

function jobDetailCacheKey(userId: number, jobId: string): string {
  return `${userId}:${jobId}`;
}

function cacheJobDetail(userId: number, jobId: string, job: JobDetail, complete: boolean): void {
  const key = jobDetailCacheKey(userId, jobId);
  jobDetailCache.delete(key);
  jobDetailCache.set(key, {
    job,
    complete,
    expiresAt: Date.now() + JOB_DETAIL_CACHE_TTL_MS,
  });
  while (jobDetailCache.size > MAX_CACHED_JOB_DETAILS) {
    const oldestKey = jobDetailCache.keys().next().value;
    if (oldestKey === undefined) break;
    jobDetailCache.delete(oldestKey);
  }
}

export function getCachedJobDetail(
  userId: number,
  jobId: string,
): { job: JobDetail; complete: boolean } | null {
  const key = jobDetailCacheKey(userId, jobId);
  const cached = jobDetailCache.get(key);
  if (!cached) return null;
  if (cached.expiresAt <= Date.now()) {
    jobDetailCache.delete(key);
    return null;
  }
  jobDetailCache.delete(key);
  jobDetailCache.set(key, cached);
  return { job: cached.job, complete: cached.complete };
}

export function cacheJobPreviews(userId: number, jobs: Job[]): void {
  for (const job of jobs) {
    cacheJobDetail(
      userId,
      String(job.id),
      { ...job, employment_type: null, salary_text: null },
      false,
    );
  }
}

export function cacheCompleteJobDetail(userId: number, job: JobDetail): void {
  cacheJobDetail(userId, String(job.id), job, true);
}

export type Company = {
  id: number;
  name: string;
  ats_type: 'greenhouse' | 'lever' | 'ashby' | 'workable';
  ats_slug: string;
  website: string | null;
};

export type ProfileProject = {
  name: string;
  description: string;
  url: string;
};

export type Profile = {
  skills: string[];
  target_roles: string[];
  seniority: string | null;
  country: string | null;
  timezones: string[];
  work_authorizations: string[];
  allowed_seniority: string[];
  custom_title_keywords?: string[];
  full_name?: string | null;
  headline?: string | null;
  summary?: string | null;
  projects?: ProfileProject[];
};

export type Draft = {
  job_id: number;
  cover_letter: string;
  answers: Record<string, string>;
  generated_by: string;
  warnings: string[];
};

export type ProviderBudget = {
  name: string;
  configured: boolean;
  used_today: number;
  daily_cap: number | null;
  used_this_month: number;
  monthly_cap: number | null;
  used_total: number;
  total_cap: number | null;
  remaining_now: number | null;
};

export type DiscoveryCandidate = {
  ats_type: string;
  ats_slug: string;
  source: string;
  status: 'added' | 'rejected';
  reason: string | null;
  company_id: number | null;
  found_at: string;
};

export type DiscoveryStatus = {
  providers: ProviderBudget[];
  added_total: number;
  rejected_total: number;
  last_run_at: string | null;
  last_run: {
    urls_seen?: number;
    candidates?: number;
    validated?: number;
    added?: number;
    rejected?: number;
    deferred?: number;
    added_companies?: string[];
    errors?: string[];
  } | null;
  recent_candidates: DiscoveryCandidate[];
};

export type Stats = {
  jobs_found: number;
  applied: number;
  replies: number;
  interviews: number;
  by_source: {
    source: string;
    jobs_found: number;
    applied: number;
    replies: number;
    interviews: number;
  }[];
};

export type User = {
  id: number;
  email: string;
  is_admin: boolean;
  onboarding_completed: boolean;
};

export type AuthSession = {
  access_token: string;
  expires_in: number;
  user: User;
};

export type RoleFamily = { key: string; label: string };

export type CvSuggestions = { full_name: string | null; skills: string[] };

export type CvInfo = {
  filename: string;
  content_type: string;
  size_bytes: number;
  uploaded_at: string;
  text_characters: number;
  suggestions: CvSuggestions;
};

export type GmailStatus = {
  connected: boolean;
  gmail_address: string | null;
  tracked_threads: number;
  oauth_configured: boolean;
  telegram_alerts_enabled: boolean;
};

export type GmailThread = {
  thread_id: string;
  subject: string;
  last_message_at: number;
  tracked: boolean;
  tracked_id: number | null;
  application_id: number | null;
};

export type GmailApplication = {
  id: number;
  job_id: number;
  title: string;
  company: string | null;
  status: string;
};

// The browser talks to /api on its own origin. Next.js forwards it to the real API
// (see next.config.mjs), which keeps the session cookie first-party and private.
const apiBase = '/api';
const CLIENT_HEADER = { 'X-OpenHunt-Client': 'web' };

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

// ---- session state: the access token lives only in memory ----

let accessToken: string | null = null;
let accessExpiresAt = 0;
let refreshInFlight: Promise<AuthSession | null> | null = null;
const sessionListeners = new Set<(user: User | null) => void>();

export function subscribeToSession(listener: (user: User | null) => void): () => void {
  sessionListeners.add(listener);
  return () => sessionListeners.delete(listener);
}

function notifySession(user: User | null) {
  sessionListeners.forEach((listener) => listener(user));
}

function storeSession(session: AuthSession) {
  accessToken = session.access_token;
  accessExpiresAt = Date.now() + session.expires_in * 1000;
}

function clearSession() {
  accessToken = null;
  accessExpiresAt = 0;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// Free hosts put idle servers to sleep. A sleeping server answers 502/503/504 or drops
// the request while it wakes up, so those are retried with growing pauses.
async function fetchWithWake(path: string, init: RequestInit, attempts = 5): Promise<Response> {
  let lastError: unknown;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(`${apiBase}${path}`, { ...init, cache: 'no-store', credentials: 'same-origin' });
      if (![502, 503, 504].includes(response.status) || attempt === attempts - 1) return response;
    } catch (error) {
      lastError = error;
      if (attempt === attempts - 1) break;
    }
    await sleep(Math.min(2500 * (attempt + 1), 9000));
  }
  throw lastError instanceof Error ? lastError : new Error('The server could not be reached. Try again in a minute.');
}

async function errorFrom(response: Response): Promise<ApiError> {
  let message = `Request failed (${response.status})`;
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === 'string') message = body.detail;
    else if (Array.isArray(body.detail)) message = 'Please check the highlighted values and try again.';
  } catch {
    // Keep the status-based message for non-JSON errors.
  }
  return new ApiError(message, response.status);
}

async function doRefresh(): Promise<AuthSession | null> {
  const attempt = () => fetchWithWake('/auth/refresh', { method: 'POST', headers: CLIENT_HEADER });
  let response = await attempt();
  if (response.status === 401) {
    // Another tab may have rotated the cookie a moment ago; the shared cookie jar now holds the new one.
    await sleep(500);
    response = await attempt();
  }
  if (!response.ok) {
    clearSession();
    return null;
  }
  const session = (await response.json()) as AuthSession;
  storeSession(session);
  return session;
}

/** Trade the refresh cookie for a new access token. One call at a time, across tabs too. */
export function refreshSession(): Promise<AuthSession | null> {
  if (!refreshInFlight) {
    const run = () => doRefresh();
    const locked = typeof navigator !== 'undefined' && 'locks' in navigator
      ? navigator.locks.request('openhunt-refresh', run)
      : run();
    refreshInFlight = locked.finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

async function usableToken(): Promise<string> {
  if (!accessToken || Date.now() > accessExpiresAt - 20_000) {
    const session = await refreshSession();
    if (!session) {
      notifySession(null);
      throw new ApiError('Your session has ended. Please sign in again.', 401);
    }
  }
  return accessToken as string;
}

/** `_token` is kept so older callers still compile; the real token is managed here. */
export async function apiRequest<T>(path: string, _token: string, init: RequestInit = {}): Promise<T> {
  const send = async () =>
    fetchWithWake(path, {
      ...init,
      headers: {
        Authorization: `Bearer ${await usableToken()}`,
        ...(init.body && !(init.headers as Record<string, string> | undefined)?.['Content-Type']
          ? { 'Content-Type': 'application/json' }
          : {}),
        ...init.headers,
      },
    });

  let response = await send();
  if (response.status === 401) {
    const session = await refreshSession();
    if (!session) {
      notifySession(null);
      throw new ApiError('Your session has ended. Please sign in again.', 401);
    }
    response = await send();
  }
  if (!response.ok) throw await errorFrom(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function uploadCv(file: File): Promise<CvInfo> {
  return apiRequest<CvInfo>('/profile/cv', '', {
    method: 'PUT',
    body: file,
    headers: {
      'Content-Type': file.type || 'application/octet-stream',
      'X-Filename': encodeURIComponent(file.name),
    },
  });
}

export async function downloadCv(filename: string): Promise<void> {
  const response = await fetchWithWake('/profile/cv/download', {
    headers: { Authorization: `Bearer ${await usableToken()}` },
  });
  if (!response.ok) throw await errorFrom(response);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

// ---- accounts ----

async function authCall(path: string, body: unknown, authorized = false): Promise<AuthSession> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (authorized) headers.Authorization = `Bearer ${await usableToken()}`;
  const response = await fetchWithWake(path, { method: 'POST', headers, body: JSON.stringify(body) });
  if (!response.ok) throw await errorFrom(response);
  const session = (await response.json()) as AuthSession;
  storeSession(session);
  return session;
}

export const signUp = (email: string, password: string) => authCall('/auth/signup', { email, password });
export const logIn = (email: string, password: string) => authCall('/auth/login', { email, password });

export const changePassword = (currentPassword: string, newPassword: string) =>
  authCall('/auth/change-password', { current_password: currentPassword, new_password: newPassword }, true);

export async function logOut(): Promise<void> {
  try {
    await fetchWithWake('/auth/logout', { method: 'POST', headers: CLIENT_HEADER }, 2);
  } finally {
    clearSession();
  }
}

export async function logOutEverywhere(): Promise<void> {
  try {
    await apiRequest<void>('/auth/logout-all', '', { method: 'POST' });
  } finally {
    clearSession();
  }
}

export async function deleteAccount(password: string): Promise<void> {
  await apiRequest<void>('/auth/account', '', { method: 'DELETE', body: JSON.stringify({ password }) });
  clearSession();
}

export const completeOnboarding = () => apiRequest<User>('/auth/onboarding/complete', '', { method: 'POST' });

// ---- Gmail reply tracking and shared Telegram notifications ----

export const getGmailStatus = () => apiRequest<GmailStatus>('/integrations/gmail', '');
export const getGmailThreads = () => apiRequest<GmailThread[]>('/integrations/gmail/threads', '');
export const getGmailApplications = () =>
  apiRequest<GmailApplication[]>('/integrations/gmail/applications', '');
export const getGmailAuthorizationUrl = () =>
  apiRequest<{ authorization_url: string }>('/integrations/gmail/connect', '');
export const trackGmailThread = (threadId: string, applicationId: number) =>
  apiRequest<void>('/integrations/gmail/threads', '', {
    method: 'POST',
    body: JSON.stringify({ thread_id: threadId, application_id: applicationId }),
  });
export const untrackGmailThread = (trackedId: number) =>
  apiRequest<void>(`/integrations/gmail/threads/${trackedId}`, '', { method: 'DELETE' });
export const disconnectGmail = () =>
  apiRequest<void>('/integrations/gmail', '', { method: 'DELETE' });

/** Wake a sleeping free server while the person is still typing their email. */
export function warmUpServer(): void {
  void fetch(`${apiBase}/health`, { cache: 'no-store' }).catch(() => undefined);
}
