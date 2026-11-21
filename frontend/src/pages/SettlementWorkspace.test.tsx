import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { api, type SettlementRecord } from "../api";
import { SettlementWorkspace } from "./SettlementWorkspace";

vi.mock("../context/AuthContext",()=>({useAuth:()=>({user:{permissions:["ledger.read"]}})}));

test("an auditor can inspect reconciliation exceptions and their linked records", async()=>{
  const run: SettlementRecord={id:"run-1",customer_id:"customer",status:"completed",created_at:"2026-11-21",
    matched_count:0,exception_count:1};
  vi.spyOn(api,"settlementList").mockResolvedValue([run]);
  vi.spyOn(api,"settlementItems").mockResolvedValue([{id:"result",payment_id:"payment-1",
    classification:"amount_mismatch",evidence:{internal:{batch_id:"batch-1"}}}]);
  render(<SettlementWorkspace initial="reconciliation-runs"/>);
  fireEvent.click(await screen.findByRole("button",{name:/run-1/}));
  expect(await screen.findByText("amount_mismatch")).toBeTruthy();
  expect(screen.getByRole("link",{name:"View payment"}).getAttribute("href")).toContain("payment-1");
  expect(screen.getByRole("link",{name:"View settlement batch"}).getAttribute("href")).toContain("batch-1");
  expect(screen.queryByRole("button",{name:"Process batch"})).toBeNull();
});
