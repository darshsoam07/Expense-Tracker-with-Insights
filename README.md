# 💰 Darsh Financial Dashboard

A full-featured personal finance dashboard for tracking expenses, visualizing spending habits, and exporting financial reports — built with **Flask, SQLite, Chart.js, and Tailwind CSS**. No React, no Node build pipeline, no external database. Just a clean Python backend and a premium dark-themed UI.

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)
![SQLite](https://img.shields.io/badge/Database-SQLite-07405E?logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Active-brightgreen)

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Screenshots](#screenshots)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Security](#security)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

Darsh Financial Dashboard is a self-hosted expense tracker designed for individuals who want clear visibility into their spending without handing their data to a third-party service. Every user's expenses are stored locally in SQLite, scoped strictly to their account, and visualized through interactive charts and KPI cards on a responsive, mobile-friendly dashboard.

| Capability | Implementation |
|---|---|
| User accounts | Flask sessions + Werkzeug password hashing |
| Persistent data | SQLite database at `instance/expenses.db` |
| Expense management | Full CRUD via a JSON API |
| Financial KPIs | Server-calculated totals, averages, and breakdowns |
| Interactive charts | Chart.js — line, doughnut, and bar charts |
| Filtering | Time period, category, and search (server-side) |
| CSV export | Client-side download of filtered expenses |
| Excel export | Server-generated `.xlsx` via openpyxl with professional formatting |

## Features

- 🔐 **Authentication** — Signup, login, and logout with hashed passwords
- 📝 **Expense CRUD** — Add, edit, and delete expenses with instant dashboard updates
- 📊 **6 KPI Cards** — Total spending, this month, average, transaction count, highest expense, top category
- 📈 **3 Interactive Charts** — Monthly spending trend (line), category distribution (doughnut), category comparison (bar)
- 🗓️ **Time Filtering** — All time, this month, last month, last 3/6 months, this year
- 🏷️ **Category Filtering** — Food & Dining, Transport, Shopping, Bills & Utilities, Entertainment, Other
- 🔍 **Search** — Search by description, merchant, or category
- ↕️ **Sort** — Sort the expense table by date or amount
- 📤 **CSV Export** — Download filtered expenses as CSV
- 📑 **Excel Export** — Download all expenses as a professionally formatted `.xlsx` file
- 📱 **Responsive Design** — Mobile-friendly, with a bottom navigation bar
- 🌙 **Dark Theme** — Premium slate/indigo interface with a glassmorphism aesthetic

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask |
| Database | SQLite |
| Frontend | HTML / Jinja2, Tailwind CSS (CDN), vanilla JavaScript |
| Charts | Chart.js (CDN) |
| Excel export | openpyxl |
| Auth | Werkzeug security (password hashing) |

## Screenshots

> Add screenshots or a short GIF of the dashboard here to help visitors see the UI before they clone it.

```
![Dashboard Overview](docs/screenshot-dashboard.png)
![Expense Table](docs/screenshot-expenses.png)
```

## Getting Started

### Prerequisites

- Python 3.9 or later
- `pip`

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/darsh-financial-dashboard.git
cd darsh-financial-dashboard

# 2. Create and activate a virtual environment
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the application
python app.py
```

The app starts on **`http://127.0.0.1:4949`**. Open it in your browser, create an account, and start tracking your expenses. The SQLite database is created automatically at `instance/expenses.db` on first run.

## Configuration

Set a strong secret key before deploying publicly — Flask sessions rely on it for signing cookies:

```bash
export FLASK_SECRET_KEY="your-strong-random-key"
```

| Variable | Required | Description |
|---|---|---|
| `FLASK_SECRET_KEY` | Recommended for production | Secret key used to sign session cookies. Falls back to an insecure development default if unset. |

## API Reference

All endpoints below require an authenticated session (`@login_required`) unless noted otherwise.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/expenses` | List expenses. Supports `period`, `category`, and `search` query params. |
| `POST` | `/api/expenses` | Add a new expense. |
| `PUT` | `/api/expenses/<id>` | Update an existing expense (ownership-checked). |
| `DELETE` | `/api/expenses/<id>` | Delete an expense (ownership-checked). |
| `GET` | `/api/expenses/summary` | Get KPIs and chart aggregates for the dashboard. |
| `GET` | `/api/expenses/export/excel` | Download all of the current user's expenses as a formatted `.xlsx` file. |

**Example — add an expense:**

```bash
curl -X POST http://127.0.0.1:4949/api/expenses \
  -H "Content-Type: application/json" \
  --cookie "session=<your-session-cookie>" \
  -d '{
    "description": "Groceries",
    "merchant": "Whole Foods",
    "amount": 54.32,
    "category": "Food & Dining",
    "date": "2026-09-01"
  }'
```

## Project Structure

```
Expense-Tracker-with-Insights/
├── app.py                  # Flask app: routes, auth, CRUD API, KPI/summary logic, Excel export
├── requirements.txt        # Python dependencies (Flask, openpyxl)
├── static/
│   ├── css/
│   │   └── app.css         # Custom theme and styling
│   └── js/
│       └── dashboard.js    # Dashboard interactivity, charts, filters, table logic
├── templates/
│   ├── base.html           # Shared layout, Tailwind config, fonts
│   ├── auth.html           # Signup / login page
│   └── index.html          # Main dashboard page
├── instance/
│   └── expenses.db         # SQLite database (created automatically at runtime)
├── .gitignore
└── README.md
```

## Security

- Passwords are hashed with Werkzeug (`generate_password_hash` / `check_password_hash`) — never stored in plain text
- All expense operations are scoped to the logged-in user via `session["user_id"]`
- Edit and delete operations verify ownership with `WHERE id = ? AND user_id = ?`
- Excel and CSV exports only ever include the current user's data
- All SQL queries are parameterized to prevent injection

