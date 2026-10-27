import type { DocumentDetail, DocumentInput, DocumentSummary, Equipment, Recipient, User } from "./types";

const TOKEN_KEY = "xezer-esign-token";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

let token: string | null = (() => {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
})();

function setToken(value: string | null) {
  token = value;
  try {
    if (value) localStorage.setItem(TOKEN_KEY, value);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable — keep the session in memory only */
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && path !== "/me") {
    // Session lost (e.g. the demo database was reset from the command line).
    window.dispatchEvent(new Event("esign-session-expired"));
  }
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "The request could not be completed.";
    throw new ApiError(res.status, data.code ?? "ERROR", detail);
  }
  return data as T;
}

export const api = {
  hasToken: () => token !== null,
  users: () => request<User[]>("GET", "/users"),
  me: () => request<User>("GET", "/me"),
  async login(userId: number): Promise<User> {
    const res = await request<{ token: string; user: User }>("POST", "/auth/login", { user_id: userId });
    setToken(res.token);
    return res.user;
  },
  recipients: () => request<Recipient[]>("GET", "/recipients"),
  equipment: (forDocumentId?: number) =>
    request<Equipment[]>("GET", `/equipment${forDocumentId ? `?for_document_id=${forDocumentId}` : ""}`),
  documents: () => request<DocumentSummary[]>("GET", "/documents"),
  document: (id: number) => request<DocumentDetail>("GET", `/documents/${id}`),
  create: (input: DocumentInput) => request<DocumentDetail>("POST", "/documents", input),
  update: (id: number, input: DocumentInput) => request<DocumentDetail>("PUT", `/documents/${id}`, input),
  submit: (id: number) => request<DocumentDetail>("POST", `/documents/${id}/submit`),
  sign: (id: number, pin: string, documentHash: string) =>
    request<DocumentDetail>("POST", `/documents/${id}/sign`, { pin, document_hash: documentHash }),
  reopen: (id: number) => request<DocumentDetail>("POST", `/documents/${id}/reopen`, { confirm_invalidate: true }),
  release: (id: number) => request<DocumentDetail>("POST", `/documents/${id}/release`),
  cancel: (id: number, reason: string) => request<DocumentDetail>("POST", `/documents/${id}/cancel`, { reason }),
  resetDemo: () => request<{ ok: boolean }>("POST", "/demo/reset"),
};
