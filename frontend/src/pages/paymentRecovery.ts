import type { PaymentCommand } from "../api";

export interface Attempt {
  version: 1;
  maker: string;
  key: string;
  body: PaymentCommand;
  created: number;
  state: "submitting" | "outcome_unknown";
}

export function validBody(body: PaymentCommand): boolean {
  return !!body && body.currency === "INR" && typeof body.source_id === "string" && !!body.source_id &&
    [body.beneficiary_name, body.destination_reference, body.customer_reference].every(
      value => typeof value === "string" && !!value.trim() && value.length <= 128
    ) && typeof body.amount === "string" && /^(0|[1-9]\d{0,15})(\.\d{1,2})?$/.test(body.amount) &&
    /[1-9]/.test(body.amount);
}

const slot = (maker: string) => "ledgerops:payment-create-recovery:v1:" + maker;

export function readAttempt(maker: string): Attempt | null {
  const raw = sessionStorage.getItem(slot(maker));
  if (raw === null) return null;
  const a = JSON.parse(raw);
  if (a?.version !== 1 || a.maker !== maker || typeof a.key !== "string" ||
      !/^[0-9a-f-]{36}$/i.test(a.key) || !Number.isFinite(a.created) ||
      !["submitting", "outcome_unknown"].includes(a.state) || !validBody(a.body) ||
      Object.keys(a.body).length !== 6) throw Error("Invalid recovery record");
  return a;
}

export function saveAttempt(a: Attempt) {
  const raw = JSON.stringify(a);
  sessionStorage.setItem(slot(a.maker), raw);
  if (sessionStorage.getItem(slot(a.maker)) !== raw) throw Error("Recovery write failed");
}

export function clearAttempt(a: Attempt) {
  if (readAttempt(a.maker)?.key === a.key) sessionStorage.removeItem(slot(a.maker));
}
