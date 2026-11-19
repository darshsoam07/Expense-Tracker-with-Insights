import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { api, type Account, type Hold, type User } from "../api";
import { AccountHolds } from "./AccountHolds";

const account: Account = {
  id: "a",
  membership_role: "member",
  reference: "account",
  customer_name: "Customer",
  status: "active",
  currency: "INR",
  ledger_balance: "1000.00",
  held_amount: "60.00",
  available_balance: "940.00",
};
const user: User = {
  id: "owner",
  display_name: "User",
  email: "user@example.test",
  roles: ["operator"],
  permissions: ["holds.read", "holds.release", "holds.create"],
};
const hold: Hold = {
  id: "h",
  account_id: "a",
  creator: user.id,
  currency: "INR",
  original_amount: "60.00",
  remaining: "60.00",
  status: "active",
  reason: "Order",
  business_reference: null,
  expires_at: null,
  created_at: "2026-11-20T00:00:00Z",
};

test("an ambiguous reservation keeps the decimal body and key until confirmation", async () => {
  vi.spyOn(api, "holds").mockResolvedValue([]);
  const post = vi
    .spyOn(api, "createHold")
    .mockRejectedValueOnce(new Error("Connection lost"))
    .mockResolvedValueOnce({
      kind: "created",
      hold_id: "h",
      event_id: "e",
      currency: "INR",
      remaining: "1.20",
    });
  const refresh = vi.fn();
  render(<AccountHolds account={account} user={user} refresh={refresh} />);
  await screen.findByText("No holds on this page.");
  fireEvent.click(screen.getByRole("button", { name: "Reserve funds" }));
  const dialog = within(screen.getByRole("dialog", { name: "Reserve funds" }));
  fireEvent.change(dialog.getByLabelText(/Amount/), {
    target: { value: "1.20" },
  });
  fireEvent.change(dialog.getByLabelText("Reason"), {
    target: { value: "Order" },
  });
  fireEvent.click(dialog.getByText("Confirm reservation"));
  expect((await dialog.findByRole("alert")).textContent).toBe(
    "Connection lost",
  );
  expect(refresh).not.toHaveBeenCalled();
  fireEvent.click(dialog.getByText("Confirm reservation"));
  await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
  expect(post.mock.calls[0]).toEqual(post.mock.calls[1]);
  expect(post.mock.calls[0][1].amount).toBe("1.20");
  expect(post.mock.calls[0][2]).toBeTruthy();
});

test("partial release uses the existing hold and refreshes on success", async () => {
  vi.spyOn(api, "holds").mockResolvedValue([hold]);
  const post = vi.spyOn(api, "releaseHold").mockResolvedValue({
    kind: "partially_released",
    hold_id: "h",
    event_id: "e",
    remaining: "54.75",
    currency: "INR",
  });
  const refresh = vi.fn();
  render(<AccountHolds account={account} user={user} refresh={refresh} />);
  fireEvent.click(await screen.findByRole("button", { name: "Release funds" }));
  const dialog = within(screen.getByRole("dialog"));
  fireEvent.change(dialog.getByLabelText(/Amount/), {
    target: { value: "5.25" },
  });
  fireEvent.click(dialog.getByText("Confirm release"));
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
  expect(post).toHaveBeenCalledWith(hold.id, "5.25", expect.any(String));
});

test("read-only membership can inspect lifecycle history", async () => {
  vi.spyOn(api, "holds").mockResolvedValue([hold]);
  vi.spyOn(api, "hold").mockResolvedValue({
    ...hold,
    events: [
      {
        id: "e",
        amount: "60.00",
        remaining: "60.00",
        kind: "created",
        currency: "INR",
        occurred_at: hold.created_at,
        journal_id: null,
      },
    ],
  });
  render(
    <AccountHolds
      account={{ ...account, membership_role: "viewer" }}
      user={user}
      refresh={vi.fn()}
    />,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "History for Order" }),
  );
  expect(
    await screen.findByRole("region", { name: "Hold history" }),
  ).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Reserve funds" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Release funds" })).toBeNull();
});
