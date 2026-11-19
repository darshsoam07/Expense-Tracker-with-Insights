import { useEffect, useState } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AppShell } from "./components/AppShell";
import { ConsolePages } from "./pages/ConsolePages";
import { PublicWebsite } from "./pages/PublicWebsite";
import { initialEntries, useHealth } from "./model";
import { EmptyState, ErrorState, LoadingState } from "./components/ui";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { LoginForm } from "./components/LoginForm";

function Workspace() {
  const [entries, setEntries] = useState(initialEntries);
  const health = useHealth();
  const { status, error, refresh } = useAuth();
  const location = useLocation();

  function reset() {
    setEntries(initialEntries);
  }

  let body;
  if (status === "loading") {
    body = <LoadingState />;
  } else if (status === "anonymous") {
    body = <LoginForm />;
  } else if (status === "error") {
    body = (
      <ErrorState title="Authentication service error" retry={refresh}>
        {error || "Unable to reach identity service."}
      </ErrorState>
    );
  } else {
    body = (
      <ConsolePages
        key={location.pathname}
        entries={entries}
        reset={reset}
        health={health}
      />
    );
  }

  return <AppShell health={health}>{body}</AppShell>;
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
      <AuthProvider>
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
      </AuthProvider>
    </BrowserRouter>
  );
}
