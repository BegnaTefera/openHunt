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

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export async function apiRequest<T>(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...init.headers,
    },
    cache: 'no-store',
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      message = body.detail ?? message;
    } catch {
      // Keep the status-based message for non-JSON errors.
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export async function login(username: string, password: string): Promise<string> {
  const response = await fetch(`${apiBase}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
    cache: 'no-store',
  });
  if (!response.ok) throw new Error('Invalid username or password');
  const body = (await response.json()) as { access_token: string };
  return body.access_token;
}
