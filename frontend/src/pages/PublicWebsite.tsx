import { Link } from "react-router-dom";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  Database,
  Fingerprint,
  GitBranch,
  Layers,
  LockKeyhole,
  Menu,
  Network,
  Scale,
  Server,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { useState } from "react";
import { Brand, StatusBadge } from "../components/ui";
import { money } from "../model";

function DashboardPreview() {
  return (
    <div
      className="product-preview"
      aria-label="Demo operations dashboard preview"
    >
      <div className="preview-nav">
        <Layers size={18} />
        <div>
          <strong>LedgerOps</strong>
          <small>Operations console</small>
        </div>
        <span className="preview-nav-active">Overview</span>
      </div>
      <div className="preview-content">
        <div className="preview-title">
          <span>Workspace overview</span>
          <StatusBadge>Demo data</StatusBadge>
        </div>
        <div className="preview-balance">
          <div>
            <small>Total simulated balance</small>
            <strong>{money(12500000)}</strong>
          </div>
          <span className="mini-trend">
            <Scale size={16} /> Balanced journal
          </span>
        </div>
        <div className="preview-chart">
          <div className="chart-topline">
            <span>Transfer activity</span>
            <small>3 recorded transfers</small>
          </div>
          <svg
            viewBox="0 0 600 140"
            role="img"
            aria-label="Demo transfer amounts, 1250, 750 and 250 dollars"
          >
            <path
              d="M0 35H600 M0 75H600 M0 115H600"
              stroke="#E6E1D7"
              strokeDasharray="4 6"
            />
            <path
              d="M20 30 L290 65 L570 112"
              fill="none"
              stroke="#244F43"
              strokeWidth="3"
            />
            <circle cx="20" cy="30" r="5" fill="#B89A6A" />
            <circle cx="290" cy="65" r="5" fill="#B89A6A" />
            <circle cx="570" cy="112" r="5" fill="#B89A6A" />
          </svg>
        </div>
        <div className="preview-bottom">
          <span>Latest transfer</span>
          <strong className="numeric">{money(25000)}</strong>
          <StatusBadge tone="success">Recorded</StatusBadge>
        </div>
      </div>
    </div>
  );
}
export function PublicWebsite() {
  const [menu, setMenu] = useState(false);
  return (
    <div className="public-site">
      <a className="skip-link" href="#public-content">
        Skip to content
      </a>
      <header className="public-header">
        <div className="public-wrap public-nav">
          <Brand />
          <button
            className="icon-button mobile-menu"
            aria-label="Toggle website navigation"
            aria-expanded={menu}
            onClick={() => setMenu(!menu)}
          >
            <Menu />
          </button>
          <nav
            className={menu ? "website-links expanded" : "website-links"}
            aria-label="Website navigation"
          >
            {["Platform", "Operations", "Reliability", "Architecture"].map(
              (text) => (
                <a
                  key={text}
                  href={"#" + text.toLowerCase()}
                  onClick={() => setMenu(false)}
                >
                  {text}
                </a>
              ),
            )}
            <a href="https://github.com/darshsoam07/Expense-Tracker-with-Insights/tree/main/docs">
              Documentation <ArrowUpRight size={12} />
            </a>
          </nav>
          <Link to="/console" className="button primary nav-launch">
            Launch demo <ArrowUpRight size={15} />
          </Link>
        </div>
      </header>
      <main id="public-content">
        <section className="public-hero public-wrap">
          <div className="hero-copy">
            <div className="eyebrow">
              <span />
              Financial operations, considered.
            </div>
            <h1>
              Financial integrity.
              <br />
              By design.
            </h1>
            <p>
              A considered workspace for banking operations.
              <br className="desktop-break" /> Explore simulated accounts,
              balanced transfers,
              <br className="desktop-break" /> and the engineering behind every
              movement.
            </p>
            <div className="hero-actions">
              <Link className="button primary" to="/console">
                Explore the console <ArrowRight size={17} />
              </Link>
              <a className="text-link" href="#architecture">
                View architecture <ArrowDownIcon />
              </a>
            </div>
            <div className="hero-note">
              <ShieldCheck size={15} />
              <span>
                Synthetic customers. Simulated funds. Real engineering.
              </span>
            </div>
          </div>
          <div className="hero-product">
            <div className="preview-label">
              <span className="tiny-square" />
              The operations workspace <span>01 / Demo</span>
            </div>
            <DashboardPreview />
            <div className="preview-footnote">
              <span>Clarity at every level.</span>
              <Link to="/console">
                Enter workspace <ArrowUpRight size={13} />
              </Link>
            </div>
          </div>
        </section>
        <div className="technology-strip public-wrap">
          <span>Built on a deliberate foundation</span>
          <strong>FastAPI</strong>
          <strong>React</strong>
          <strong>TypeScript</strong>
          <strong>
            PostgreSQL <small>Foundation</small>
          </strong>
          <strong>Docker</strong>
        </div>
        <section id="platform" className="public-section public-wrap">
          <div className="section-intro">
            <div>
              <div className="eyebrow">A single operating perspective</div>
              <h2>
                The detail matters.
                <br />
                So does the whole.
              </h2>
            </div>
            <p>
              Financial integrity, controlled operations, and service
              reliability belong in the same conversation.
            </p>
          </div>
          <div className="capability-grid">
            {[
              {
                icon: Scale,
                title: "Banking core",
                text: "Inspect equal debits and credits in a working, session-only transfer sandbox.",
                link: "/console/ledger",
                label: "Explore the ledger",
              },
              {
                icon: Workflow,
                title: "Financial operations",
                text: "A dedicated workspace for the approval, settlement, and reconciliation roadmap.",
                link: "/console/approvals",
                label: "View operations",
              },
              {
                icon: Fingerprint,
                title: "Governance",
                text: "Clear boundaries for identity, permissions, and the future audit history.",
                link: "/console/audit",
                label: "View governance",
              },
              {
                icon: Network,
                title: "Reliability engineering",
                text: "Read service readiness from the API, with explicit unavailable states.",
                link: "/console/health",
                label: "Check service health",
              },
            ].map((card) => (
              <article key={card.title}>
                <card.icon size={25} />
                <h3>{card.title}</h3>
                <p>{card.text}</p>
                <Link to={card.link}>
                  {card.label}
                  <ArrowUpRight size={15} />
                </Link>
              </article>
            ))}
          </div>
        </section>
        <section id="operations" className="operations-section">
          <div className="public-wrap operations-layout">
            <div>
              <div className="eyebrow">Designed for operational control</div>
              <h2>
                A clear path.
                <br />
                An accountable record.
              </h2>
              <p>
                Follow the financial lifecycle from initiation to audit. The
                transfer sandbox is available today; approval and reconciliation
                workflows follow the backend roadmap.
              </p>
              <Link className="button light" to="/console/transfers">
                Try a simulated transfer <ArrowRight size={17} />
              </Link>
            </div>
            <ol className="workflow">
              {[
                "Initiate",
                "Validate",
                "Approve",
                "Post",
                "Reconcile",
                "Audit",
              ].map((step, index) => (
                <li key={step}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <strong>{step}</strong>
                  <small>
                    {index === 0 || index === 3
                      ? "Browser simulation"
                      : "Design target"}
                  </small>
                </li>
              ))}
            </ol>
          </div>
        </section>
        <section id="architecture" className="public-section public-wrap">
          <div className="section-intro">
            <div>
              <div className="eyebrow">Engineering, made legible</div>
              <h2>A foundation you can inspect.</h2>
            </div>
            <a
              className="text-link"
              href="https://github.com/darshsoam07/Expense-Tracker-with-Insights/tree/main/docs/architecture"
            >
              Read the architecture decisions <ArrowUpRight size={16} />
            </a>
          </div>
          <div className="architecture-flow">
            {[
              {
                icon: Layers,
                name: "React workspace",
                detail: "Interactive demo · available",
              },
              {
                icon: Server,
                name: "FastAPI",
                detail: "Health & request context · available",
              },
              {
                icon: Database,
                name: "PostgreSQL 17",
                detail: "PR 3 foundation · local setup",
              },
            ].map((item) => (
              <article key={item.name}>
                <item.icon size={26} />
                <h3>{item.name}</h3>
                <p>{item.detail}</p>
              </article>
            ))}
          </div>
          <div className="architecture-target">
            <GitBranch size={16} />
            <p>
              Modular monolith · Future additions include authentication,
              durable ledger posting, an outbox, and measured telemetry.
            </p>
          </div>
        </section>
        <section id="reliability" className="public-wrap reliability-section">
          <div>
            <div className="eyebrow">Trust through transparency</div>
            <h2>Reliability is a practice.</h2>
            <p>
              Explore the safeguards present in the code, alongside an explicit
              view of the work ahead.
            </p>
          </div>
          <div className="reliability-list">
            <div>
              <Check size={18} />
              <span>
                <strong>Traceable requests</strong>
                <small>Structured JSON logs and correlation IDs.</small>
              </span>
            </div>
            <div>
              <Check size={18} />
              <span>
                <strong>Explicit service readiness</strong>
                <small>Independent liveness and readiness endpoints.</small>
              </span>
            </div>
            <div>
              <LockKeyhole size={18} />
              <span>
                <strong>A documented security roadmap</strong>
                <small>
                  Sessions, CSRF, RBAC and audit enforcement are planned.
                </small>
              </span>
            </div>
          </div>
        </section>
        <section className="public-wrap final-cta">
          <div className="eyebrow">Step inside the sandbox</div>
          <h2>See the whole picture.</h2>
          <Link className="button primary" to="/console">
            Explore the console <ArrowRight size={17} />
          </Link>
        </section>
      </main>
      <footer className="public-footer public-wrap">
        <div>
          <Brand />
          <p>
            A simulated financial operations platform.
            <br />
            Synthetic customers and funds only. No real banking rails or
            regulatory certification.
          </p>
        </div>
        <div>
          <a href="https://github.com/darshsoam07/Expense-Tracker-with-Insights">
            Repository <ArrowUpRight size={14} />
          </a>
          <a href="https://github.com/darshsoam07/Expense-Tracker-with-Insights/tree/main/docs">
            Documentation
          </a>
          <Link to="/console">Demo workspace</Link>
          <small>LedgerOps · 2026</small>
        </div>
      </footer>
    </div>
  );
}
function ArrowDownIcon() {
  return <ArrowRight size={15} className="arrow-down" />;
}
