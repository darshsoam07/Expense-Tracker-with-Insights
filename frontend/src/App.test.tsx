import { beforeEach, expect, test, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react";
import { App } from "./App";
import { balancesFor, initialEntries } from "./model";

const mockOperator = {
  id: "usr_op_1",
  email: "operator@ledgerops.local",
  display_name: "Alice Operator",
  roles: ["operator"],
  permissions: ["transfer:create", "account:read"],
};

function setupFetchMock(options?: {
  authenticated?: boolean;
  healthOk?: boolean;
}) {
  const { authenticated = true, healthOk = true } = options || {};

  return vi.fn().mockImplementation(async (url: string | URL | Request, init?: RequestInit) => {
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
            error: { code: "not_authenticated", message: "Not authenticated" },
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

    if (urlStr.includes("/api/v1/transfers") && method === "POST") {
      return {
        ok: false,
        status: 501,
        json: async () => ({
          error: {
            code: "not_implemented",
            message: "Transfers are not available yet.",
          },
        }),
      };
    }

    return {
      ok: true,
      status: 200,
      json: async () => ({}),
    };
  });
}

beforeEach(() => {
  window.history.replaceState({}, "", "/console");
  vi.stubGlobal("fetch", setupFetchMock({ authenticated: true, healthOk: true }));
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
    expect(screen.getByRole("heading", { name: "Console sign in" })).toBeTruthy();
  });
  expect(screen.getByLabelText(/Email address/i)).toBeTruthy();
  expect(screen.getByLabelText(/Password/i)).toBeTruthy();
  expect(screen.getByRole("button", { name: /Sign in/i })).toBeTruthy();
});

test("successful login transitions to workspace overview", async () => {
  vi.stubGlobal("fetch", setupFetchMock({ authenticated: false }));
  render(<App />);

  await waitFor(() => {
    expect(screen.getByRole("heading", { name: "Console sign in" })).toBeTruthy();
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
    expect(screen.getByRole("heading", { name: "Console sign in" })).toBeTruthy();
  });
});

test("transfer submit calls backend and handles 501 without mutating balance", async () => {
  render(<App />);

  await waitFor(() => {
    expect(screen.getByRole("button", { name: "Simulate transfer" })).toBeTruthy();
  });

  fireEvent.click(screen.getByRole("button", { name: "Simulate transfer" }));
  const dialog = screen.getByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText("Amount · USD"), {
    target: { value: "321.12" },
  });

  const submitBtn = within(dialog).getByRole("button", { name: "Post simulated transfer" });
  fireEvent.click(submitBtn);

  await waitFor(() => {
    expect(screen.getByText("Transfers are not available yet.")).toBeTruthy();
  });

  // Balance remains unmutated
  expect(screen.getByText("Equal debits and credits across 3 transfers")).toBeTruthy();
});

test("search has an empty state and settings displays authenticated operator profile", async () => {
  render(<App />);

  await waitFor(() => {
    expect(screen.getByText("Workspace overview")).toBeTruthy();
  });

  fireEvent.click(screen.getByRole("link", { name: "Payments & Transfers" }));
  fireEvent.change(screen.getByLabelText("Search transactions"), {
    target: { value: "missing-reference" },
  });
  expect(screen.getByText("No matching transactions")).toBeTruthy();

  fireEvent.click(screen.getByRole("link", { name: "Settings" }));
  await waitFor(() => {
    expect(screen.getByText("Active operator profile")).toBeTruthy();
  });
  const settingsSection = screen
    .getByRole("heading", { name: "Active operator profile" })
    .closest("section")!;
  expect(within(settingsSection).getByText("Alice Operator")).toBeTruthy();
  expect(within(settingsSection).getByText("operator@ledgerops.local")).toBeTruthy();
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
