import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api, type ExceptionPage, type ExceptionRecord } from "../api";
import { ExceptionsWorkspace } from "./ExceptionsWorkspace";

const auth = vi.hoisted(() => ({ permissions: ["exceptions.read", "exceptions.manage"] as string[] }));
vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ user: { id: "operator", permissions: auth.permissions } }),
}));

const item: ExceptionRecord = {
  id: "exception", reference: "EXC-001", customer_id: "customer", exception_type: "payment_failed",
  severity: "high", status: "open", source_domain: "payment", source_reference: "payment-1",
  title: "Payment rejected", description: "The simulated rail confirmed payment rejection.",
  assigned_user_id: null, assigned_name: null, created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z", events: [],
};
const people = [
  { id: "ada", display_name: "Ada Operator" },
  { id: "bea", display_name: "Bea Operator" },
];
const queue = (items: ExceptionRecord[], total = items.length, offset = 0): ExceptionPage => ({
  items, total, limit: 25, offset,
});

function setup(record: ExceptionRecord = item, assignees = people) {
  const list = vi.spyOn(api, "exceptions").mockResolvedValue(queue([record]));
  vi.spyOn(api, "exception").mockResolvedValue(record);
  const eligible = vi.spyOn(api, "exceptionAssignees").mockResolvedValue(assignees);
  return { list, eligible };
}
async function openRecord() {
  fireEvent.click(await screen.findByRole("button", { name: /Payment rejected/ }));
}

beforeEach(() => { auth.permissions = ["exceptions.read", "exceptions.manage"]; });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

test("an operator investigates a server-backed exception and the queue refreshes", async () => {
  const { list } = setup();
  const transition = vi.spyOn(api, "transitionException").mockResolvedValue({ ...item, status: "investigating" });
  render(<ExceptionsWorkspace />);
  await openRecord();
  fireEvent.click(await screen.findByRole("button", { name: "Start investigation" }));
  await waitFor(() => expect(transition).toHaveBeenCalledWith("exception", "investigating"));
  await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  expect(list.mock.calls[0]).toEqual([0, "&limit=25"]); // offset is sent once, as an argument
  expect(await screen.findByText("Investigating", { selector: "dd" })).toBeTruthy();
});

test("Await information needs a reason that fits the 500 character limit", async () => {
  setup();
  const transition = vi.spyOn(api, "transitionException").mockResolvedValue({ ...item, status: "awaiting_information" });
  render(<ExceptionsWorkspace />);
  await openRecord();
  const await_ = await screen.findByRole("button", { name: "Await information" });
  expect((await_ as HTMLButtonElement).disabled).toBe(true);
  const box = screen.getByLabelText("Operational note or resolution summary");
  fireEvent.change(box, { target: { value: "   " } });
  expect((await_ as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(box, { target: { value: "x".repeat(501) } });
  expect((await_ as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText(/Shorten the text/)).toBeTruthy();
  fireEvent.change(box, { target: { value: "Need rail evidence" } });
  expect((await_ as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(await_);
  await waitFor(() => expect(transition).toHaveBeenCalledWith("exception", "awaiting_information", "Need rail evidence"));
});

test("an operator assigns an exception and sees the result in the detail, history and queue", async () => {
  const { list, eligible } = setup();
  const assigned: ExceptionRecord = {
    ...item, assigned_user_id: "bea", assigned_name: "Bea Operator",
    events: [{ id: "e1", kind: "assigned", occurred_at: "2026-01-01T00:00:00Z", actor_name: "Ada Operator", metadata: { assigned_name: "Bea Operator" } }],
  };
  const assign = vi.spyOn(api, "assignException").mockResolvedValue(assigned);
  render(<ExceptionsWorkspace />);
  await openRecord();
  const select = await screen.findByLabelText("Assignee");
  expect(eligible).toHaveBeenCalledWith("exception");
  const button = screen.getByRole("button", { name: "Assign" }) as HTMLButtonElement;
  expect(button.disabled).toBe(true); // nothing chosen yet
  fireEvent.change(select, { target: { value: "bea" } });
  expect(button.disabled).toBe(false);
  fireEvent.click(button);
  await waitFor(() => expect(assign).toHaveBeenCalledWith("exception", "bea"));
  expect(await screen.findByText("Assigned to Bea Operator.")).toBeTruthy();
  expect(screen.getByText("Bea Operator", { selector: "dd" })).toBeTruthy();
  expect(screen.getByText("Assigned to Bea Operator", { selector: "strong" })).toBeTruthy();
  await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
});

test("reassignment marks the current assignee and refuses a no-op selection", async () => {
  const current: ExceptionRecord = { ...item, assigned_user_id: "ada", assigned_name: "Ada Operator" };
  setup(current);
  const reassigned: ExceptionRecord = { ...current, assigned_user_id: "bea", assigned_name: "Bea Operator" };
  const assign = vi.spyOn(api, "assignException").mockResolvedValue(reassigned);
  render(<ExceptionsWorkspace />);
  await openRecord();
  const select = await screen.findByLabelText("Assignee");
  expect(screen.getByRole("option", { name: "Ada Operator (current)" })).toBeTruthy();
  const button = screen.getByRole("button", { name: "Reassign" }) as HTMLButtonElement;
  fireEvent.change(select, { target: { value: "ada" } });
  expect(button.disabled).toBe(true); // already assigned to Ada
  fireEvent.change(select, { target: { value: "bea" } });
  fireEvent.click(button);
  await waitFor(() => expect(assign).toHaveBeenCalledWith("exception", "bea"));
  expect(await screen.findByText("Reassigned to Bea Operator.")).toBeTruthy();
});

test("a rejected assignment shows the API message and does not refresh the queue", async () => {
  const { list } = setup();
  vi.spyOn(api, "assignException").mockRejectedValue(new Error("Assignee must have active workspace membership."));
  render(<ExceptionsWorkspace />);
  await openRecord();
  fireEvent.change(await screen.findByLabelText("Assignee"), { target: { value: "ada" } });
  fireEvent.click(screen.getByRole("button", { name: "Assign" }));
  expect((await screen.findByRole("alert")).textContent).toContain("active workspace membership");
  expect(list).toHaveBeenCalledTimes(1);
  expect((screen.getByRole("button", { name: "Assign" }) as HTMLButtonElement).disabled).toBe(false); // can retry
});

test("assignee discovery failure is reported and can be retried", async () => {
  setup();
  const eligible = vi.spyOn(api, "exceptionAssignees")
    .mockRejectedValueOnce(new Error("Exception unavailable."))
    .mockResolvedValueOnce(people);
  render(<ExceptionsWorkspace />);
  await openRecord();
  expect((await screen.findByRole("alert")).textContent).toContain("Exception unavailable.");
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByLabelText("Assignee")).toBeTruthy();
  expect(eligible).toHaveBeenCalledTimes(2);
});

test("an exception with no eligible assignees says so", async () => {
  setup(item, []);
  render(<ExceptionsWorkspace />);
  await openRecord();
  expect(await screen.findByText("No eligible assignees.")).toBeTruthy();
});

test("a read-only user sees the assignee but gets no assignment or lifecycle controls", async () => {
  auth.permissions = ["exceptions.read"];
  const { eligible } = setup();
  render(<ExceptionsWorkspace />);
  await openRecord();
  expect(await screen.findByText("Unassigned", { selector: "dd" })).toBeTruthy();
  expect(screen.queryByText("Assignment")).toBeNull();
  expect(screen.queryByRole("button", { name: "Start investigation" })).toBeNull();
  expect(eligible).not.toHaveBeenCalled();
});

test("a closed exception cannot be assigned", async () => {
  const closed: ExceptionRecord = { ...item, status: "closed" };
  const { eligible } = setup(closed);
  render(<ExceptionsWorkspace />);
  await openRecord();
  expect(await screen.findByText("Closed", { selector: "dd" })).toBeTruthy();
  expect(screen.queryByText("Assignment")).toBeNull();
  expect(eligible).not.toHaveBeenCalled();
});

test("filters offer the reconciliation direction and status types and send them to the API", async () => {
  const { list } = setup();
  render(<ExceptionsWorkspace />);
  await screen.findByRole("button", { name: /Payment rejected/ });
  for (const label of ["Reconciliation direction mismatch", "Reconciliation status mismatch"]) {
    expect(screen.getByRole("option", { name: label })).toBeTruthy();
  }
  fireEvent.change(screen.getByLabelText("Type"), { target: { value: "direction_mismatch" } });
  await waitFor(() => expect(list).toHaveBeenLastCalledWith(0, expect.stringContaining("exception_type=direction_mismatch")));
});

test("pagination follows the server total and steps back when a page empties", async () => {
  const list = vi.spyOn(api, "exceptions").mockImplementation(offset =>
    Promise.resolve(offset >= 50 ? queue([], 30, offset) : queue([item], 60, offset)));
  render(<ExceptionsWorkspace />);
  expect(await screen.findByText(/Page 1 of 3 · 60 results/)).toBeTruthy();
  const previous = screen.getByRole("button", { name: "Previous" }) as HTMLButtonElement;
  const next = screen.getByRole("button", { name: "Next" }) as HTMLButtonElement;
  expect(previous.disabled).toBe(true);
  fireEvent.click(next);
  await waitFor(() => expect(list).toHaveBeenLastCalledWith(25, expect.any(String)));
  expect(await screen.findByText(/Page 2 of 3/)).toBeTruthy();
  fireEvent.click(next);
  // Offset 50 now returns nothing (the queue shrank to 30): the workspace steps back to offset 25.
  await waitFor(() => expect(list).toHaveBeenLastCalledWith(25, expect.any(String)));
  expect(list.mock.calls.some(call => call[0] === 50)).toBe(true);
});
