import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { api, type Account, type Payment } from "../api";
import { PaymentHub } from "./PaymentHub";

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ user: { permissions: [
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
