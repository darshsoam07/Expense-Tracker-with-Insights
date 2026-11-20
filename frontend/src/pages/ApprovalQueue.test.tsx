import { render, screen, fireEvent } from "@testing-library/react";
import { test, expect, vi } from "vitest";
import { api, type Approval } from "../api";
import { ApprovalQueue } from "./ApprovalQueue";

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({user:{id:"checker",permissions:["approvals.read","approvals.decide"]}})
}));

test("reviewer supplies a reason and sees the server-confirmed rejection", async () => {
  const pending: Approval = {id:"request",maker:"maker",maker_name:"Test maker",
    source_id:"A",destination_id:"B",amount:"600.00",currency:"INR",status:"pending_approval",
    required_count:2,hold_status:"active",decisions:[]};
  vi.spyOn(api,"approvals").mockResolvedValueOnce([pending]).mockResolvedValue([]);
  vi.spyOn(api,"approval").mockResolvedValue(pending);
  const decide=vi.spyOn(api,"decide").mockResolvedValue({...pending,status:"rejected",hold_status:"released"});
  render(<ApprovalQueue/>);
  fireEvent.click(await screen.findByRole("button",{name:/Test maker/}));
  const reject=await screen.findByRole("button",{name:"Reject"});
  expect((reject as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(screen.getByLabelText("Decision reason"),{target:{value:"Incorrect amount"}});
  fireEvent.click(reject);
  expect(await screen.findByText("released")).toBeTruthy();
  expect(decide).toHaveBeenCalledWith("request","reject","Incorrect amount");
  expect(await screen.findByText("No pending approvals on this page.")).toBeTruthy();
});
