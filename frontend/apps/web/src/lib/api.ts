import axios, { AxiosError } from 'axios';

// Resolve API base once. In Docker we proxy /api via nginx; in dev you can set VITE_API_URL
export const API_BASE = (import.meta as any).env?.VITE_API_URL?.replace(/\/+$/, '') || '/api';

export const api = axios.create({
  baseURL: API_BASE,
});

// Attach token on every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers = config.headers ?? {};
    (config.headers as any).Authorization = `Bearer ${token}`;
  }
  return config;
});

// Global 401 handling
api.interceptors.response.use(
  (resp) => resp,
  (err: AxiosError) => {
    const status = err.response?.status;
    if (status === 401) {
      try {
        localStorage.removeItem('token');
      } catch {}
      // Do a hard redirect to clear app state
      window.location.href = '/login';
    }
    return Promise.reject(err);
  },
);

// Helper wrappers with AbortController support (Axios v1 supports `signal`)
export async function getJson<T = any>(
  url: string,
  opts?: { signal?: AbortSignal; headers?: Record<string, string> },
): Promise<T> {
  const resp = await api.get<T>(url, {
    signal: opts?.signal,
    headers: opts?.headers,
  });
  return resp.data as T;
}

export async function postJson<T = any>(
  url: string,
  body?: any,
  opts?: { signal?: AbortSignal; headers?: Record<string, string> },
): Promise<T> {
  const resp = await api.post<T>(url, body ?? {}, {
    signal: opts?.signal,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...(opts?.headers ?? {}),
    },
  });
  return resp.data as T;
}

export async function putJson<T = any>(
  url: string,
  body?: any,
  opts?: { signal?: AbortSignal; headers?: Record<string, string> },
): Promise<T> {
  const resp = await api.put<T>(url, body ?? {}, {
    signal: opts?.signal,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...(opts?.headers ?? {}),
    },
  });
  return resp.data as T;
}

export function approveArtifact(
  id: string,
  opts?: { signal?: AbortSignal },
): Promise<{ status: string }> {
  return postJson<{ status: string }>(`/artifacts/${id}/approve`, undefined, opts);
}
