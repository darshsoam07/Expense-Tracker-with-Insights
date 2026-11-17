import { useEffect, useRef, useState } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { Toaster, toast } from "sonner";
import { AppShell } from "./components/AppShell";
import { ConsolePages } from "./pages/ConsolePages";
import { PublicWebsite } from "./pages/PublicWebsite";
import { initialEntries, useHealth, type Entry } from "./model";
import { EmptyState } from "./components/ui";

function Workspace() {
  const [entries, setEntries] = useState(initialEntries);
  const seen = useRef(new Set(initialEntries.map((entry) => entry.key)));
  const health = useHealth();
  const [persona, setPersona] = useState("Operator demo");
  function post(entry: Entry) {
    if (seen.current.has(entry.key)) {
      toast.info("Replay detected. Balances unchanged.");
      return;
    }
    seen.current.add(entry.key);
    setEntries((previous) => [entry, ...previous]);
    toast.success("Simulated transfer posted", {
      description: "Equal debit and credit recorded in this session.",
    });
  }
  function reset() {
    seen.current = new Set(initialEntries.map((entry) => entry.key));
    setEntries(initialEntries);
  }
  const location = useLocation();
  return (
    <AppShell health={health}>
      <ConsolePages
        key={location.pathname}
        entries={entries}
        post={post}
        reset={reset}
        health={health}
        persona={persona}
        setPersona={setPersona}
      />
    </AppShell>
  );
}
function RouteScroll() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}
export function App() {
  return (
    <BrowserRouter>
      <RouteScroll />
      <Routes>
        <Route path="/" element={<PublicWebsite />} />
        <Route path="/console" element={<Workspace />} />
        <Route path="/console/:section" element={<Workspace />} />
        <Route
          path="*"
          element={
            <EmptyState title="Page not found">
              Return to the LedgerOps homepage.
            </EmptyState>
          }
        />
      </Routes>
      <Toaster theme="light" position="bottom-right" closeButton />
    </BrowserRouter>
  );
}
