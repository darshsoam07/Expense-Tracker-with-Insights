/**
 * Central typed API client for LedgerOps.
 *
 * Adheres to:
 * - Same-origin relative paths (/api/v1/...)
 * - Cookie-based sessions with credentials: "include"
 * - In-memory CSRF token management (never JavaScript storage)
 * - Standardized backend error response normalization
 */

export interface User {
  id: string;
  email: string;
  display_name: string;
  roles: string[];
  permissions: string[];
}

export interface AuthStateResponse {
  user: User;
  csrf_token: string;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly requestId?: string,
    public readonly details: unknown[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let memoryCsrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  memoryCsrfToken = token;
}

export function getCachedCsrfToken(): string | null {
  return memoryCsrfToken;
}

async function fetchCsrfToken(): Promise<string> {
  const res = await fetch("/api/v1/auth/csrf", {
    method: "GET",
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) {
    throw await parseApiError(res);
  }
  const data = (await res.json()) as { csrf_token: string };
  memoryCsrfToken = data.csrf_token;
  return data.csrf_token;
}

async function parseApiError(res: Response): Promise<ApiError> {
  try {
    const data = (await res.json()) as {
      error?: {
        code?: string;
        message?: string;
        request_id?: string;
        details?: unknown[];
      };
    };
    if (data?.error) {
      return new ApiError(
        res.status,
        data.error.code || "unknown_error",
        data.error.message || `Request failed with status ${res.status}`,
        data.error.request_id,
        data.error.details || [],
      );
    }
  } catch {
    /* Non-JSON response fallback */
  }
  return new ApiError(
    res.status,
    "http_error",
    `Request failed with status ${res.status}`,
  );
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});

  const isStateChanging = ["POST", "PUT", "PATCH", "DELETE"].includes(method);
  if (isStateChanging && !headers.has("X-CSRF-Token")) {
    const token = memoryCsrfToken || (await fetchCsrfToken());
    headers.set("X-CSRF-Token", token);
  }

  if (
    options.body &&
    typeof options.body === "string" &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(path, {
    ...options,
    method,
    headers,
    credentials: "include",
    cache: "no-store",
  });

  if (!res.ok) {
    throw await parseApiError(res);
  }

  if (res.status === 204) {
    return undefined as unknown as T;
  }

  return (await res.json()) as T;
}

export const api = {
  getCsrf: fetchCsrfToken,

  async getMe(): Promise<AuthStateResponse> {
    const data = await request<AuthStateResponse>("/api/v1/me");
    if (data?.csrf_token) {
      setCsrfToken(data.csrf_token);
    }
    return data;
  },

  async login(credentials: {
    email: string;
    password: string;
  }): Promise<AuthStateResponse> {
    const data = await request<AuthStateResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify(credentials),
    });
    if (data?.csrf_token) {
      setCsrfToken(data.csrf_token);
    }
    return data;
  },

  async logout(): Promise<void> {
    try {
      await request<void>("/api/v1/auth/logout", {
        method: "POST",
      });
    } finally {
      setCsrfToken(null);
    }
  },

  account: (id: string) => request<Account>(`/api/v1/accounts/${id}`),
  accounts: () => request<Account[]>("/api/v1/accounts"),
  ledger: (id: string, offset: number) =>
    request<Posting[]>(
      `/api/v1/accounts/${id}/ledger?limit=25&offset=${offset}`,
    ),
  transfers: (offset: number) =>
    request<Transfer[]>(`/api/v1/transfers?limit=25&offset=${offset}`),
  createTransfer: (payload: TransferCommand, key: string) =>
    request<Transfer>("/api/v1/transfers", {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify(payload),
    }),
};

export type Money = string;
export interface Account {
  id: string;
  reference: string;
  customer_name: string;
  currency: string;
  status: string;
  ledger_balance: Money;
  available_balance: Money;
}
export interface Posting {
  id: string;
  reference: string;
  posted_at: string;
  description: string;
  direction: string;
  amount: Money;
  currency: string;
}
export interface TransferCommand {
  source_id: string;
  destination_id: string;
  amount: Money;
  currency: "INR";
  description: string;
}
export interface Transfer {
  id: string;
  source_id: string;
  destination_id: string;
  amount: Money;
  currency: string;
  journal_reference: string;
  created_at: string;
  status: string;
}
