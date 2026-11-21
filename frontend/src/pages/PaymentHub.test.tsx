import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { api, ApiError, type Account, type Payment } from "../api";
import { PaymentHub } from "./PaymentHub";

const identity = vi.hoisted(() => ({ id: "operator" }));
vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ status: "authenticated", user: { id: identity.id, permissions: [
    "payments.read", "payments.create", "payments.submit", "payments.cancel"
  ] } }),
}));

const account: Account = {
  id:"account",membership_role:"member",reference:"SYN 001",customer_name:"Synthetic",
  currency:"INR",status:"active",ledger_balance:"1000.00",held_amount:"0.00",
  available_balance:"1000.00",
};
const payment: Payment = {
  id:"payment",customer_id:"customer",source_id:"account",actor_id:"operator",
  customer_reference:"INV 2047",beneficiary_name:"Synthetic Supplier",
  destination_reference:"SIM DEST 001",amount:"125.50",currency:"INR",
  rail:"SIMULATED_INR",status:"ready_for_submission",hold_id:"hold",approval_id:null,
  provider_reference:"sim_reference",created_at:"2026-11-20T00:00:00Z",
  updated_at:"2026-11-20T00:00:00Z",events:[],
};

test("creates a real instruction and shows accepted as awaiting settlement", async () => {
  vi.spyOn(api,"payments").mockResolvedValueOnce([]).mockResolvedValue([payment]);
  vi.spyOn(api,"accounts").mockResolvedValue([account]);
  const create=vi.spyOn(api,"createPayment").mockResolvedValue(payment);
  vi.spyOn(api,"submitPayment").mockResolvedValue({...payment,status:"accepted"});
  render(<PaymentHub/>);
  fireEvent.change(await screen.findByLabelText("Beneficiary name"),
    {target:{value:"Synthetic Supplier"}});
  fireEvent.change(screen.getByLabelText("Destination reference"),
    {target:{value:"SIM DEST 001"}});
  fireEvent.change(screen.getByLabelText("Customer reference"),{target:{value:"INV 2047"}});
  fireEvent.change(screen.getByLabelText("Amount in INR"),{target:{value:"125.50"}});
  fireEvent.click(screen.getByRole("button",{name:"Create and reserve"}));
  expect(await screen.findByText("Instruction detail")).toBeTruthy();
  expect(create).toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"Submit to simulated rail"}));
  expect(await screen.findByText(/Settlement is still pending/)).toBeTruthy();
});

async function fillForm() {
  await screen.findByRole("option");
  for (const [label, value] of [
    ["Beneficiary name", payment.beneficiary_name], ["Destination reference", payment.destination_reference],
    ["Customer reference", payment.customer_reference], ["Amount in INR", payment.amount],
  ]) fireEvent.change(screen.getByLabelText(label), {target: {value}});
}

test.each([new TypeError("Connection lost"), new ApiError(503,"unavailable","Unavailable")])(
  "recovers the original request after %s, remount and identity change", async failure => {
    identity.id = "operator";
    const slot = "ledgerops:payment-create-recovery:v1:operator";
    vi.spyOn(api,"payments").mockResolvedValue([]);
    vi.spyOn(api,"accounts").mockResolvedValue([account]);
    const create = vi.spyOn(api,"createPayment").mockImplementationOnce(async (body, key) => {
      const record = JSON.parse(sessionStorage.getItem(slot)!);
      expect(record).toEqual({version:1,maker:"operator",created:expect.any(Number),state:"submitting",body,key});
      expect(Object.keys(body).sort()).toEqual(["amount","beneficiary_name","currency","customer_reference","destination_reference","source_id"]);
      throw failure;
    }).mockResolvedValueOnce(payment);
    const view = render(<PaymentHub/>);
    await fillForm();
    fireEvent.click(screen.getByRole("button",{name:"Create and reserve"}));
    await screen.findByText(failure.message);
    const record = JSON.parse(sessionStorage.getItem(slot)!);
    expect(record.state).toBe("outcome_unknown");
    view.unmount();
    identity.id = "other";
    const other = render(<PaymentHub/>);
    await screen.findByRole("option");
    expect(screen.queryByText(/submission may already/)).toBeNull();
    expect(screen.getByLabelText("Beneficiary name")).toHaveProperty("value","");
    const otherSlot = slot.replace(/operator$/, "other");
    const otherRecord = JSON.stringify({...record,maker:"other"});
    sessionStorage.setItem(otherSlot,otherRecord);
    identity.id = "operator";
    other.rerender(<PaymentHub/>);
    expect(screen.queryByLabelText("Beneficiary name")).toBeNull();
    expect(screen.queryByRole("button",{name:"Create and reserve"})).toBeNull();
    expect(create).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button",{name:"Retry original submission"}));
    await screen.findByText("Instruction detail");
    expect(create.mock.calls[1]).toEqual(create.mock.calls[0]);
    expect(sessionStorage.getItem(slot)).toBeNull();
    expect(sessionStorage.getItem(otherSlot)).toBe(otherRecord);
    sessionStorage.removeItem(otherSlot);
  }
);

test("refuses creation when session storage cannot verify the write", async () => {
  vi.spyOn(api,"payments").mockResolvedValue([]);
  vi.spyOn(api,"accounts").mockResolvedValue([account]);
  const create = vi.spyOn(api,"createPayment");
  vi.spyOn(Storage.prototype,"setItem").mockImplementation(() => {});
  render(<PaymentHub/>);
  await fillForm();
  fireEvent.click(screen.getByRole("button",{name:"Create and reserve"}));
  await screen.findByText(/Safe retry protection could not be initialized/);
  expect(create).not.toHaveBeenCalled();
});
