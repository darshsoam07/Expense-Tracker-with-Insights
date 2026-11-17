# LedgerOps — Institutional Luxury Design System

This specification implements the approved LedgerOps 2.0 blueprint for the public website and operations console.

## Palette

| Token | Value | Purpose |
|---|---|---|
| --lo-canvas | #F3F1EB | Warm application canvas |
| --lo-forest | #111B18 | Sidebar and editorial dark sections |
| --lo-emerald | #244F43 | Primary actions and financial emphasis |
| --lo-champagne | #B89A6A | Small premium accents and chart markers |
| --lo-card | #FFFFFF | Panels and cards |
| --lo-border | #E6E1D7 | Hairline boundaries |
| --lo-text | #18211D | Main text |
| --lo-muted | #747D76 | Decorative or large secondary labels |
| --lo-secondary-text | #59645D | Accessible small supporting text |
| --lo-success | #34775C | Success semantics |
| --lo-warning | #B77B36 | Warning semantics |
| --lo-critical | #B84F4B | Critical semantics |

Use darker semantic text variants for small status text on tinted backgrounds. Champagne accents carry no essential information by themselves.

## Typography and spacing

Manrope is the interface and heading family. IBM Plex Mono is reserved for money, identifiers, timestamps and numerical metadata. Financial numerals use tabular figures.

Use an 8px primary spacing rhythm with 4px adjustments for compact metadata. Public content has a 1240px maximum width. Console gutters scale from 36px to 18px. The desktop sidebar is 248px, with a 78px collapsed rail. Cards have 14px radii, buttons 7px, dialogs 16px.

## Components and behavior

Shared components include AppShell, Sidebar, Topbar, PageHeader, MetricCard, StatusBadge, DataTable, FilterBar, TransactionRow, ActivityTimeline, ChartPanel, EmptyState, LoadingState, ErrorState and ConfirmationDialog.

Every destination has its own URL under /console. Unsupported workflows display an unavailable state with no invented records. Authentication-dependent administration explains its access requirement. The Operator and Auditor personas preview UI access only.

Transfers, journal rows and balances share one browser-memory dataset. Journal rows open a detail dialog with matching debit/credit postings, copy-key feedback and replay detection. CSV export uses the filtered journal. Settings can reset demo data after confirmation.

## Motion and accessibility

Entrance animations are limited to the public hero and dialogs. Use transform and opacity at 180–250ms with cubic-bezier(.22,1,.36,1). Hover colors use 180ms. Reduced motion disables transitions, transforms introduced by animations and smooth scrolling. No scroll fade-ins.

Tables scroll within their cards. Mobile navigation is keyboard operable, traps focus while open, restores focus on dismissal, and is inert while hidden. Controls have visible focus and accessible labels.

## Data provenance

The financial charts derive from the labelled synthetic journal. Pending approvals and exception queues display unavailable integrations. API readiness comes from the existing FastAPI endpoint and reports the latest check time. Latency, utilization and other absent metrics remain unavailable.
