export type Gender = "female" | "male" | "non_binary" | "other" | "prefer_not_to_say";

export interface User {
  id: string;
  email: string;
  name: string;
  phone: string;
  dob: string | null;
  gender: Gender | null;
  has_photo: boolean;
  photo_version: number;
  email_verified: boolean;
  created_at: string;
}

export interface DocumentItem {
  id: string;
  filename: string;
  size_bytes: number;
  created_at: string;
}

export interface ConversationItem {
  id: string;
  title: string;
  updated_at: string;
}

export interface Source {
  number: number;
  title: string;
  kind: "document" | "web";
  url: string | null;
  excerpt: string;
}

export interface ChatMessage {
  id: number | string;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  verified: boolean | null;
  created_at: string;
}

export type ChatEvent =
  | { type: "conversation"; id: string; title: string }
  | { type: "status"; text: string }
  | { type: "token"; text: string }
  | { type: "reset" }
  | { type: "done"; answer: string; sources: Source[]; verified: boolean; message_id: number }
  | { type: "error"; message: string };

export class ApiError extends Error {
  status: number;
  code: string;
  fields: Record<string, string>;
  retryAfter?: number;

  constructor(status: number, code: string, message: string, fields: Record<string, string> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

export const UNAUTHORIZED_EVENT = "crag:unauthorized";
export const UNVERIFIED_EVENT = "crag:unverified";

function toApiError(status: number, payload: unknown): ApiError {
  const detail = (payload as { detail?: unknown } | null)?.detail;
  if (detail && typeof detail === "object") {
    const d = detail as { code?: string; message?: string; fields?: Record<string, string>; retry_after?: number };
    const err = new ApiError(status, d.code ?? "error", d.message ?? "Something went wrong.", d.fields ?? {});
    err.retryAfter = d.retry_after;
    return err;
  }
  if (status === 0) return new ApiError(0, "network", "Can't reach the server. Check that CRAG is running.");
  return new ApiError(status, "error", "Something went wrong. Please try again.");
}

function signalUnauthorized(err: ApiError) {
  if (err.status === 401 && err.code === "not_signed_in") window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  if (err.status === 403 && err.code === "email_not_verified") window.dispatchEvent(new Event(UNVERIFIED_EVENT));
}

async function request<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  let response: Response;
  try {
    response = await fetch(path, {
      credentials: "same-origin",
      ...rest,
      headers: json !== undefined ? { "Content-Type": "application/json", ...headers } : headers,
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
  } catch {
    throw toApiError(0, null);
  }
  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const err = toApiError(response.status, payload);
    signalUnauthorized(err);
    throw err;
  }
  return payload as T;
}

function upload<T>(path: string, file: File, onProgress?: (fraction: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", path);
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      let payload: unknown = null;
      try {
        payload = JSON.parse(xhr.responseText);
      } catch {
        payload = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(payload as T);
      else {
        const err = toApiError(xhr.status, payload);
        signalUnauthorized(err);
        reject(err);
      }
    };
    xhr.onerror = () => reject(toApiError(0, null));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

export const api = {
  health: () => request<{ ready: boolean; error: string | null; email: "smtp" | "console" }>("/api/health"),

  checkEmail: (email: string) => request<{ registered: boolean }>("/api/auth/check-email", { method: "POST", json: { email } }),
  login: (email: string, password: string) =>
    request<User>("/api/auth/login", { method: "POST", json: { email, password } }),
  signup: (body: { name: string; email: string; phone: string; password: string }) =>
    request<User>("/api/auth/signup", { method: "POST", json: body }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  verifyEmail: (code: string) => request<User>("/api/auth/verify-email", { method: "POST", json: { code } }),
  resendVerification: () => request<{ retry_after: number }>("/api/auth/resend-verification", { method: "POST" }),
  verificationStatus: () => request<{ retry_after: number }>("/api/auth/verification-status"),
  forgotPassword: (email: string) =>
    request<{ retry_after: number }>("/api/auth/forgot-password", { method: "POST", json: { email } }),
  resetPassword: (email: string, code: string, new_password: string) =>
    request<User>("/api/auth/reset-password", { method: "POST", json: { email, code, new_password } }),

  me: () => request<User>("/api/me"),
  updateProfile: (body: Partial<Pick<User, "name" | "phone" | "dob" | "gender">>) =>
    request<User>("/api/me", { method: "PATCH", json: body }),
  uploadPhoto: (file: File) => upload<User>("/api/me/photo", file),
  deletePhoto: () => request<User>("/api/me/photo", { method: "DELETE" }),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("/api/me/password", { method: "POST", json: { current_password, new_password } }),

  listDocuments: () => request<DocumentItem[]>("/api/documents"),
  uploadDocument: (file: File, onProgress?: (fraction: number) => void) =>
    upload<DocumentItem>("/api/documents", file, onProgress),
  deleteDocument: (id: string) => request<void>(`/api/documents/${id}`, { method: "DELETE" }),

  listConversations: () => request<ConversationItem[]>("/api/conversations"),
  messages: (id: string) => request<ChatMessage[]>(`/api/conversations/${id}/messages`),
  renameConversation: (id: string, title: string) =>
    request<ConversationItem>(`/api/conversations/${id}`, { method: "PATCH", json: { title } }),
  deleteConversation: (id: string) => request<void>(`/api/conversations/${id}`, { method: "DELETE" }),
};

export async function streamChat(
  body: { question: string; conversation_id: string | null },
  onEvent: (event: ChatEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/api/chat", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw toApiError(0, null);
  }
  if (!response.ok || !response.body) {
    const err = toApiError(response.status, await response.json().catch(() => null));
    signalUnauthorized(err);
    throw err;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let newline = buffer.indexOf("\n");
    while (newline >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (line) onEvent(JSON.parse(line) as ChatEvent);
      newline = buffer.indexOf("\n");
    }
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer) as ChatEvent);
}

export function parseDate(value: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" }).format(parseDate(value));
}

export function photoUrl(user: User): string | null {
  return user.has_photo ? `/api/me/photo?v=${user.photo_version}` : null;
}
