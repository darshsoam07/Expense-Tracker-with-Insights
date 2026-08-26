# Darsh Financial Dashboard

A full-featured personal finance dashboard built with **Flask, SQLite, Chart.js, Tailwind CSS, and vanilla JavaScript**. No React, no Node.js build pipeline, no external database — just a clean Python backend and a premium dark-themed interface.

| Capability | Implementation |
| --- | --- |
| User accounts | Flask sessions and Werkzeug password hashes |
| Persistent data | SQLite database at `instance/expenses.db` |
| Expense management | Full CRUD (Create, Read, Update, Delete) via JSON API |
| Financial KPIs | Server-calculated totals, averages, and breakdowns |
| Interactive charts | Chart.js — line, doughnut, and bar charts |
| Filtering | Time period, category, and search (server-side) |
| CSV export | Client-side download of filtered expenses |
| Excel export | Server-generated `.xlsx` via openpyxl with professional formatting |
| Dashboard UI | HTML templates, Tailwind CSS CDN, custom dark theme, vanilla JS |

## Features

- **Authentication** — Signup, login, logout with password hashing
- **Expense CRUD** — Add, edit, and delete expenses with instant dashboard updates
- **6 KPI Cards** — Total spending, this month, average, transactions, highest, top category
- **3 Interactive Charts** — Monthly spending trend (line), category distribution (doughnut), category comparison (bar)
- **Time Filtering** — All time, this month, last month, last 3/6 months, this year
- **Category Filtering** — Filter by Food & Dining, Transport, Shopping, Bills & Utilities, Entertainment, Other
- **Search** — Search by description, merchant, or category
- **Sort** — Sort the expense table by date or amount
- **CSV Export** — Download filtered expenses as CSV
- **Excel Export** — Download all expenses as a professionally formatted `.xlsx` file
- **Responsive Design** — Mobile-friendly with a bottom navigation bar
- **Dark Theme** — Premium slate/indigo glassmorphism interface

## Technology Stack

- **Backend**: Python, Flask
- **Database**: SQLite
- **Frontend**: HTML/Jinja2, Tailwind CSS (CDN), vanilla JavaScript
- **Charts**: Chart.js (CDN)
- **Excel**: openpyxl

## Run Locally

Create and activate a virtual environment, install dependencies, and start the server.

```bash
# Create virtual environment
python -m venv .venv

# Activate (Linux/macOS)
source .venv/bin/activate

# Activate (Windows)
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

Open `http://127.0.0.1:4949`, create an account, and start tracking your expenses.

## API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/expenses` | List expenses (supports `period`, `category`, `search` params) |
| `POST` | `/api/expenses` | Add a new expense |
| `PUT` | `/api/expenses/<id>` | Update an existing expense |
| `DELETE` | `/api/expenses/<id>` | Delete an expense |
| `GET` | `/api/expenses/summary` | Get KPIs and chart aggregates |
| `GET` | `/api/expenses/export/excel` | Download expenses as Excel file |

## Security

- Passwords are hashed with Werkzeug
- All expense operations are scoped to the logged-in user via `session["user_id"]`
- Edit and delete check ownership: `WHERE id = ? AND user_id = ?`
- Excel and CSV exports only include the current user's data
- Parameterized SQL queries throughout

## Configuration

Set a strong secret key before hosting publicly:

```bash
export FLASK_SECRET_KEY="your-strong-random-key"
```
