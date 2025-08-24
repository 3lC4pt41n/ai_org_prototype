const API = import.meta.env.VITE_API_URL || '/api';

export async function getJson(path: string) {
  const res = await fetch(`${API}${path}`, {
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${localStorage.getItem('token') || ''}`,
    },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function postJson<TBody extends object = any, TResp = any>(path: string, body: TBody) {
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      Authorization: `Bearer ${localStorage.getItem('token') || ''}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as TResp;
}

// --- Auth helpers ---
export type RegisterPayload = { name: string; email: string; password: string };
export type RegisterResponse = {
  id?: string;
  email?: string;
  access_token?: string;
  token_type?: string;
};

export async function register(payload: RegisterPayload): Promise<RegisterResponse> {
  return await postJson<RegisterPayload, RegisterResponse>('/api/register', payload);
}

export type LoginPayload = { email: string; password: string };
export type LoginResponse = { access_token: string; token_type?: string };

export async function login(payload: LoginPayload): Promise<LoginResponse> {
  // Accept either JSON or x-www-form-urlencoded depending on backend; try JSON first
  try {
    return await postJson<LoginPayload, LoginResponse>('/api/login', payload);
  } catch {
    const res = await fetch(`${API}/api/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        Accept: 'application/json',
      },
      body: new URLSearchParams({
        username: payload.email,
        password: payload.password,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    return (await res.json()) as LoginResponse;
  }
}
