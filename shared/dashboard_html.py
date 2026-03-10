"""Vulcan Dashboard — Inline HTML template for monitoring."""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Vulcan — Monitor</title>
<style>
  :root { --bg: #0a0e17; --surface: #111827; --border: #1e293b; --text: #e2e8f0; --muted: #64748b; --accent: #3b82f6; --green: #22c55e; --red: #ef4444; --yellow: #eab308; --orange: #f97316; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'SF Mono', 'Fira Code', monospace; background: var(--bg); color: var(--text); font-size: 13px; }
  .header { background: linear-gradient(135deg, #111827, #1e293b); padding: 1rem 1.5rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
  .header h1 { font-size: 1.1rem; font-weight: 600; }
  .header h1 span { color: var(--accent); }
  .header .meta { color: var(--muted); font-size: 0.75rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.75rem; padding: 1rem 1.5rem; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; }
  .card .label { color: var(--muted); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.25rem; }
  .card .value { font-size: 1.5rem; font-weight: 700; }
  .card .value.green { color: var(--green); }
  .card .value.red { color: var(--red); }
  .card .value.yellow { color: var(--yellow); }
  .modules { padding: 0 1.5rem; margin-bottom: 1rem; }
  .modules h2 { font-size: 0.85rem; margin-bottom: 0.5rem; color: var(--muted); }
  .mod-grid { display: flex; flex-wrap: wrap; gap: 0.4rem; }
  .mod-chip { padding: 0.25rem 0.6rem; border-radius: 4px; font-size: 0.7rem; border: 1px solid var(--border); }
  .mod-chip.ok { background: #052e16; border-color: #166534; color: var(--green); }
  .mod-chip.fail { background: #450a0a; border-color: #991b1b; color: var(--red); }
  .toolbar { padding: 0.5rem 1.5rem; display: flex; gap: 0.5rem; align-items: center; }
  .toolbar input { background: var(--surface); border: 1px solid var(--border); border-radius: 4px; padding: 0.4rem 0.75rem; color: var(--text); font-family: inherit; font-size: 0.8rem; width: 300px; }
  .toolbar button { background: var(--accent); color: #fff; border: none; border-radius: 4px; padding: 0.4rem 0.75rem; cursor: pointer; font-family: inherit; font-size: 0.75rem; }
  .toolbar button:hover { opacity: 0.85; }
  .toolbar .auto { margin-left: auto; display: flex; align-items: center; gap: 0.4rem; color: var(--muted); font-size: 0.75rem; }
  .table-wrap { padding: 0 1.5rem 2rem; overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 0.5rem 0.75rem; color: var(--muted); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--bg); }
  td { padding: 0.4rem 0.75rem; border-bottom: 1px solid var(--border); font-size: 0.78rem; white-space: nowrap; }
  tr:hover td { background: rgba(59,130,246,0.05); }
  .status { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 3px; font-size: 0.7rem; font-weight: 600; }
  .s2xx { background: #052e16; color: var(--green); }
  .s3xx { background: #422006; color: var(--orange); }
  .s4xx { background: #450a0a; color: var(--red); }
  .s5xx { background: #450a0a; color: var(--red); }
  .dur { color: var(--muted); }
  .dur.slow { color: var(--yellow); }
  .dur.very-slow { color: var(--red); }
  .path { max-width: 400px; overflow: hidden; text-overflow: ellipsis; }
  .query { color: var(--muted); max-width: 300px; overflow: hidden; text-overflow: ellipsis; }
  .module-tag { color: var(--accent); font-weight: 600; }
  .empty { text-align: center; padding: 3rem; color: var(--muted); }
  .pulse { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--green); animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
</style>
</head>
<body>

<div class="header">
  <h1><span>VULCAN</span> Monitor</h1>
  <div class="meta">
    <span class="pulse"></span>
    <span id="clock"></span>
  </div>
</div>

<div class="grid" id="stats-grid">
  <div class="card"><div class="label">Total Requests</div><div class="value" id="stat-total">-</div></div>
  <div class="card"><div class="label">Errores (4xx/5xx)</div><div class="value red" id="stat-errors">-</div></div>
  <div class="card"><div class="label">Vehicle Searches</div><div class="value yellow" id="stat-vehicle">-</div></div>
  <div class="card"><div class="label">OSINT Queries</div><div class="value green" id="stat-osint">-</div></div>
</div>

<div class="modules">
  <h2>Modulos</h2>
  <div class="mod-grid" id="mod-grid"></div>
</div>

<div class="toolbar">
  <input type="text" id="search" placeholder="Filtrar por ruta, query o modulo..." />
  <button onclick="doSearch()">Buscar</button>
  <button onclick="clearSearch()">Limpiar</button>
  <div class="auto">
    <input type="checkbox" id="autoRefresh" checked>
    <label for="autoRefresh">Auto-refresh 5s</label>
  </div>
</div>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>#</th><th>Timestamp</th><th>Modulo</th><th>Metodo</th><th>Ruta</th><th>Query</th><th>Status</th><th>Duracion</th><th>IP</th><th>Error</th>
      </tr>
    </thead>
    <tbody id="log-body">
      <tr><td colspan="10" class="empty">Cargando...</td></tr>
    </tbody>
  </table>
</div>

<script>
let refreshTimer;

function statusClass(code) {
  if (code < 300) return 's2xx';
  if (code < 400) return 's3xx';
  if (code < 500) return 's4xx';
  return 's5xx';
}

function durClass(ms) {
  if (ms > 10000) return 'dur very-slow';
  if (ms > 3000) return 'dur slow';
  return 'dur';
}

function renderRow(e) {
  return `<tr>
    <td>${e.id}</td>
    <td>${e.timestamp?.substring(11, 19) || '-'}</td>
    <td class="module-tag">${e.module || '-'}</td>
    <td>${e.method}</td>
    <td class="path" title="${e.path}">${e.path}</td>
    <td class="query" title="${e.query || ''}">${e.query || '-'}</td>
    <td><span class="status ${statusClass(e.status_code)}">${e.status_code}</span></td>
    <td class="${durClass(e.duration_ms)}">${e.duration_ms.toFixed(0)}ms</td>
    <td>${e.client_ip || '-'}</td>
    <td style="color:var(--red);max-width:200px;overflow:hidden;text-overflow:ellipsis" title="${e.error||''}">${e.error || '-'}</td>
  </tr>`;
}

async function fetchData(query) {
  try {
    const url = query ? `/api/activity/search?q=${encodeURIComponent(query)}&limit=100` : '/api/activity/recent?limit=100';
    const [actRes, statsRes, healthRes] = await Promise.all([
      fetch(url),
      fetch('/api/activity/stats'),
      fetch('/health'),
    ]);
    const entries = await actRes.json();
    const stats = await statsRes.json();
    const health = await healthRes.json();

    document.getElementById('stat-total').textContent = stats.total_requests || 0;
    document.getElementById('stat-errors').textContent = stats.total_errors || 0;
    const veh = (stats.by_module?.vehicle || 0) + (stats.by_module?.vehicle_osint || 0);
    document.getElementById('stat-vehicle').textContent = veh;
    const osint = Object.entries(stats.by_module || {}).filter(([k]) => !['vehicle','vehicle_osint','dashboard','health','root'].includes(k)).reduce((a,[,v]) => a+v, 0);
    document.getElementById('stat-osint').textContent = osint;

    // Modules
    const modGrid = document.getElementById('mod-grid');
    if (health.modules) {
      modGrid.innerHTML = Object.entries(health.modules).map(([name, info]) =>
        `<span class="mod-chip ${info.available ? 'ok' : 'fail'}" title="${info.detail || ''}">${name}</span>`
      ).join('');
    }

    // Table
    const tbody = document.getElementById('log-body');
    if (!entries.length) {
      tbody.innerHTML = '<tr><td colspan="10" class="empty">Sin actividad registrada</td></tr>';
    } else {
      tbody.innerHTML = entries.map(renderRow).join('');
    }
  } catch (err) {
    console.error('Dashboard fetch error:', err);
  }
}

function doSearch() {
  const q = document.getElementById('search').value.trim();
  fetchData(q);
}

function clearSearch() {
  document.getElementById('search').value = '';
  fetchData();
}

function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(() => {
    if (document.getElementById('autoRefresh').checked) {
      const q = document.getElementById('search').value.trim();
      fetchData(q);
    }
  }, 5000);
}

function updateClock() {
  document.getElementById('clock').textContent = new Date().toLocaleTimeString('es-MX');
  requestAnimationFrame(() => setTimeout(updateClock, 1000));
}

document.getElementById('search').addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });

fetchData();
startAutoRefresh();
updateClock();
</script>
</body>
</html>"""
