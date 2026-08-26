/* Darsh Financial Dashboard: vanilla JavaScript for server-driven KPIs, Chart.js visualizations, and expense CRUD. */

const categories = ['Food & Dining', 'Transport', 'Shopping', 'Bills & Utilities', 'Entertainment', 'Other'];

const categoryStyle = {
  'Food & Dining':      { icon: '♨', bg: '#DDF2E1', color: '#1F8F45' },
  'Transport':          { icon: '⌁', bg: '#EFF5EE', color: '#3A4A3E' },
  'Shopping':           { icon: '▢', bg: '#E4F4E7', color: '#2E9B52' },
  'Bills & Utilities':  { icon: 'ϟ', bg: '#FEF3C7', color: '#D97706' },
  'Entertainment':      { icon: '✦', bg: '#EDE9FE', color: '#7C3AED' },
  'Other':              { icon: '…', bg: '#F1F5F1', color: '#758078' },
};

/* Coordinated natural sage/green/neutral palette */
const chartColors = ['#1F8F45', '#2E9B52', '#52B774', '#7EC98E', '#A0B5A5', '#758078'];
const chartColorsBg = ['rgba(31,143,69,0.85)', 'rgba(46,155,82,0.85)', 'rgba(82,183,116,0.85)', 'rgba(126,201,142,0.85)', 'rgba(160,181,165,0.85)', 'rgba(117,128,120,0.85)'];

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
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => toast.classList.remove('show'), 3000);
}

/* ===== Build query string from current filters ===== */
function buildQueryString() {
  const params = new URLSearchParams();
  const period = byId('time-filter') ? byId('time-filter').value : '';
  const category = byId('category-filter') ? byId('category-filter').value : '';
  const search = byId('search-input') ? byId('search-input').value.trim() : '';
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
    if (window.lucide) {
      lucide.createIcons();
    }
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
Chart.defaults.color = '#758078';
Chart.defaults.font.family = "'DM Sans', system-ui, sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.font.weight = 500;

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
        borderColor: '#1F8F45',
        backgroundColor: 'rgba(31, 143, 69, 0.07)',
        borderWidth: 2.2,
        pointBackgroundColor: '#1F8F45',
        pointBorderColor: '#FFFFFF',
        pointBorderWidth: 2,
        pointRadius: 4.5,
        pointHoverRadius: 6.5,
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
          backgroundColor: '#172019',
          borderColor: '#E4EAE3',
          borderWidth: 1,
          titleColor: '#FFFFFF',
          bodyColor: '#DDF2E1',
          padding: 10,
          cornerRadius: 8,
          callbacks: {
            label: (ctx) => ` ${money.format(ctx.parsed.y)}`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: 'rgba(228, 234, 227, 0.6)' },
          ticks: { color: '#758078', font: { size: 10 } },
        },
        y: {
          grid: { color: 'rgba(228, 234, 227, 0.6)' },
          ticks: {
            color: '#758078',
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
        borderColor: '#FFFFFF',
        borderWidth: 2.5,
        hoverBorderWidth: 3,
        hoverOffset: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '64%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: { padding: 14, usePointStyle: true, pointStyle: 'circle', font: { size: 10, weight: 600 }, color: '#3A4A3E' },
        },
        tooltip: {
          backgroundColor: '#172019',
          borderColor: '#E4EAE3',
          borderWidth: 1,
          titleColor: '#FFFFFF',
          bodyColor: '#DDF2E1',
          padding: 10,
          cornerRadius: 8,
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
        borderWidth: 1,
        borderRadius: 8,
        hoverBackgroundColor: brColors,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#172019',
          borderColor: '#E4EAE3',
          borderWidth: 1,
          titleColor: '#FFFFFF',
          bodyColor: '#DDF2E1',
          padding: 10,
          cornerRadius: 8,
          callbacks: {
            label: (ctx) => ` ${money.format(ctx.parsed.y)}`,
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#758078', font: { size: 10 } },
        },
        y: {
          grid: { color: 'rgba(228, 234, 227, 0.6)' },
          ticks: {
            color: '#758078',
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
        <p class="truncate text-[12px] font-bold text-ink">${escapeHTML(e.description)}</p>
        <p class="mt-0.5 text-[10px] font-medium text-ink-3">${escapeHTML(e.merchant)} · ${dateLabel(e.date)}</p>
      </div>
      <span class="text-[12px] font-bold text-danger">−${money.format(e.amount)}</span>
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
      <td class="text-[11px] font-medium text-ink-3">${dateLabel(e.date)}</td>
      <td><p class="text-[12px] font-semibold text-ink">${escapeHTML(e.description)}</p></td>
      <td class="text-[11px] text-ink-3">${escapeHTML(e.merchant)}</td>
      <td><span class="cat-badge" style="background:${s.bg};color:${s.color}">${e.category}</span></td>
      <td class="money-cell text-right text-[12px] font-bold text-danger">−${preciseMoney.format(e.amount)}</td>
      <td class="text-right whitespace-nowrap">
        <button data-edit="${e.id}" class="row-action row-action-edit" aria-label="Edit" title="Edit">
          <i data-lucide="pencil" class="w-3.5 h-3.5 inline"></i>
        </button>
        <button data-delete="${e.id}" class="row-action row-action-delete" aria-label="Delete" title="Delete">
          <i data-lucide="trash-2" class="w-3.5 h-3.5 inline"></i>
        </button>
      </td>
    </tr>`;
  }).join('') : '<tr><td colspan="6" class="px-5 py-12 text-center text-[11px] font-semibold text-ink-4">No expenses match this view. Try adjusting the filters or add your first expense.</td></tr>';
}

/* ===== Modal ===== */
function toggleModal(open, editData) {
  const modal = byId('expense-modal');
  if (!modal) return;
  modal.classList.toggle('hidden', !open);
  modal.setAttribute('aria-hidden', String(!open));

  if (open) {
    if (editData) {
      byId('modal-title').textContent = 'Edit expense';
      byId('modal-submit').innerHTML = '<i data-lucide="check" class="w-3.5 h-3.5 inline"></i> Update expense';
      byId('expense-id').value = editData.id;
      byId('expense-description').value = editData.description;
      byId('expense-merchant').value = editData.merchant;
      byId('expense-amount').value = editData.amount;
      byId('expense-date').value = editData.date;
      byId('expense-category').value = editData.category;
    } else {
      byId('modal-title').textContent = 'Add an expense';
      byId('modal-submit').innerHTML = '<i data-lucide="plus" class="w-3.5 h-3.5 inline"></i> Save expense';
      byId('expense-id').value = '';
      byId('expense-form').reset();
      byId('expense-date').value = new Date().toISOString().slice(0, 10);
    }
    if (window.lucide) lucide.createIcons();
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
  if (byId('expense-date')) {
    byId('expense-date').value = new Date().toISOString().slice(0, 10);
  }

  /* Filters — all trigger a full server-side refresh */
  if (byId('category-filter')) {
    byId('category-filter').addEventListener('change', refreshDashboard);
  }
  if (byId('time-filter')) {
    byId('time-filter').addEventListener('change', refreshDashboard);
  }

  let searchDebounce;
  if (byId('search-input')) {
    byId('search-input').addEventListener('input', () => {
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(refreshDashboard, 300);
    });
  }

  if (byId('clear-search')) {
    byId('clear-search').addEventListener('click', () => {
      if (byId('search-input')) byId('search-input').value = '';
      if (byId('category-filter')) byId('category-filter').value = '';
      if (byId('time-filter')) byId('time-filter').value = '';
      refreshDashboard();
    });
  }

  /* Sort buttons */
  if (byId('sort-date')) {
    byId('sort-date').addEventListener('click', () => {
      if (sortField === 'date') sortAsc = !sortAsc; else { sortField = 'date'; sortAsc = false; }
      renderLedger();
    });
  }
  if (byId('sort-amount')) {
    byId('sort-amount').addEventListener('click', () => {
      if (sortField === 'amount') sortAsc = !sortAsc; else { sortField = 'amount'; sortAsc = false; }
      renderLedger();
    });
  }

  /* Modal triggers */
  ['add-expense-button', 'sidebar-add', 'mobile-add'].forEach(id => {
    const el = byId(id);
    if (el) el.addEventListener('click', () => toggleModal(true));
  });
  if (byId('close-modal')) byId('close-modal').addEventListener('click', () => toggleModal(false));
  if (byId('cancel-modal')) byId('cancel-modal').addEventListener('click', () => toggleModal(false));
  if (byId('expense-form')) byId('expense-form').addEventListener('submit', saveExpense);

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
  if (byId('ledger-body')) {
    byId('ledger-body').addEventListener('click', (event) => {
      const editBtn = event.target.closest('[data-edit]');
      if (editBtn) { editExpense(Number(editBtn.dataset.edit)); return; }
      const delBtn = event.target.closest('[data-delete]');
      if (delBtn) removeExpense(delBtn.dataset.delete);
    });
  }

  /* Placeholder notices */
  document.querySelectorAll('.js-placeholder').forEach(btn => {
    btn.addEventListener('click', () => notify('This view is connected to the primary overview.'));
  });

  /* Initial load */
  try {
    await refreshDashboard();
  } catch (err) {
    notify(err.message);
  }
});
