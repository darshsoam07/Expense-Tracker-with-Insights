import { beforeEach, expect, test, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react";
import { App } from "./App";
import { api } from "./api";
import workspaceStyles from "./index.css?raw";
import { balancesFor, initialEntries } from "./model";

const mockOperator = {
  id: "usr_op_1",
  email: "operator@ledgerops.local",
  display_name: "Alice Operator",
  roles: ["operator"],
  permissions: ["transfers.create", "accounts.read"],
};

function setupFetchMock(options?: {
  authenticated?: boolean;
  healthOk?: boolean;
}) {
  const { authenticated = true, healthOk = true } = options || {};

  return vi
    .fn()
    .mockImplementation(
      async (url: string | URL | Request, init?: RequestInit) => {
        const urlStr = typeof url === "string" ? url : url.toString();
        const method = init?.method?.toUpperCase() || "GET";

        if (urlStr.includes("/health/ready")) {
          if (!healthOk) {
            return {
              ok: false,
              status: 503,
              json: async () => ({ status: "unavailable" }),
            };
          }
          return {
            ok: true,
            status: 200,
            json: async () => ({ status: "ready", checks: { database: "ok" } }),
          };
        }

        if (urlStr.includes("/api/v1/auth/csrf")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ csrf_token: "test-csrf-token-123" }),
          };
        }

        if (urlStr.includes("/api/v1/me")) {
          if (!authenticated) {
            return {
              ok: false,
              status: 401,
              json: async () => ({
                error: {
                  code: "not_authenticated",
                  message: "Not authenticated",
                },
              }),
            };
          }
          return {
            ok: true,
            status: 200,
            json: async () => ({
              user: mockOperator,
              csrf_token: "test-csrf-token-123",
            }),
          };
        }

        if (urlStr.includes("/api/v1/auth/login") && method === "POST") {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              user: mockOperator,
              csrf_token: "test-csrf-token-123",
            }),
          };
        }

        if (urlStr.includes("/api/v1/auth/logout") && method === "POST") {
          return {
            ok: true,
            status: 204,
          };
        }

        if (urlStr.includes("/api/v1/accounts"))
          return {
            ok: true,
            json: async () =>
              ["First", "Second"].map((id) => ({
                id,
                reference: id,
                status: "active",
                currency: "INR",
                customer_name: id,
                ledger_balance: "5.00",
                available_balance: "5.00",
              })),
          };
        if (urlStr.includes("/api/v1/transfers"))
          return {
            ok: true,
            json: async () =>
              method === "POST" ? { journal_reference: "J-123" } : [],
          };

        return {
          ok: true,
          status: 200,
          json: async () => ({}),
        };
      },
    );
}

beforeEach(() => {
  window.history.replaceState({}, "", "/console");
  vi.stubGlobal(
    "fetch",
    setupFetchMock({ authenticated: true, healthOk: true }),
  );
});

test("balanced postings preserve combined funds in both directions", () => {
  const opening = balancesFor(initialEntries);
  const updated = balancesFor([
    ...initialEntries,
    { ...initialEntries[0], amount: 999, source: 1 },
  ]);
  expect(updated[0]).toBe(opening[0] + 999);
  expect(updated[1]).toBe(opening[1] - 999);
  expect(updated[0] + updated[1]).toBe(12500000);
});

test("anonymous state renders console sign-in form", async () => {
  vi.stubGlobal("fetch", setupFetchMock({ authenticated: false }));
  render(<App />);

  await waitFor(() => {
    expect(
      screen.getByRole("heading", { name: "Console sign in" }),
    ).toBeTruthy();
  });
  expect(screen.getByLabelText(/Email address/i)).toBeTruthy();
  expect(screen.getByLabelText(/Password/i)).toBeTruthy();
  expect(screen.getByRole("button", { name: /Sign in/i })).toBeTruthy();
});

test("successful login transitions to workspace overview", async () => {
  vi.stubGlobal("fetch", setupFetchMock({ authenticated: false }));
  render(<App />);

  await waitFor(() => {
    expect(
      screen.getByRole("heading", { name: "Console sign in" }),
    ).toBeTruthy();
  });

  fireEvent.change(screen.getByLabelText(/Email address/i), {
    target: { value: "operator@ledgerops.local" },
  });
  fireEvent.change(screen.getByLabelText(/Password/i), {
    target: { value: "secure-password-123" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Sign in/i }));

  await waitFor(() => {
    expect(screen.getByText("Workspace overview")).toBeTruthy();
  });
  expect(screen.getByText("AO")).toBeTruthy(); // Initials for Alice Operator
});

test("logout clears session and returns to login form", async () => {
  render(<App />);

  await waitFor(() => {
    expect(screen.getByText("Workspace overview")).toBeTruthy();
  });

  const signOutBtn = screen.getByRole("button", { name: "Sign out" });
  fireEvent.click(signOutBtn);

  await waitFor(() => {
    expect(
      screen.getByRole("heading", { name: "Console sign in" }),
    ).toBeTruthy();
  });
});

test("ambiguous transfer retry preserves decimal body, CSRF and idempotency key", async () => {
  window.history.replaceState({}, "", "/console/transfers");
  render(<App />);
  fireEvent.click(
    await screen.findByRole("button", { name: "New internal transfer" }),
  );
  const dialog = within(screen.getByRole("dialog"));
  fireEvent.change(dialog.getByLabelText("Source account"), {
    target: { value: "First" },
  });
  fireEvent.change(dialog.getByLabelText("Destination account"), {
    target: { value: "Second" },
  });
  fireEvent.change(dialog.getByLabelText(/Amount.*INR/), {
    target: { value: "1.20" },
  });
  vi.mocked(fetch).mockRejectedValueOnce(new TypeError("Connection lost"));
  fireEvent.click(dialog.getByRole("button", { name: "Post internal transfer" }));
  expect((await dialog.findByRole("alert")).textContent).toBe("Connection lost");
  expect((dialog.getByLabelText(/Amount.*INR/) as HTMLInputElement).value).toBe("1.20");
  fireEvent.click(
    dialog.getByRole("button", { name: "Post internal transfer" }),
  );
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  const requests = vi
    .mocked(fetch)
    .mock.calls.filter(
      ([path, options]) =>
        path === "/api/v1/transfers" && options?.method === "POST",
    );
  expect(requests).toHaveLength(2);
  const [call, retry] = requests;
  expect(retry[1]?.body).toBe(call[1]?.body);
  expect(new Headers(retry[1]?.headers).get("Idempotency-Key")).toBe(
    new Headers(call[1]?.headers).get("Idempotency-Key"),
  );
  expect(JSON.parse(String(call?.[1]?.body)).amount).toBe("1.20");
  const headers = new Headers(call?.[1]?.headers);
  expect(headers.get("Idempotency-Key")).toBeTruthy();
  expect(headers.get("X-CSRF-Token")).toBe("test-csrf-token-123");
});

test("transfer history has an empty state and settings displays operator profile", async () => {
  render(<App />);
  fireEvent.click(
    await screen.findByRole("link", { name: "Internal Transfers" }),
  );
  expect(
    await screen.findByText("No posted transfers on this page."),
  ).toBeTruthy();
  fireEvent.click(screen.getByRole("link", { name: "Settings" }));
  await waitFor(() => {
    expect(screen.getByText("Active operator profile")).toBeTruthy();
  });
  const settingsSection = screen
    .getByRole("heading", { name: "Active operator profile" })
    .closest("section")!;
  expect(within(settingsSection).getByText("Alice Operator")).toBeTruthy();
  expect(
    within(settingsSection).getByText("operator@ledgerops.local"),
  ).toBeTruthy();
  expect(within(settingsSection).getByText("operator")).toBeTruthy();
});

test("unavailable health is rendered with retry button", async () => {
  window.history.replaceState({}, "", "/console/health");
  vi.stubGlobal(
    "fetch",
    setupFetchMock({ authenticated: true, healthOk: false }),
  );
  render(<App />);

  await waitFor(() => {
    expect(screen.getByText("Service unavailable")).toBeTruthy();
  });
  expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
});

test("a pending transfer survives Escape and announces rejection inside the dialog", async () => {
  window.history.replaceState({}, "", "/console/transfers");
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "New internal transfer" }));
  const element = screen.getByRole("dialog");
  const dialog = within(element);
  fireEvent.change(dialog.getByLabelText("Source account"), { target: { value: "First" } });
  fireEvent.change(dialog.getByLabelText("Destination account"), { target: { value: "Second" } });
  fireEvent.change(dialog.getByLabelText(/Amount.*INR/), { target: { value: "9.00" } });
  let finish!: (value: Response) => void;
  vi.mocked(fetch).mockReturnValueOnce(new Promise<Response>((resolve) => { finish = resolve; }));
  fireEvent.click(dialog.getByRole("button", { name: "Post internal transfer" }));
  await dialog.findByText(/Posting/);
  const cancel = new Event("cancel", { bubbles: false, cancelable: true });
  fireEvent(element, cancel);
  expect(cancel.defaultPrevented).toBe(true);
  expect(screen.getByRole("dialog")).toBe(element);
  finish(new Response(JSON.stringify({ error: { code: "insufficient_funds", message: "Insufficient funds" } }), {status: 409}));
  expect((await dialog.findByRole("alert")).textContent).toBe("Insufficient funds");
  expect(dialog.getByRole("button", { name: "Post internal transfer" })).toBeTruthy();
});

test("ledger preserves long narration and displays decimal text in financial typography", async () => {
  const style = document.createElement("style");
  // JSDOM cannot resolve Vite's stylesheet imports; these component rules are local.
  style.textContent = workspaceStyles.replace(/^@import.*$/gm, "");
  document.head.append(style);
  const description = "A".repeat(255);
  const ledger = vi.spyOn(api, "ledger").mockResolvedValue([{
    id: "posting", reference: "journal", posted_at: "2026-11-19T00:00:00Z",
    description, direction: "debit", currency: "INR", amount: "1.20",
  }]);
  try {
    window.history.replaceState({}, "", "/console/ledger");
    render(<App />);
    const amount = await screen.findByText("INR 1.20");
    expect(getComputedStyle(amount).fontVariantNumeric).toBe("tabular-nums");
    expect(getComputedStyle(amount.closest("section")!).overflowWrap).toBe("anywhere");
    expect(amount.closest("article")?.textContent).toContain(description);
  } finally {
    style.remove();
    ledger.mockRestore();
  }
});
