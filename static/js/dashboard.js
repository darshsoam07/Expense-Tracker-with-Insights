/* Darsh Financial Dashboard: vanilla JavaScript for server-driven KPIs, Chart.js visualizations, and expense CRUD. */

const categories = ['Food & Dining', 'Transport', 'Shopping', 'Bills & Utilities', 'Entertainment', 'Other'];

const categoryStyle = {
  'Food & Dining':      { icon: '♨', bg: 'rgba(251,146,60,.15)',  color: '#fb923c' },
  'Transport':          { icon: '⌁', bg: 'rgba(129,140,248,.15)', color: '#818cf8' },
  'Shopping':           { icon: '▢', bg: 'rgba(52,211,153,.15)',   color: '#34d399' },
  'Bills & Utilities':  { icon: 'ϟ', bg: 'rgba(250,204,21,.15)',  color: '#facc15' },
  'Entertainment':      { icon: '✦', bg: 'rgba(244,114,182,.15)', color: '#f472b6' },
  'Other':              { icon: '…', bg: 'rgba(148,163,184,.15)', color: '#94a3b8' },
};

/* Chart.js color palette */
const chartColors = ['#818cf8', '#34d399', '#fb923c', '#facc15', '#f472b6', '#94a3b8'];
const chartColorsBg = ['rgba(129,140,248,.7)', 'rgba(52,211,153,.7)', 'rgba(251,146,60,.7)', 'rgba(250,204,21,.7)', 'rgba(244,114,182,.7)', 'rgba(148,163,184,.7)'];

let expenses = [];
let sortField = 'date';
let sortAsc = false;

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 });
const preciseMoney = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2, maximumFractionDigits: 2 });

const byId = (id) => document.getElementById(id);
const escapeHTML = (t) => String(t).replace(/[&<>'"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));

/* ===== Chart instances ===== */
let lineChart = null;
let doughnutChart = null;
let barChart = null;

/* ===== Toast ===== */
function notify(message) {
  const toast = byId('toast');
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => toast.classList.remove('show'), 3000);
}

/* ===== Build query string from current filters ===== */
function buildQueryString() {
  const params = new URLSearchParams();
  const period = byId('time-filter').value;
  const category = byId('category-filter').value;
  const search = byId('search-input').value.trim();
  if (period) params.set('period', period);
  if (category) params.set('category', category);
  if (search) params.set('search', search);
  return params.toString();
}

/* ===== Fetch data from server (single source of truth) ===== */
async function fetchData() {
  const qs = buildQueryString();
  const [expRes, sumRes] = await Promise.all([
    fetch(`/api/expenses?${qs}`),
    fetch(`/api/expenses/summary?${qs}`),
  ]);
  if (!expRes.ok || !sumRes.ok) throw new Error('Could not load dashboard data.');
  expenses = await expRes.json();
  return await sumRes.json();
}

/* ===== Render everything ===== */
async function refreshDashboard() {
  try {
    const summary = await fetchData();
    renderKPIs(summary);
    renderLineChart(summary.monthly_totals);
    renderDoughnutChart(summary.category_totals);
    renderBarChart(summary.category_totals);
    renderRecent(expenses.slice(0, 5));
    renderLedger();
  } catch (err) {
    console.error(err);
    notify(err.message || 'Failed to load data.');
  }
}

/* ===== KPI Cards ===== */
function renderKPIs(s) {
  byId('kpi-total').textContent = money.format(s.total_spending);
  byId('kpi-month').textContent = money.format(s.this_month_spending);
  byId('kpi-avg').textContent = money.format(Math.round(s.average_expense));
  byId('kpi-count').textContent = s.transaction_count.toLocaleString('en-IN');
  byId('kpi-max').textContent = money.format(s.highest_expense);
  byId('kpi-top-cat').textContent = s.top_category || '—';
  byId('entry-count').textContent = `${expenses.length} ${expenses.length === 1 ? 'entry' : 'entries'}`;
  byId('average-spend').textContent = `Avg. ${money.format(Math.round(s.average_expense))}`;
}

/* ===== Chart.js Global Defaults ===== */
Chart.defaults.color = '#94a3b8';
Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.font.weight = 600;

/* ===== Line Chart ===== */
function renderLineChart(monthlyTotals) {
  const labels = Object.keys(monthlyTotals);
  const data = Object.values(monthlyTotals);
  const canvas = byId('line-chart');
  const emptyMsg = byId('line-empty');

  if (!labels.length) {
    if (lineChart) { lineChart.destroy(); lineChart = null; }
    canvas.style.display = 'none';
    emptyMsg.classList.remove('hidden');
    return;
  }
  canvas.style.display = 'block';
  emptyMsg.classList.add('hidden');

  const monthLabels = labels.map(m => {
    const [y, mo] = m.split('-');
    return new Date(y, mo - 1).toLocaleString('en-IN', { month: 'short', year: '2-digit' });
  });

  if (lineChart) { lineChart.destroy(); }
  lineChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: monthLabels,
      datasets: [{
        label: 'Monthly Spending (₹)',
        data: data,
        borderColor: '#818cf8',
        backgroundColor: 'rgba(129,140,248,.12)',
        borderWidth: 2.5,
        pointBackgroundColor: '#818cf8',
        pointBorderColor: '#1e293b',
        pointBorderWidth: 2,
        pointRadius: 5,
        pointHoverRadius: 7,
        fill: true,
        tension: 0.35,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1e293b',
          borderColor: 'rgba(148,163,184,.2)',
          borderWidth: 1,
          titleColor: '#e2e8f0',
          bodyColor: '#f1f5f9',
          padding: 12,
          callbacks: {
            label: (ctx) => ` ${money.format(ctx.parsed.y)}`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: 'rgba(148,163,184,.06)' },
          ticks: { color: '#64748b', font: { size: 10 } },
        },
        y: {
          grid: { color: 'rgba(148,163,184,.06)' },
          ticks: {
            color: '#64748b',
            font: { size: 10 },
            callback: (v) => money.format(v),
          },
        },
      },
    },
  });
}

/* ===== Doughnut Chart ===== */
function renderDoughnutChart(categoryTotals) {
  const labels = Object.keys(categoryTotals);
  const data = Object.values(categoryTotals);
  const canvas = byId('doughnut-chart');
  const emptyMsg = byId('doughnut-empty');

  if (!labels.length) {
    if (doughnutChart) { doughnutChart.destroy(); doughnutChart = null; }
    canvas.style.display = 'none';
    emptyMsg.classList.remove('hidden');
    return;
  }
  canvas.style.display = 'block';
  emptyMsg.classList.add('hidden');

  const colors = labels.map(l => {
    const idx = categories.indexOf(l);
    return idx >= 0 ? chartColorsBg[idx] : chartColorsBg[5];
  });
  const borderColors = labels.map(l => {
    const idx = categories.indexOf(l);
    return idx >= 0 ? chartColors[idx] : chartColors[5];
  });

  const total = data.reduce((a, b) => a + b, 0);

  if (doughnutChart) { doughnutChart.destroy(); }
  doughnutChart = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: colors,
        borderColor: borderColors,
        borderWidth: 2,
        hoverBorderWidth: 3,
        hoverOffset: 8,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '62%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: { padding: 16, usePointStyle: true, pointStyle: 'circle', font: { size: 10, weight: 700 } },
        },
        tooltip: {
          backgroundColor: '#1e293b',
          borderColor: 'rgba(148,163,184,.2)',
          borderWidth: 1,
          titleColor: '#e2e8f0',
          bodyColor: '#f1f5f9',
          padding: 12,
          callbacks: {
            label: (ctx) => {
              const pct = total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
              return ` ${ctx.label}: ${money.format(ctx.parsed)} (${pct}%)`;
            },
          },
        },
      },
    },
  });
}

/* ===== Bar Chart ===== */
function renderBarChart(categoryTotals) {
  const labels = Object.keys(categoryTotals);
  const data = Object.values(categoryTotals);
  const canvas = byId('bar-chart');
  const emptyMsg = byId('bar-empty');

  if (!labels.length) {
    if (barChart) { barChart.destroy(); barChart = null; }
    canvas.style.display = 'none';
    emptyMsg.classList.remove('hidden');
    return;
  }
  canvas.style.display = 'block';
  emptyMsg.classList.add('hidden');

  const bgColors = labels.map(l => {
    const idx = categories.indexOf(l);
    return idx >= 0 ? chartColorsBg[idx] : chartColorsBg[5];
  });
  const brColors = labels.map(l => {
    const idx = categories.indexOf(l);
    return idx >= 0 ? chartColors[idx] : chartColors[5];
  });

  if (barChart) { barChart.destroy(); }
  barChart = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Spending (₹)',
        data: data,
        backgroundColor: bgColors,
        borderColor: brColors,
        borderWidth: 1.5,
        borderRadius: 6,
        hoverBackgroundColor: brColors,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1e293b',
          borderColor: 'rgba(148,163,184,.2)',
          borderWidth: 1,
          titleColor: '#e2e8f0',
          bodyColor: '#f1f5f9',
          padding: 12,
          callbacks: {
            label: (ctx) => ` ${money.format(ctx.parsed.y)}`,
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#64748b', font: { size: 10 } },
        },
        y: {
          grid: { color: 'rgba(148,163,184,.06)' },
          ticks: {
            color: '#64748b',
            font: { size: 10 },
            callback: (v) => money.format(v),
          },
        },
      },
    },
  });
}

/* ===== Date label helper ===== */
function dateLabel(value) {
  return new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(`${value}T12:00:00`));
}

/* ===== Recent Transactions ===== */
function renderRecent(items) {
  const container = byId('recent-transactions');
  if (!items.length) {
    container.innerHTML = '<p class="chart-empty">No matching transactions. Add your first expense to unlock financial insights.</p>';
    return;
  }
  container.innerHTML = items.map(e => {
    const s = categoryStyle[e.category] || categoryStyle['Other'];
    return `<div class="recent-row">
      <span class="recent-icon" style="background:${s.bg};color:${s.color}">${s.icon}</span>
      <div class="min-w-0 flex-1">
        <p class="truncate text-[11px] font-bold text-text-primary">${escapeHTML(e.description)}</p>
        <p class="mt-0.5 text-[9px] font-medium text-text-muted">${escapeHTML(e.merchant)} · ${dateLabel(e.date)}</p>
      </div>
      <span class="text-[11px] font-extrabold text-danger">−${money.format(e.amount)}</span>
    </div>`;
  }).join('');
}

/* ===== Full Ledger Table ===== */
function renderLedger() {
  const sorted = [...expenses];
  sorted.sort((a, b) => {
    if (sortField === 'date') {
      const cmp = a.date.localeCompare(b.date);
      return sortAsc ? cmp : -cmp;
    }
    const cmp = a.amount - b.amount;
    return sortAsc ? cmp : -cmp;
  });

  byId('ledger-body').innerHTML = sorted.length ? sorted.map(e => {
    const s = categoryStyle[e.category] || categoryStyle['Other'];
    return `<tr>
      <td class="text-[10px] font-semibold text-text-muted">${dateLabel(e.date)}</td>
      <td><p class="text-[11px] font-bold text-text-primary">${escapeHTML(e.description)}</p></td>
      <td class="text-[10px] text-text-secondary">${escapeHTML(e.merchant)}</td>
      <td><span class="cat-badge" style="background:${s.bg};color:${s.color}">${e.category}</span></td>
      <td class="money-cell text-right text-[11px] font-extrabold text-danger">−${preciseMoney.format(e.amount)}</td>
      <td class="text-right whitespace-nowrap">
        <button data-edit="${e.id}" class="row-action row-action-edit" aria-label="Edit" title="Edit">✎</button>
        <button data-delete="${e.id}" class="row-action row-action-delete" aria-label="Delete" title="Delete">✕</button>
      </td>
    </tr>`;
  }).join('') : '<tr><td colspan="6" class="px-5 py-12 text-center text-[11px] font-semibold text-text-muted">No expenses match this view. Try adjusting the filters or add your first expense.</td></tr>';
}

/* ===== Modal ===== */
function toggleModal(open, editData) {
  const modal = byId('expense-modal');
  modal.classList.toggle('hidden', !open);
  modal.setAttribute('aria-hidden', String(!open));

  if (open) {
    if (editData) {
      byId('modal-title').textContent = 'Edit expense';
      byId('modal-submit').textContent = '✓ Update expense';
      byId('expense-id').value = editData.id;
      byId('expense-description').value = editData.description;
      byId('expense-merchant').value = editData.merchant;
      byId('expense-amount').value = editData.amount;
      byId('expense-date').value = editData.date;
      byId('expense-category').value = editData.category;
    } else {
      byId('modal-title').textContent = 'Add an expense';
      byId('modal-submit').textContent = '＋ Save expense';
      byId('expense-id').value = '';
      byId('expense-form').reset();
      byId('expense-date').value = new Date().toISOString().slice(0, 10);
    }
    byId('expense-description').focus();
  }
}

/* ===== Save / Update Expense ===== */
async function saveExpense(event) {
  event.preventDefault();
  const editId = byId('expense-id').value;
  const payload = {
    description: byId('expense-description').value,
    merchant: byId('expense-merchant').value,
    amount: Number(byId('expense-amount').value),
    category: byId('expense-category').value,
    date: byId('expense-date').value,
  };

  const url = editId ? `/api/expenses/${editId}` : '/api/expenses';
  const method = editId ? 'PUT' : 'POST';

  const response = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const result = await response.json();

  if (!response.ok) {
    notify(result.message || 'Please check the expense details.');
    return;
  }

  toggleModal(false);
  await refreshDashboard();
  notify(editId ? 'Expense updated successfully.' : 'Expense added to your dashboard.');
}

/* ===== Delete Expense ===== */
async function removeExpense(id) {
  if (!window.confirm('Remove this expense permanently?')) return;
  const response = await fetch(`/api/expenses/${id}`, { method: 'DELETE' });
  if (!response.ok) { notify('The transaction could not be removed.'); return; }
  await refreshDashboard();
  notify('Transaction removed.');
}

/* ===== Edit Expense (populate modal) ===== */
function editExpense(id) {
  const expense = expenses.find(e => e.id === id);
  if (!expense) { notify('Expense not found.'); return; }
  toggleModal(true, expense);
}

/* ===== CSV Export (client-side from current filtered data) ===== */
function exportCSV() {
  if (!expenses.length) { notify('No transactions to export.'); return; }
  const escapeCell = (v) => `"${String(v).replace(/"/g, '""')}"`;
  const rows = [
    ['Date', 'Description', 'Merchant', 'Category', 'Amount (INR)'],
    ...expenses.map(e => [e.date, e.description, e.merchant, e.category, Number(e.amount).toFixed(2)]),
  ];
  const blob = new Blob([rows.map(r => r.map(escapeCell).join(',')).join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'darsh-financial-dashboard-expenses.csv';
  link.click();
  URL.revokeObjectURL(url);
  notify('CSV file downloaded.');
}

/* ===== Excel Export (server-side) ===== */
function exportExcel() {
  notify('Generating Excel file…');
  window.location.href = '/api/expenses/export/excel';
}

/* ===== Init ===== */
document.addEventListener('DOMContentLoaded', async () => {
  byId('expense-date').value = new Date().toISOString().slice(0, 10);

  /* Filters — all trigger a full server-side refresh */
  byId('category-filter').addEventListener('change', refreshDashboard);
  byId('time-filter').addEventListener('change', refreshDashboard);

  let searchDebounce;
  byId('search-input').addEventListener('input', () => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(refreshDashboard, 300);
  });

  byId('clear-search').addEventListener('click', () => {
    byId('search-input').value = '';
    byId('category-filter').value = '';
    byId('time-filter').value = '';
    refreshDashboard();
  });

  /* Sort buttons */
  byId('sort-date').addEventListener('click', () => {
    if (sortField === 'date') sortAsc = !sortAsc; else { sortField = 'date'; sortAsc = false; }
    renderLedger();
  });
  byId('sort-amount').addEventListener('click', () => {
    if (sortField === 'amount') sortAsc = !sortAsc; else { sortField = 'amount'; sortAsc = false; }
    renderLedger();
  });

  /* Modal triggers */
  ['add-expense-button', 'sidebar-add', 'mobile-add'].forEach(id => {
    const el = byId(id);
    if (el) el.addEventListener('click', () => toggleModal(true));
  });
  byId('close-modal').addEventListener('click', () => toggleModal(false));
  byId('cancel-modal').addEventListener('click', () => toggleModal(false));
  byId('expense-form').addEventListener('submit', saveExpense);

  /* Export triggers */
  ['export-csv', 'export-csv-sidebar'].forEach(id => {
    const el = byId(id);
    if (el) el.addEventListener('click', exportCSV);
  });
  ['export-excel', 'export-excel-sidebar'].forEach(id => {
    const el = byId(id);
    if (el) el.addEventListener('click', exportExcel);
  });
  const mobileExport = byId('mobile-export');
  if (mobileExport) mobileExport.addEventListener('click', exportCSV);

  /* Table delegation for edit / delete */
  byId('ledger-body').addEventListener('click', (event) => {
    const editBtn = event.target.closest('[data-edit]');
    if (editBtn) { editExpense(Number(editBtn.dataset.edit)); return; }
    const delBtn = event.target.closest('[data-delete]');
    if (delBtn) removeExpense(delBtn.dataset.delete);
  });

  /* Initial load */
  try { await refreshDashboard(); } catch (err) { notify(err.message); }
});
