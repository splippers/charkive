/* Charkive Web — frontend logic */

function showToast(msg, type) {
  var t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.className = 'toast ' + (type || 'info');
  t.classList.remove('hidden');
  setTimeout(function () { t.classList.add('hidden'); }, 3500);
}

function fmtBytes(n) {
  if (n === 0) return '0 B';
  var units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  var i = 0;
  var v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return (i === 0 ? v : v.toFixed(2)) + ' ' + units[i];
}

function plural(n, s) { return n + ' ' + (n === 1 ? s : s + 's'); }

function tag(status, tier) {
  if (tier) return '<span class="tag tag-' + tier + '">' + tier + '</span>';
  if (status) return '<span class="tag tag-' + status + '">' + status + '</span>';
  return '';
}

// ---- Status polling ----
function updateStatus() {
  fetch('/api/status')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var dot = document.getElementById('status-dot');
      var txt = document.getElementById('status-text');
      if (data.scan_running) {
        dot.className = 'status-dot scanning';
        txt.textContent = 'Scanning...';
      } else if (data.latest_scan) {
        dot.className = 'status-dot online';
        txt.textContent = 'Scan #' + data.latest_scan.id + ' ' + data.latest_scan.duration + ' ago';
      } else {
        dot.className = 'status-dot';
        txt.textContent = 'No scans';
      }
    })
    .catch(function () {
      var dot = document.getElementById('status-dot');
      dot.className = 'status-dot error';
      document.getElementById('status-text').textContent = 'Offline';
    });
}

// ---- Scan runner ----
function runScan() {
  var btn = document.getElementById('btn-scan');
  if (btn) btn.disabled = true;
  showToast('Starting scan...', 'info');
  fetch('/api/scan/run', { method: 'POST' })
    .then(function (r) { return r.json(); })
    .then(function () {
      showToast('Scan started — refresh to see results', 'success');
      var poll = setInterval(function () {
        fetch('/api/scan/progress')
          .then(function (r) { return r.json(); })
          .then(function (p) {
            if (!p.running) {
              clearInterval(poll);
              updateStatus();
              refreshPage();
              if (btn) btn.disabled = false;
            }
          });
      }, 2000);
    })
    .catch(function (err) {
      showToast('Scan error: ' + err, 'error');
      if (btn) btn.disabled = false;
    });
}

function refreshPage() {
  var loc = window.location.pathname;
  if (loc === '/dashboard') { loadDashboard(); }
  else if (loc === '/scans') { loadScansList(); }
  else if (loc.indexOf('/scans/') === 0) { /* handled by specific fns */ }
  else if (loc === '/sanitorium') { loadSanitorium(); }
  else if (loc === '/config') { loadConfig(); }
}

// ---- Dashboard ----
function loadDashboard() {
  fetch('/api/status')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      // Latest scan
      var lsEl = document.getElementById('latest-scan');
      if (data.latest_scan) {
        var s = data.latest_scan;
        lsEl.innerHTML =
          '<div class="stat-row"><span class="stat-label">Scan #' + s.id + '</span><span class="stat-value amber">' + s.duration + ' ago</span></div>' +
          '<div class="stat-row"><span class="stat-label">Root</span><span class="stat-value" style="font-size:0.78rem">' + escHtml(s.root) + '</span></div>' +
          '<div class="stat-row"><span class="stat-label">Files scanned</span><span class="stat-value">' + plural(s.artifact_count, 'file') + '</span></div>';
        if (s.summary) {
          lsEl.innerHTML +=
            '<div class="stat-row"><span class="stat-label">Protected</span><span class="stat-value green">' + fmtBytes(s.summary.protected.bytes) + '</span></div>' +
            '<div class="stat-row"><span class="stat-label">Fluff found</span><span class="stat-value amber">' + fmtBytes(s.summary.fluff.bytes) + '</span></div>' +
            '<div class="stat-row"><span class="stat-label">Review</span><span class="stat-value" style="color:var(--review)">' + fmtBytes(s.summary.review.bytes) + '</span></div>';
        }
      } else {
        lsEl.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:20px 0">No scans yet. Run one to get started.</p>';
      }

      // Tier breakdown
      var tierEl = document.getElementById('tier-breakdown');
      if (data.latest_scan && data.latest_scan.summary) {
        var tiers = data.latest_scan.summary.by_tier || {};
        var fluffB = data.latest_scan.summary.fluff.bytes || 1;
        var tierOrder = ['shyte', 'kiloshyte', 'megashyte', 'gigashyte'];
        var html = '<div class="bar-chart">';
        var hasAny = false;
        tierOrder.forEach(function (t) {
          if (tiers[t] && tiers[t].files > 0) {
            hasAny = true;
            var pct = Math.round((tiers[t].bytes / fluffB) * 100);
            html += '<div class="bar-row">' +
              '<span class="bar-label">' + t + '</span>' +
              '<div class="bar-track"><div class="bar-fill ' + t + '" style="width:' + pct + '%" data-label="' + pct + '%"></div></div>' +
              '<span class="bar-value">' + fmtBytes(tiers[t].bytes) + '</span>' +
              '</div>';
          }
        });
        html += '</div>';
        if (!hasAny) html = '<p style="color:var(--text-muted);text-align:center;padding:10px 0">No fluff classified yet.</p>';
        tierEl.innerHTML = html;
      } else {
        tierEl.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:20px 0">No data.</p>';
      }

      // Protection status
      var protEl = document.getElementById('protection-status');
      if (data.latest_scan && data.latest_scan.summary) {
        var sm = data.latest_scan.summary;
        protEl.innerHTML =
          '<div class="bar-chart">' +
          '<div class="bar-row"><span class="bar-label">Protected</span><div class="bar-track"><div class="bar-fill protect" style="width:' + pctOf(sm.protected.bytes, sm.grand.bytes) + '%" data-label="' + fmtBytes(sm.protected.bytes) + '"></div></div><span class="bar-value">' + fmtBytes(sm.protected.bytes) + '</span></div>' +
          '<div class="bar-row"><span class="bar-label">Fluff</span><div class="bar-track"><div class="bar-fill kiloshyte" style="width:' + pctOf(sm.fluff.bytes, sm.grand.bytes) + '%" data-label="' + fmtBytes(sm.fluff.bytes) + '"></div></div><span class="bar-value">' + fmtBytes(sm.fluff.bytes) + '</span></div>' +
          '<div class="bar-row"><span class="bar-label">Review</span><div class="bar-track"><div class="bar-fill review" style="width:' + pctOf(sm.review.bytes, sm.grand.bytes) + '%" data-label="' + fmtBytes(sm.review.bytes) + '"></div></div><span class="bar-value">' + fmtBytes(sm.review.bytes) + '</span></div>' +
          '</div>';
      } else {
        protEl.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:20px 0">No data.</p>';
      }

      // Config summary
      var cfgEl = document.getElementById('config-summary');
      var heroRoot = document.getElementById('hero-root');
      if (heroRoot) heroRoot.textContent = data.config_root;
      cfgEl.innerHTML =
        '<div class="stat-row"><span class="stat-label">Root</span><span class="stat-value" style="font-size:0.78rem">' + escHtml(data.config_root) + '</span></div>' +
        '<div class="stat-row"><span class="stat-label">Sandbox</span><span class="stat-value ' + (data.sandbox ? 'green' : '') + '">' + (data.sandbox ? 'Enabled' : 'Disabled') + '</span></div>' +
        '<div class="stat-row"><span class="stat-label">Sanctuary</span><span class="stat-value">' + plural(data.sanctuary_patterns.length, 'pattern') + '</span></div>' +
        '<div class="stat-row"><span class="stat-label">Rules</span><span class="stat-value">' + plural(data.rule_count, 'rule') + '</span></div>' +
        (data.gluster_volume ? '<div class="stat-row"><span class="stat-label">Gluster</span><span class="stat-value">' + escHtml(data.gluster_volume) + '</span></div>' : '');

      // Recent artifacts
      loadRecentArtifacts(data.latest_scan);
      var cleanupResult = document.getElementById('cleanup-result');
      if (cleanupResult) {
        cleanupResult.textContent = data.latest_scan
          ? 'Scan #' + data.latest_scan.id + ' is ready for preview.'
          : 'Run a scan first. Preview and quarantine stay disabled until a scan exists.';
      }
    })
    .catch(function (err) {
      showToast('Failed to load dashboard: ' + err, 'error');
    });
}

function pctOf(a, b) {
  if (!b) return 0;
  return Math.round((a / b) * 100);
}

function selectedCleanupTier() {
  return document.getElementById('cleanup-tier').value || null;
}

function cleanupRequest(dryRun, confirmation) {
  var payload = { tier: selectedCleanupTier(), dry_run: dryRun };
  if (confirmation) payload.confirmation = confirmation;
  return fetch('/api/sanitise', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }).then(function (response) {
    return response.json().then(function (data) {
      if (!response.ok) throw new Error(data.detail || 'Request failed');
      return data;
    });
  });
}

function previewSanitise() {
  var result = document.getElementById('cleanup-result');
  result.textContent = 'Checking the latest scan...';
  cleanupRequest(true).then(function (data) {
    result.textContent = 'Preview: ' + plural(data.staged, 'file') + ' · about ' + data.moved_fmt +
      ' would move into the SANitorium. Nothing has moved.';
  }).catch(function (err) {
    result.textContent = 'Preview blocked: ' + err.message;
    showToast('Preview blocked: ' + err.message, 'error');
  });
}

function runSanitise() {
  var tier = selectedCleanupTier();
  var confirmation = null;
  var phraseByTier = { megashyte: 'MEGASHYTE', gigashyte: 'THESE GO TO ELEVEN' };
  var tierOrder = ['shyte', 'kiloshyte', 'megashyte', 'gigashyte'];
  var confirmTier = tier;
  if (!confirmTier) {
    fetch('/api/status').then(function (response) { return response.json(); }).then(function (status) {
      var tiers = status.latest_scan && status.latest_scan.summary ? status.latest_scan.summary.by_tier : {};
      confirmTier = tierOrder.filter(function (name) { return tiers[name] && tiers[name].files > 0; }).pop() || null;
      askToSanitise(confirmTier, phraseByTier);
    }).catch(function (err) { showToast('Could not check scan tiers: ' + err.message, 'error'); });
    return;
  }
  askToSanitise(confirmTier, phraseByTier);
}

function askToSanitise(tier, phraseByTier) {
  var confirmation = null;
  var phrase = phraseByTier[tier];
  if (phrase) {
    confirmation = window.prompt('This tier needs explicit confirmation. Type: ' + phrase);
    if (confirmation === null) return;
  } else if (!window.confirm('Move the selected scan candidates into the SANitorium? They will remain recoverable.')) {
    return;
  }
  var result = document.getElementById('cleanup-result');
  result.textContent = 'Moving candidates into the SANitorium...';
  cleanupRequest(false, confirmation).then(function (data) {
    result.textContent = 'Quarantined ' + plural(data.staged, 'file') + ' · ' + data.moved_fmt +
      ' moved. Restore them from the SANitorium if needed.';
    showToast('Files moved to the SANitorium', 'success');
    loadDashboard();
  }).catch(function (err) {
    result.textContent = 'Quarantine blocked: ' + err.message;
    showToast('Quarantine blocked: ' + err.message, 'error');
  });
}

function escHtml(s) {
  if (!s) return '';
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function loadRecentArtifacts(latestScan) {
  var el = document.getElementById('recent-artifacts');
  if (!latestScan || !latestScan.id) {
    el.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:20px 0">No artifacts to show.</p>';
    return;
  }
  fetch('/api/scans/' + latestScan.id + '/artifacts?limit=20&status=candidate')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (!data.artifacts || data.artifacts.length === 0) {
        el.innerHTML = '<p style="color:var(--text-muted);padding:10px 0">No candidate (fluff) artifacts found.</p>';
        return;
      }
      var h = '<div class="table-wrap"><table><thead><tr><th>Path</th><th>Size</th><th>Tier</th><th>Rule</th></tr></thead><tbody>';
      data.artifacts.forEach(function (a) {
        h += '<tr><td class="path-cell" title="' + escHtml(a.rel_path) + '">' + escHtml(a.rel_path) + '</td>' +
          '<td>' + a.bytes_fmt + '</td>' +
          '<td>' + (a.tier ? tag('candidate', a.tier) : '') + '</td>' +
          '<td style="color:var(--text-muted)">' + (a.rule_name ? escHtml(a.rule_name) : '-') + '</td></tr>';
      });
      h += '</tbody></table></div>';
      el.innerHTML = h;
    })
    .catch(function () {
      el.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:10px 0">Failed to load artifacts.</p>';
    });
}

// ---- Scans list ----
function loadScansList() {
  fetch('/api/scans')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var el = document.getElementById('scans-list');
      if (!data.scans || data.scans.length === 0) {
        el.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:20px 0">No scans recorded.</p>';
        return;
      }
      var h = '<div class="table-wrap"><table><thead><tr><th>ID</th><th>Started</th><th>Duration</th><th>Files</th><th>Protected</th><th>Fluff</th><th>Root</th></tr></thead><tbody>';
      data.scans.forEach(function (s) {
        var prot = s.summary ? fmtBytes(s.summary.protected.bytes) : '-';
        var fluff = s.summary ? fmtBytes(s.summary.fluff.bytes) : '-';
        h += '<tr onclick="location.href=\'/scans/' + s.id + '\'" style="cursor:pointer">' +
          '<td><strong>#' + s.id + '</strong></td>' +
          '<td>' + (s.started_at || '-') + '</td>' +
          '<td>' + s.duration + '</td>' +
          '<td>' + plural(s.artifact_count, 'file') + '</td>' +
          '<td class="stat-value green">' + prot + '</td>' +
          '<td class="stat-value amber">' + fluff + '</td>' +
          '<td style="font-size:0.75rem;color:var(--text-muted)">' + escHtml(s.root) + '</td></tr>';
      });
      h += '</tbody></table></div>';
      el.innerHTML = h;
    })
    .catch(function (err) {
      showToast('Failed to load scans: ' + err, 'error');
    });
}

// ---- Scan detail ----
var _searchTimer = null;
function debounceSearch() {
  if (_searchTimer) clearTimeout(_searchTimer);
  _searchTimer = setTimeout(function () { loadArtifacts(); }, 300);
}

function loadScanMeta() {
  if (!window.scanId) return;
  fetch('/api/scans/' + window.scanId)
    .then(function (r) { return r.json(); })
    .then(function (s) {
      var el = document.getElementById('scan-meta');
      el.innerHTML =
        '<div class="stat-row"><span class="stat-label">Scan #</span><span class="stat-value amber">' + s.id + '</span></div>' +
        '<div class="stat-row"><span class="stat-label">Started</span><span class="stat-value">' + (s.started_at || '-') + '</span></div>' +
        '<div class="stat-row"><span class="stat-label">Duration</span><span class="stat-value">' + s.duration + '</span></div>' +
        '<div class="stat-row"><span class="stat-label">Files</span><span class="stat-value">' + plural(s.artifact_count, 'file') + '</span></div>' +
        '<div class="stat-row"><span class="stat-label">Root</span><span class="stat-value" style="font-size:0.78rem">' + escHtml(s.root) + '</span></div>';

      if (s.summary) {
        var sm = s.summary;
        var sumEl = document.getElementById('scan-summary');
        var h = '<div class="bar-chart">';
        var total = sm.grand.bytes || 1;
        h += '<div class="bar-row"><span class="bar-label">Protected</span><div class="bar-track"><div class="bar-fill protect" style="width:' + pctOf(sm.protected.bytes, total) + '%" data-label="' + fmtBytes(sm.protected.bytes) + '"></div></div><span class="bar-value">' + fmtBytes(sm.protected.bytes) + '</span></div>';
        h += '<div class="bar-row"><span class="bar-label">Fluff</span><div class="bar-track"><div class="bar-fill kiloshyte" style="width:' + pctOf(sm.fluff.bytes, total) + '%" data-label="' + fmtBytes(sm.fluff.bytes) + '"></div></div><span class="bar-value">' + fmtBytes(sm.fluff.bytes) + '</span></div>';
        h += '<div class="bar-row"><span class="bar-label">Review</span><div class="bar-track"><div class="bar-fill review" style="width:' + pctOf(sm.review.bytes, total) + '%" data-label="' + fmtBytes(sm.review.bytes) + '"></div></div><span class="bar-value">' + fmtBytes(sm.review.bytes) + '</span></div>';
        h += '</div>';

        var tiers = sm.by_tier || {};
        var tOrder = ['shyte', 'kiloshyte', 'megashyte', 'gigashyte'];
        tOrder.forEach(function (t) {
          if (tiers[t] && tiers[t].files > 0) {
            h += '<div class="stat-row"><span class="stat-label">' + t + ' fluff</span><span class="stat-value amber">' + fmtBytes(tiers[t].bytes) + ' (' + plural(tiers[t].files, 'file') + ')</span></div>';
          }
        });
        sumEl.innerHTML = h;
      }
    })
    .catch(function (err) {
      showToast('Failed to load scan: ' + err, 'error');
    });
}

function loadArtifacts() {
  if (!window.scanId) return;
  var status = (document.getElementById('filter-status') || {}).value || '';
  var tier = (document.getElementById('filter-tier') || {}).value || '';
  var search = (document.getElementById('filter-search') || {}).value || '';
  var params = 'limit=100&offset=0';
  if (status) params += '&status=' + encodeURIComponent(status);
  if (tier) params += '&tier=' + encodeURIComponent(tier);
  if (search) params += '&search=' + encodeURIComponent(search);

  fetch('/api/scans/' + window.scanId + '/artifacts?' + params)
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var el = document.getElementById('artifacts-table');
      var h = '<p class="meta-line">' + plural(data.total, 'artifact') + ' found</p>';
      if (data.artifacts.length === 0) {
        h += '<p style="color:var(--text-muted);text-align:center;padding:20px 0">No matching artifacts.</p>';
        el.innerHTML = h;
        return;
      }
      h += '<div class="table-wrap"><table><thead><tr><th>Path</th><th>Size</th><th>Status</th><th>Tier</th><th>Rule</th><th>Modified</th></tr></thead><tbody>';
      data.artifacts.forEach(function (a) {
        h += '<tr>' +
          '<td class="path-cell" title="' + escHtml(a.rel_path) + '">' + escHtml(a.rel_path) + '</td>' +
          '<td>' + a.bytes_fmt + '</td>' +
          '<td>' + tag(a.status, null) + '</td>' +
          '<td>' + (a.tier ? tag('candidate', a.tier) : '-') + '</td>' +
          '<td style="color:var(--text-muted);font-size:0.75rem">' + (a.rule_name || '-') + '</td>' +
          '<td style="color:var(--text-muted);font-size:0.75rem">' + (a.mtime ? a.mtime.split('T')[0] : '-') + '</td></tr>';
      });
      h += '</tbody></table></div>';
      el.innerHTML = h;
    })
    .catch(function () {
      document.getElementById('artifacts-table').innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:10px 0">Failed to load artifacts.</p>';
    });
}

// ---- Sanitorium ----
function loadSanitorium() {
  fetch('/api/sanitorium')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var el = document.getElementById('sanitorium-content');
      if (!data.weeks || data.weeks.length === 0) {
        el.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:30px 0">Sanitorium is empty. Run <code>charkive sanitise</code> to move fluff here.</p>';
        return;
      }
      var h = '';
      data.weeks.forEach(function (w) {
        h += '<div class="week-group">' +
          '<div class="week-header">' +
          '<span><strong>' + escHtml(w.week) + '</strong> &mdash; ' + plural(w.file_count, 'file') + '</span>' +
          '<span>' + w.total_fmt + '</span>' +
          '</div>';
        w.files.forEach(function (f) {
          h += '<div class="file-row">' +
            '<span class="file-path" title="' + escHtml(f.rel_path) + '">' + escHtml(f.rel_path) + '</span>' +
            '<span class="file-size">' + f.bytes_fmt + '</span>' +
            '<span class="file-action"><button class="btn btn-sm btn-outline" onclick="quench(\'' + escHtml(f.rel_path) + '\')">Restore</button></span>' +
            '</div>';
        });
        h += '</div>';
      });
      el.innerHTML = h;
    })
    .catch(function (err) {
      showToast('Failed to load sanitorium: ' + err, 'error');
    });
}

function quench(path) {
  if (!confirm('Restore "' + path + '" from sanitorium?')) return;
  fetch('/api/quench', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: path })
  })
    .then(function (r) { return r.json(); })
    .then(function () {
      showToast('Restored: ' + path, 'success');
      loadSanitorium();
    })
    .catch(function (err) {
      showToast('Restore failed: ' + err, 'error');
    });
}

// ---- Config ----
function loadConfig() {
  fetch('/api/config')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var setEl = document.getElementById('config-settings');
      setEl.innerHTML =
        '<div class="stat-row"><span class="stat-label">Root</span><span class="stat-value" style="font-size:0.78rem">' + escHtml(data.root) + '</span></div>' +
        '<div class="stat-row"><span class="stat-label">Sandbox</span><span class="stat-value ' + (data.sandbox ? 'green' : '') + '">' + (data.sandbox ? 'Enabled' : 'Disabled') + '</span></div>' +
        '<div class="stat-row"><span class="stat-label">Spinal Tap Mode</span><span class="stat-value">' + (data.spinal_tap_mode ? 'ON' : 'OFF') + '</span></div>' +
        '<div class="stat-row"><span class="stat-label">Brick Protection</span><span class="stat-value ' + (data.has_brick_protection ? 'green' : 'red') + '">' + (data.has_brick_protection ? 'Active' : 'Disabled') + '</span></div>' +
        '<div class="stat-row"><span class="stat-label">Sanitorium</span><span class="stat-value" style="font-size:0.78rem">' + escHtml(data.sanitorium_path) + '</span></div>' +
        '<div class="stat-row"><span class="stat-label">Retention</span><span class="stat-value">' + plural(data.sanitorium_retention_days, 'day') + '</span></div>' +
        (data.gluster_volume ? '<div class="stat-row"><span class="stat-label">Gluster Volume</span><span class="stat-value">' + escHtml(data.gluster_volume) + '</span></div>' : '') +
        '<div class="stat-row"><span class="stat-label">Protected Extensions</span><span class="stat-value" style="font-size:0.75rem">' + (data.protect_extensions || []).join(', ') + '</span></div>' +
        '<div class="stat-row"><span class="stat-label">Source File</span><span class="stat-value" style="font-size:0.75rem;color:var(--text-muted)">' + escHtml(data.source_file) + '</span></div>';

      var rawEl = document.getElementById('config-raw');
      if (data.raw_yaml) {
        rawEl.innerHTML = '<pre>' + escHtml(data.raw_yaml) + '</pre>';
      } else {
        rawEl.innerHTML = '<p style="color:var(--text-muted)">Raw YAML not available.</p>';
      }
    })
    .catch(function (err) {
      showToast('Failed to load config: ' + err, 'error');
    });
}

function reloadConfig() {
  fetch('/api/config/reload', { method: 'POST' })
    .then(function (r) { return r.json(); })
    .then(function () {
      showToast('Config reloaded', 'success');
      loadConfig();
    })
    .catch(function (err) {
      showToast('Reload failed: ' + err, 'error');
    });
}

// ---- Init by page ----
document.addEventListener('DOMContentLoaded', function () {
  updateStatus();
  setInterval(updateStatus, 10000);

  var path = window.location.pathname;
  if (path === '/dashboard') { loadDashboard(); }
  else if (path === '/scans') { loadScansList(); }
  else if (path.indexOf('/scans/') === 0) {
    loadScanMeta();
    loadArtifacts();
  }
  else if (path === '/sanitorium') { loadSanitorium(); }
  else if (path === '/config') { loadConfig(); }
});
