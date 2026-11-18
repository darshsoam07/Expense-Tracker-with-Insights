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

beforeEach(() => {
  window.history.replaceState({}, "", "/console");
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ready", checks: { database: "ok" } }),
    }),
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
test("transfer, navigation and replay retain one consistent session journal", async () => {
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Simulate transfer" }));
  const dialog = screen.getByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText("Amount · USD"), {
    target: { value: "321.12" },
  });
  fireEvent.submit(
    within(dialog)
      .getByRole("button", { name: "Post simulated transfer" })
      .closest("form")!,
  );
  expect(
    screen.getByText("Equal debits and credits across 4 transfers"),
  ).toBeTruthy();
  fireEvent.click(screen.getByRole("link", { name: "Payments & Transfers" }));
  expect(screen.getAllByText("$321.12").length).toBeGreaterThan(0);
  fireEvent.click(
    screen.getAllByRole("button", { name: /Internal liquidity allocation/ })[0],
  );
  fireEvent.click(screen.getByRole("button", { name: "Replay request" }));
  await waitFor(() =>
    expect(
      screen.getByText("Replay detected. Balances unchanged."),
    ).toBeTruthy(),
  );
});
test("search has an empty state and auditor preview disables transfer controls", async () => {
  render(<App />);
  fireEvent.click(screen.getByRole("link", { name: "Payments & Transfers" }));
  fireEvent.change(screen.getByLabelText("Search transactions"), {
    target: { value: "missing-reference" },
  });
  expect(screen.getByText("No matching transactions")).toBeTruthy();
  fireEvent.click(screen.getByRole("link", { name: "Settings" }));
  fireEvent.change(screen.getByLabelText("Persona"), {
    target: { value: "Auditor demo" },
  });
  fireEvent.click(screen.getByRole("link", { name: "Payments & Transfers" }));
  expect(
    (
      screen.getByRole("button", {
        name: "Simulate transfer",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
});
test("unavailable health is rendered with retry instead of invented metrics", async () => {
  window.history.replaceState({}, "", "/console/health");
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  render(<App />);
  await waitFor(() =>
    expect(screen.getByText("Service unavailable")).toBeTruthy(),
  );
  expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
});
