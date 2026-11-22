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

export type SettlementKind = "batches" | "statements" | "reconciliation-runs";
export interface SettlementRecord {
  id: string; customer_id: string; status: string; created_at: string; filename?: string;
  currency?: string; item_count?: number; total?: string; settled_count?: number; failed_count?: number;
  matched_count?: number; exception_count?: number; row_count?: number; replayed?: boolean;
}
export interface ExceptionEvent {
  id: string; kind: string; actor_name?: string | null; occurred_at: string; note?: string | null;
  previous_status?: string | null; next_status?: string | null;
  metadata?: { assigned_user_id?: string; assigned_name?: string; previous_assigned_user_id?: string | null };
}
export interface ExceptionRecord {
  id: string; reference: string; customer_id: string; exception_type: string; severity: string;
  status: string; source_domain: string; source_reference: string; title: string;
  description?: string; assigned_user_id: string | null; assigned_name?: string | null;
  resolution_summary?: string | null; created_at: string; updated_at: string;
  events?: ExceptionEvent[];
}
export interface ExceptionPage { items: ExceptionRecord[]; total: number; limit: number; offset: number; }
export interface ExceptionAssignee { id: string; display_name: string; }
export const api = {
  exceptions: (offset: number, query = "") => request<ExceptionPage>(`/api/v1/exceptions?offset=${offset}${query}`),
  exception: (id: string) => request<ExceptionRecord>(`/api/v1/exceptions/${id}`),
  exceptionAssignees: (id: string) => request<ExceptionAssignee[]>(`/api/v1/exceptions/${id}/assignees`),
  assignException: (id: string, assigned_user_id: string) => request<ExceptionRecord>(`/api/v1/exceptions/${id}/assign`, {method:"POST",body:JSON.stringify({assigned_user_id})}),
  transitionException: (id: string, status: string, reason = "") => request<ExceptionRecord>(`/api/v1/exceptions/${id}/transition`, {method:"POST",body:JSON.stringify({status,reason})}),
  noteException: (id: string, body: string) => request<ExceptionRecord>(`/api/v1/exceptions/${id}/notes`, {method:"POST",body:JSON.stringify({body})}),
  resolveException: (id: string, body: string) => request<ExceptionRecord>(`/api/v1/exceptions/${id}/resolve`, {method:"POST",body:JSON.stringify({body})}),
  closeException: (id: string, reason: string) => request<ExceptionRecord>(`/api/v1/exceptions/${id}/close`, {method:"POST",body:JSON.stringify({status:"closed",reason})}),
  settlementList: (kind: SettlementKind, offset: number) => request<SettlementRecord[]>(`/api/v1/settlements/${kind}?offset=${offset}`),
  settlementBatch: (id: string) => request<SettlementRecord>(`/api/v1/settlements/batches/${encodeURIComponent(id)}`),
  settlementItems: (kind: SettlementKind, id: string, offset: number) =>
    request<Record<string, unknown>[]>(`/api/v1/settlements/${kind}/${id}/items?offset=${offset}`),
  makeBatch: (customer_id: string) => request<SettlementRecord>("/api/v1/settlements/batches", {method:"POST",body:JSON.stringify({customer_id})}),
  processBatch: (id: string) => request<SettlementRecord>(`/api/v1/settlements/batches/${id}/process`, {method:"POST"}),
  importStatement: (customer: string,file: File) => request<SettlementRecord>(`/api/v1/settlements/statements/import?${new URLSearchParams({customer_id:customer,filename:file.name})}`,
    {method:"POST",headers:{"Content-Type":"text/csv"},body:file}),
  reconcile: (import_id: string) => request<SettlementRecord>("/api/v1/settlements/reconciliation-runs",{method:"POST",body:JSON.stringify({import_id})}),
  payments: (offset: number) =>
    request<Payment[]>(`/api/v1/payments?limit=25&offset=${offset}`),
  payment: (id: string) => request<Payment>(`/api/v1/payments/${id}`),
  createPayment: (body: PaymentCommand, key: string) =>
    request<Payment>("/api/v1/payments", {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify(body),
    }),
  submitPayment: (id: string) =>
    request<Payment>(`/api/v1/payments/${id}/submit`, { method: "POST" }),
  cancelPayment: (id: string) =>
    request<Payment>(`/api/v1/payments/${id}/cancel`, { method: "POST" }),
  approvals: (offset: number) => request<Approval[]>(`/api/v1/approvals?offset=${offset}`),
  approval: (id: string) => request<Approval>(`/api/v1/approvals/${id}`),
  decide: (id: string, choice: "approve"|"reject", reason: string) =>
    request<Approval>(`/api/v1/approvals/${id}/${choice}`, {method:"POST",body:JSON.stringify({reason})}),
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

  holds: (accountId: string, offset: number) =>
    request<Hold[]>(
      `/api/v1/accounts/${accountId}/holds?limit=10&offset=${offset}`,
    ),
  hold: (id: string, offset: number) =>
    request<Hold & { events: HoldEvent[] }>(
      `/api/v1/holds/${id}?limit=10&offset=${offset}`,
    ),
  createHold: (id: string, body: CreateHold, key: string) =>
    request<HoldReceipt>(`/api/v1/accounts/${id}/holds`, {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify(body),
    }),
  releaseHold: (id: string, amount: Money | null, key: string) =>
    request<HoldReceipt>(`/api/v1/holds/${id}/release`, {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ currency: "INR", amount }),
    }),
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
export interface PaymentCommand {
  source_id: string;
  beneficiary_name: string;
  destination_reference: string;
  customer_reference: string;
  amount: Money;
  currency: "INR";
}
export interface PaymentEvent {
  id: string; kind: string; actor: string | null; occurred_at: string;
  provider_reference: string | null; detail: string | null; correlation_id: string | null;
}
export interface Payment {
  settlement_journal_id?: string | null;
  id: string; customer_id: string; source_id: string; actor_id: string;
  customer_reference: string; beneficiary_name: string; destination_reference: string;
  amount: Money; currency: string; rail: "SIMULATED_INR"; status: string;
  hold_id: string; approval_id: string | null; approval_status?: string | null; provider_reference: string;
  created_at: string; updated_at: string; events?: PaymentEvent[];
}
export interface Approval {
  id:string; maker:string; maker_name:string; source_id:string; destination_id:string;
  amount:string; currency:string; status:string; required_count:number; hold_status:string;
  decisions?: {actor:string;decision:string;reason:string;decided_at:string}[];
}
export interface Account {
  customer_id?: string;
  membership_role: "owner" | "administrator" | "member" | "viewer";
  id: string;
  reference: string;
  customer_name: string;
  currency: string;
  status: string;
  ledger_balance: Money;
  held_amount: Money;
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

export interface Hold {
  id: string;
  account_id: string;
  original_amount: Money;
  remaining: Money;
  currency: string;
  status: string;
  reason: string;
  business_reference: string | null;
  expires_at: string | null;
  created_at: string;
  creator: string;
}
export interface HoldEvent {
  id: string;
  kind: string;
  currency: string;
  amount: Money;
  remaining: Money;
  occurred_at: string;
  journal_id: string | null;
}
export interface CreateHold {
  currency: "INR";
  amount: Money;
  reason: string;
  business_reference: string | null;
  expires_at: string | null;
}
interface HoldReceipt {
  hold_id: string;
  event_id: string;
  kind: string;
  remaining: Money;
  currency: string;
}
