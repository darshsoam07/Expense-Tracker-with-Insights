"""Darsh Financial Dashboard: Flask + SQLite expense tracker with interactive charts and Excel export."""
import io
import os
import sqlite3
from datetime import datetime, date
from functools import wraps
from pathlib import Path

# pyrefly: ignore [missing-import]
from flask import (
 Flask, jsonify, redirect, render_template, request,
    send_file, session, url_for,
)
# pyrefly: ignore [missing-import]
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "instance" / "expenses.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "FLASK_SECRET_KEY", "change-this-secret-before-production"
)

VALID_CATEGORIES = {
    "Food & Dining", "Transport", "Shopping",
    "Bills & Utilities", "Entertainment", "Other",
}


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    """Create a SQLite connection with dictionary-like rows."""
    DATABASE.parent.mkdir(exist_ok=True)
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    """Create the schema and performance indexes on first run."""
    connection = get_db()
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            merchant TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount > 0),
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_expenses_user ON expenses(user_id);
        CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
        CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);
        """
    )
    connection.commit()
    connection.close()


init_db()


# ---------------------------------------------------------------------------
# Auth decorator
# ---------------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth"))
        return view(*args, **kwargs)
    return wrapped_view


# ---------------------------------------------------------------------------
# Date-range helper for period filtering
# ---------------------------------------------------------------------------

def _period_dates(period):
    """Return (start_date, end_date) strings for a named period, or None."""
    today = date.today()
    if period == "this_month":
        start = today.replace(day=1)
        return start.isoformat(), today.isoformat()
    if period == "last_month":
        first_this = today.replace(day=1)
        last_prev = first_this - __import__("datetime").timedelta(days=1)
        start = last_prev.replace(day=1)
        return start.isoformat(), last_prev.isoformat()
    if period == "last_3":
        month = today.month - 3
        year = today.year
        while month < 1:
            month += 12
            year -= 1
        start = date(year, month, 1)
        return start.isoformat(), today.isoformat()
    if period == "last_6":
        month = today.month - 6
        year = today.year
        while month < 1:
            month += 12
            year -= 1
        start = date(year, month, 1)
        return start.isoformat(), today.isoformat()
    if period == "this_year":
        start = today.replace(month=1, day=1)
        return start.isoformat(), today.isoformat()
    return None  # "all" or unrecognised


def _build_query(base, user_id, period=None, category=None, search=None):
    """Append WHERE clauses for user, period, category, and search.

    Returns (sql_string, params_list).
    """
    clauses = ["user_id = ?"]
    params = [user_id]

    dates = _period_dates(period)
    if dates:
        clauses.append("date >= ? AND date <= ?")
        params.extend(dates)

    if category:
        clauses.append("category = ?")
        params.append(category)

    if search:
        clauses.append(
            "(LOWER(description) LIKE ? OR LOWER(merchant) LIKE ? OR LOWER(category) LIKE ?)"
        )
        term = f"%{search.lower()}%"
        params.extend([term, term, term])

    return f"{base} WHERE {' AND '.join(clauses)}", params


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def auth():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template("auth.html")


@app.post("/signup")
def signup():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not name or not email or len(password) < 6:
        return redirect(url_for(
            "auth",
            error="Please enter a name, email, and a password of at least six characters.",
        ))

    connection = get_db()
    try:
        cursor = connection.execute(
            "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        connection.close()
        return redirect(url_for(
            "auth",
            error="That email is already registered. Please sign in instead.",
        ))

    session["user_id"] = cursor.lastrowid
    session["user_name"] = name
    connection.close()
    return redirect(url_for("dashboard"))


@app.post("/login")
def login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    connection = get_db()
    user = connection.execute(
        "SELECT id, name, password FROM users WHERE email = ?", (email,)
    ).fetchone()
    connection.close()

    if user and check_password_hash(user["password"], password):
        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        return redirect(url_for("dashboard"))
    return redirect(url_for("auth", error="Email or password was not recognised."))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("index.html", user_name=session.get("user_name", "Friend"))


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth"))


# ---------------------------------------------------------------------------
# Expense CRUD API
# ---------------------------------------------------------------------------

@app.get("/api/expenses")
@login_required
def get_expenses():
    """Return expenses filtered by optional period, category, and search."""
    period = request.args.get("period", "")
    category = request.args.get("category", "")
    search = request.args.get("search", "").strip()

    sql, params = _build_query(
        "SELECT id, description, merchant, amount, category, date FROM expenses",
        session["user_id"], period or None, category or None, search or None,
    )
    sql += " ORDER BY date DESC, id DESC"

    connection = get_db()
    expenses = connection.execute(sql, params).fetchall()
    connection.close()
    return jsonify([dict(e) for e in expenses])


@app.post("/api/expenses")
@login_required
def add_expense():
    data = request.get_json(silent=True) or {}
    description = str(data.get("description", "")).strip()
    merchant = str(data.get("merchant") or description).strip()
    category = str(data.get("category", "Other")).strip()
    date_str = str(data.get("date", "")).strip()

    try:
        amount = float(data.get("amount", 0))
        datetime.strptime(date_str, "%Y-%m-%d")
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Please provide a valid amount and date."}), 400

    if not description or not merchant or amount <= 0 or category not in VALID_CATEGORIES:
        return jsonify({"success": False, "message": "Please complete every expense field correctly."}), 400

    connection = get_db()
    cursor = connection.execute(
        "INSERT INTO expenses (user_id, description, merchant, amount, category, date) VALUES (?, ?, ?, ?, ?, ?)",
        (session["user_id"], description, merchant, amount, category, date_str),
    )
    connection.commit()
    expense = connection.execute(
        "SELECT id, description, merchant, amount, category, date FROM expenses WHERE id = ?",
        (cursor.lastrowid,),
    ).fetchone()
    connection.close()
    return jsonify({"success": True, "expense": dict(expense)}), 201


@app.put("/api/expenses/<int:expense_id>")
@login_required
def update_expense(expense_id):
    """Edit an existing expense. Ownership enforced via user_id."""
    data = request.get_json(silent=True) or {}
    description = str(data.get("description", "")).strip()
    merchant = str(data.get("merchant") or description).strip()
    category = str(data.get("category", "Other")).strip()
    date_str = str(data.get("date", "")).strip()

    try:
        amount = float(data.get("amount", 0))
        datetime.strptime(date_str, "%Y-%m-%d")
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Please provide a valid amount and date."}), 400

    if not description or not merchant or amount <= 0 or category not in VALID_CATEGORIES:
        return jsonify({"success": False, "message": "Please complete every expense field correctly."}), 400

    connection = get_db()
    cursor = connection.execute(
        """UPDATE expenses
           SET description = ?, merchant = ?, amount = ?, category = ?, date = ?
           WHERE id = ? AND user_id = ?""",
        (description, merchant, amount, category, date_str, expense_id, session["user_id"]),
    )
    connection.commit()

    if cursor.rowcount == 0:
        connection.close()
        return jsonify({"success": False, "message": "Expense not found."}), 404

    expense = connection.execute(
        "SELECT id, description, merchant, amount, category, date FROM expenses WHERE id = ?",
        (expense_id,),
    ).fetchone()
    connection.close()
    return jsonify({"success": True, "expense": dict(expense)})


@app.delete("/api/expenses/<int:expense_id>")
@login_required
def delete_expense(expense_id):
    connection = get_db()
    cursor = connection.execute(
        "DELETE FROM expenses WHERE id = ? AND user_id = ?",
        (expense_id, session["user_id"]),
    )
    connection.commit()
    connection.close()
    return jsonify({"success": True, "deleted": cursor.rowcount == 1})


# ---------------------------------------------------------------------------
# Summary / KPI API (single source of truth for all dashboard metrics)
# ---------------------------------------------------------------------------

@app.get("/api/expenses/summary")
@login_required
def expense_summary():
    """Return aggregated KPIs and chart data.

    Query params: period, category, search (same as /api/expenses).
    ``this_month_spending`` is always the current calendar month regardless
    of the selected period filter.
    """
    uid = session["user_id"]
    period = request.args.get("period", "")
    category = request.args.get("category", "")
    search = request.args.get("search", "").strip()

    connection = get_db()

    # --- Filtered aggregates (respect period/category/search) ---
    sql, params = _build_query(
        "SELECT amount FROM expenses", uid,
        period or None, category or None, search or None,
    )
    rows = connection.execute(sql, params).fetchall()
    amounts = [r["amount"] for r in rows]

    total_spending = sum(amounts)
    transaction_count = len(amounts)
    average_expense = total_spending / transaction_count if transaction_count else 0
    highest_expense = max(amounts) if amounts else 0

    # Category totals (filtered)
    cat_sql, cat_params = _build_query(
        "SELECT category, SUM(amount) AS total FROM expenses", uid,
        period or None, category or None, search or None,
    )
    cat_sql += " GROUP BY category ORDER BY total DESC"
    cat_rows = connection.execute(cat_sql, cat_params).fetchall()
    category_totals = {r["category"]: r["total"] for r in cat_rows}
    top_category = cat_rows[0]["category"] if cat_rows else None

    # Monthly totals (filtered by category/search but show all months in range)
    month_sql, month_params = _build_query(
        "SELECT SUBSTR(date, 1, 7) AS month, SUM(amount) AS total FROM expenses",
        uid, period or None, category or None, search or None,
    )
    month_sql += " GROUP BY month ORDER BY month"
    month_rows = connection.execute(month_sql, month_params).fetchall()
    monthly_totals = {r["month"]: r["total"] for r in month_rows}

    # --- This month spending: ALWAYS current calendar month, unfiltered ---
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    this_month_row = connection.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE user_id = ? AND date >= ? AND date <= ?",
        (uid, month_start, today.isoformat()),
    ).fetchone()
    this_month_spending = this_month_row["total"]

    connection.close()

    return jsonify({
        "total_spending": total_spending,
        "this_month_spending": this_month_spending,
        "average_expense": average_expense,
        "transaction_count": transaction_count,
        "highest_expense": highest_expense,
        "top_category": top_category,
        "category_totals": category_totals,
        "monthly_totals": monthly_totals,
    })


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------

@app.get("/api/expenses/export/excel")
@login_required
def export_excel():
    """Generate a professional .xlsx of the logged-in user's expenses."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        return jsonify({"success": False, "message": "openpyxl is not installed."}), 500

    connection = get_db()
    rows = connection.execute(
        "SELECT date, description, merchant, category, amount FROM expenses WHERE user_id = ? ORDER BY date DESC",
        (session["user_id"],),
    ).fetchall()
    connection.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "Expenses"

    headers = ["Date", "Description", "Merchant", "Category", "Amount (INR)"]
    header_font = Font(name="Calibri", bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        bottom=Side(style="thin", color="CBD5E1"),
    )

    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment

    for row_idx, row in enumerate(rows, 2):
        ws.cell(row=row_idx, column=1, value=row["date"])
        ws.cell(row=row_idx, column=2, value=row["description"])
        ws.cell(row=row_idx, column=3, value=row["merchant"])
        ws.cell(row=row_idx, column=4, value=row["category"])
        amount_cell = ws.cell(row=row_idx, column=5, value=row["amount"])
        amount_cell.number_format = '₹#,##0.00'
        amount_cell.alignment = Alignment(horizontal="right")

        for c in range(1, 6):
            ws.cell(row=row_idx, column=c).border = thin_border

    # Auto-size columns
    for col_idx in range(1, 6):
        max_len = len(headers[col_idx - 1])
        for row_idx in range(2, len(rows) + 2):
            val = ws.cell(row=row_idx, column=col_idx).value
            if val and len(str(val)) > max_len:
                max_len = len(str(val))
        ws.column_dimensions[get_column_letter(col_idx)].width = max_len + 4

    # Freeze header row
    ws.freeze_panes = "A2"

    # Add Excel table
    if rows:
        from openpyxl.worksheet.table import Table, TableStyleInfo
        table = Table(
            displayName="Expenses",
            ref=f"A1:E{len(rows) + 1}",
        )
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2", showFirstColumn=False,
            showLastColumn=False, showRowStripes=True, showColumnStripes=False,
        )
        ws.add_table(table)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="darsh-financial-dashboard-expenses.xlsx",
    )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=4949)
