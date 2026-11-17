import { useEffect, useState } from "react";

export const money = (cents: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    cents / 100,
  );
const worstCase =
  import.meta.env.DEV &&
  new URLSearchParams(location.search).get("data") === "worst";
export const accountNames = worstCase
  ? [
      "International treasury operating account",
      "Cross-border settlement reserve",
    ]
  : ["Operating treasury", "Settlement reserve"];
export const accountIds = worstCase
  ? ["GB29NWBK60161331926819", "DE89370400440532013000"]
  : ["OPS-TREASURY-01", "SETTLEMENT-POOL-A"];
export interface Entry {
  id: string;
  key: string;
  amount: number;
  source: number;
  time: string;
  description: string;
}
export const initialEntries: Entry[] = [
  {
    id: "LO-2026-00483",
    key: "demo-00483",
    amount: 25000,
    source: 0,
    time: "2026-11-17T09:42:00Z",
    description: worstCase
      ? "Quarter-end international settlement reconciliation SETTLEMENT20261117INTERNATIONAL0000007429"
      : "Internal liquidity allocation",
  },
  {
    id: "LO-2026-00482",
    key: "demo-00482",
    amount: 75000,
    source: 1,
    time: "2026-11-17T08:30:00Z",
    description: "Settlement reserve adjustment",
  },
  {
    id: "LO-2026-00481",
    key: "demo-00481",
    amount: 125000,
    source: 0,
    time: "2026-11-16T16:15:00Z",
    description: "Operating treasury allocation",
  },
];
export function balancesFor(entries: Entry[]) {
  const balances = worstCase
    ? [987654321098765, 123456789012345]
    : [10000000, 2500000];
  entries.forEach((entry) => {
    balances[entry.source] -= entry.amount;
    balances[1 - entry.source] += entry.amount;
  });
  return balances;
}
export function useHealth() {
  const [health, setHealth] = useState<{
    state: string;
    checks: Record<string, string>;
    checked: string;
  }>({ state: "Checking", checks: {}, checked: "" });
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function check() {
      let state = "Unavailable";
      let checks: Record<string, string> = {};
      try {
        const response = await fetch(
          (import.meta.env.VITE_API_BASE_URL ?? "") + "/health/ready",
          {
            cache: "no-store",
            signal: AbortSignal.any([abort.signal, AbortSignal.timeout(5000)]),
          },
        );
        const body = await response.json();
        if (body.status === "ready" || body.status === "not_ready") {
          state =
            response.ok && body.status === "ready"
              ? "Operational"
              : "Not ready";
          checks = body.checks ?? {};
        }
      } catch {
        /* Connection failures are rendered as unavailable. */
      }
      if (abort.signal.aborted) return;
      setHealth({ state, checks, checked: new Date().toLocaleTimeString() });
      timer = setTimeout(check, 15000);
    }
    void check();
    return () => {
      abort.abort();
      clearTimeout(timer);
    };
  }, [refresh]);
  return {
    ...health,
    refresh: () => {
      setHealth((previous) => ({ ...previous, state: "Checking" }));
      setRefresh((value) => value + 1);
    },
  };
}
export type Health = ReturnType<typeof useHealth>;
