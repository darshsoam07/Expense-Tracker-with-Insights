import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Link, useLocation } from "react-router-dom";
import {
  Activity,
  ArrowLeft,
  ArrowLeftRight,
  BookOpen,
  Building2,
  ChevronDown,
  CircleHelp,
  ClipboardCheck,
  FileClock,
  GitCompareArrows,
  LayoutDashboard,
  Menu,
  Server,
  Settings,
  ShieldCheck,
  TriangleAlert,
  Users,
  Wallet,
  X,
  type LucideIcon,
} from "lucide-react";
import { Brand, StatusBadge } from "./ui";
import type { Health } from "../model";

export const destinations: {
  slug: string;
  label: string;
  group: string;
  icon: LucideIcon;
}[] = [
  { slug: "", label: "Overview", group: "Workspace", icon: LayoutDashboard },
  { slug: "accounts", label: "Accounts", group: "Workspace", icon: Wallet },
  {
    slug: "transfers",
    label: "Payments & Transfers",
    group: "Workspace",
    icon: ArrowLeftRight,
  },
  {
    slug: "ledger",
    label: "Ledger Explorer",
    group: "Workspace",
    icon: BookOpen,
  },
  {
    slug: "approvals",
    label: "Review & Approvals",
    group: "Operations",
    icon: ClipboardCheck,
  },
  {
    slug: "exceptions",
    label: "Exceptions",
    group: "Operations",
    icon: TriangleAlert,
  },
  {
    slug: "settlements",
    label: "Settlements",
    group: "Operations",
    icon: Building2,
  },
  {
    slug: "reconciliation",
    label: "Reconciliation",
    group: "Operations",
    icon: GitCompareArrows,
  },
  { slug: "audit", label: "Audit Trail", group: "Governance", icon: FileClock },
  {
    slug: "health",
    label: "Service Health",
    group: "Platform",
    icon: Activity,
  },
  {
    slug: "infrastructure",
    label: "Infrastructure",
    group: "Platform",
    icon: Server,
  },
  {
    slug: "users",
    label: "Users & Access",
    group: "Administration",
    icon: Users,
  },
  {
    slug: "settings",
    label: "Settings",
    group: "Administration",
    icon: Settings,
  },
];
export function Sidebar({
  collapsed,
  dismiss,
  hidden,
}: {
  collapsed: boolean;
  dismiss: () => void;
  hidden: boolean;
}) {
  return (
    <aside
      id="console-sidebar"
      inert={hidden}
      className={"sidebar " + (collapsed ? "compact" : "")}
    >
      <div className="sidebar-brand">
        <Brand />
        <button
          className="mobile-close"
          aria-label="Close navigation"
          onClick={dismiss}
        >
          <X size={20} />
        </button>
      </div>
      <div className="workspace-switch">
        <span className="workspace-avatar">
          <Building2 size={18} />
        </span>
        <div>
          <strong>LedgerOps Workspace</strong>
          <small>Sandbox environment</small>
        </div>
        <ChevronDown size={15} />
      </div>
      <nav aria-label="Console navigation">
        {destinations.map((item, index) => (
          <div key={item.slug}>
            {(index === 0 || destinations[index - 1].group !== item.group) && (
              <p className="nav-group">{item.group}</p>
            )}
            <NavLink to={"/console/" + item.slug} end title={item.label}>
              <item.icon size={17} />
              <span>{item.label}</span>
            </NavLink>
          </div>
        ))}
      </nav>
      <div className="sidebar-footer">
        <ShieldCheck size={20} />
        <div>
          <strong>Synthetic funds only</strong>
          <small>Session-only demo workspace</small>
        </div>
      </div>
      <Link className="back-link" to="/">
        <ArrowLeft size={14} />
        <span>Back to website</span>
      </Link>
    </aside>
  );
}
export function Topbar({
  health,
  toggle,
}: {
  health: Health;
  toggle: () => void;
}) {
  const location = useLocation();
  const current = destinations.find(
    (item) =>
      "/console/" + item.slug === location.pathname ||
      (item.slug === "" && location.pathname === "/console"),
  );
  return (
    <header className="topbar">
      <div className="topbar-context">
        <button
          className="icon-button"
          onClick={toggle}
          aria-label="Toggle navigation"
        >
          <Menu size={19} />
        </button>
        <span>Workspace</span>
        <span className="divider">/</span>
        <strong>{current?.label ?? "Workspace"}</strong>
      </div>
      <div className="topbar-actions">
        <button
          className="health-pill"
          onClick={health.refresh}
          title="Refresh API readiness"
        >
          <StatusBadge
            tone={health.state === "Operational" ? "success" : "neutral"}
          >
            {health.state}
          </StatusBadge>
        </button>
        <a
          className="icon-button"
          href="https://github.com/darshsoam07/Expense-Tracker-with-Insights/tree/main/docs"
          aria-label="Documentation"
        >
          <CircleHelp size={18} />
        </a>
        <span className="avatar" title="Synthetic demo operator">
          DO
        </span>
      </div>
    </header>
  );
}
export function AppShell({
  children,
  health,
}: {
  children: ReactNode;
  health: Health;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobile, setMobile] = useState(false);
  const [narrow, setNarrow] = useState(window.innerWidth < 900);
  useEffect(() => {
    const resize = () => setNarrow(window.innerWidth < 900);
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);
  useEffect(() => {
    if (!mobile) return;
    const previous = document.activeElement as HTMLElement | null;
    const sidebar = document.getElementById("console-sidebar")!;
    const controls = () =>
      Array.from(sidebar.querySelectorAll<HTMLElement>("a, button"));
    controls()[1]?.focus();
    function keyboard(event: KeyboardEvent) {
      if (event.key === "Escape") setMobile(false);
      if (event.key !== "Tab") return;
      const elements = controls();
      if (event.shiftKey && document.activeElement === elements[0]) {
        event.preventDefault();
        elements.at(-1)?.focus();
      } else if (
        !event.shiftKey &&
        document.activeElement === elements.at(-1)
      ) {
        event.preventDefault();
        elements[0]?.focus();
      }
    }
    document.addEventListener("keydown", keyboard);
    return () => {
      document.removeEventListener("keydown", keyboard);
      previous?.focus();
    };
  }, [mobile]);
  const location = useLocation();
  useEffect(() => {
    setMobile(false);
  }, [location.pathname]);
  function toggle() {
    if (window.innerWidth < 900) setMobile((value) => !value);
    else setCollapsed((value) => !value);
  }
  return (
    <div
      className={
        "app-shell " +
        (collapsed ? "sidebar-collapsed " : "") +
        (mobile ? "nav-open" : "")
      }
    >
      <a href="#console-content" className="skip-link">
        Skip to content
      </a>
      {mobile && (
        <button
          className="nav-backdrop"
          onClick={() => setMobile(false)}
          aria-label="Close navigation"
        />
      )}
      <Sidebar
        collapsed={collapsed}
        dismiss={() => setMobile(false)}
        hidden={narrow && !mobile}
      />
      <div className="app-body">
        <Topbar health={health} toggle={toggle} />
        <main id="console-content" className="console-content">
          {children}
        </main>
        <footer className="console-footer">
          <span>LedgerOps · Simulated financial operations</span>
          <span>Demo data · Browser session</span>
        </footer>
      </div>
    </div>
  );
}
