/**
 * Build a robust API base:
 * - If VITE_API_URL is set (e.g. http://localhost:8000 or http://localhost:8000/api),
 *   strip trailing slashes and DO NOT assume it already contains /api.
 * - Always append exactly one "/api".
 * - Always join with a leading slash for the path.
 */
const _VITE = (import.meta.env.VITE_API_URL || "").replace(/\/+$/, "");
export const API_BASE =
  (_VITE ? `${_VITE}/api` : "/api").replace(/\/{2,}/g, "/"); // normalise accidental double slashes

export async function getJson(path: string) {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    headers: { Accept: "application/json", Authorization: `Bearer ${localStorage.getItem("token") || ""}` },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function postJson<TBody extends object = any, TResp = any>(path: string, body: TBody) {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      Authorization: `Bearer ${localStorage.getItem("token") || ""}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = "";
    try {
      msg = await res.text();
    } catch {
      /* ignore */
    }
    if (!msg) msg = `HTTP ${res.status} ${res.statusText}`;
    throw new Error(msg);
  }
  return (await res.json()) as TResp;
}

// Purpose anlegen (Pipeline)
export async function createPurpose(purpose: string) {
  return await postJson<{ purpose: string }, { purpose_id: string; requirements: string; blueprint: string }>(
    "/purposes",
    { purpose }
  );
}

// --- Auth helpers (explicit /api paths via API_BASE) ---
export type RegisterPayload = { name: string; email: string; password: string };
export type RegisterResponse = { id?: string; email?: string; access_token?: string; token_type?: string };

export async function register(payload: RegisterPayload): Promise<RegisterResponse> {
  return await postJson<RegisterPayload, RegisterResponse>("/register", payload);
}

export type LoginPayload = { email: string; password: string };
export type LoginResponse = { access_token: string; token_type?: string };

export async function login(payload: LoginPayload): Promise<LoginResponse> {
  // Send OAuth2-style form FIRST (what FastAPI expects) to avoid 422 spam,
  // then fallback to JSON only if needed.
  const res = await fetch(`${API_BASE}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
    body: new URLSearchParams({ username: payload.email, password: payload.password }),
  });
  if (res.ok) return (await res.json()) as LoginResponse;
  // graceful fallback (dev backends that accept JSON)
  return await postJson<LoginPayload, LoginResponse>("/login", payload);
}

export async function getTemplates() {
  return await getJson("/templates");
}

export async function getGraph() {
  return await getJson("/graph");
}

export async function getPurposeGraph(pid: string) {
  return await getJson(`/purposes/${pid}/graph`);
}

export async function postFeedback(pid: string, payload: any) {
  return await postJson(`/purposes/${pid}/feedback`, payload);
}
