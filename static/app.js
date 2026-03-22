/* ============================================================
   Beer Pro — Frontend Application
   WebSocket client, view router, score rendering
   ============================================================ */

'use strict';

// ----------------------------------------------------------------
// View router
// ----------------------------------------------------------------

const views = {
  scoreboard: document.getElementById('view-scoreboard'),
  replay:     document.getElementById('view-replay'),
  gameover:   document.getElementById('view-gameover'),
  settings:   document.getElementById('view-settings'),
  setup:      document.getElementById('view-setup'),
  'tv-setup': document.getElementById('view-tv-setup'),
};

let currentView = 'scoreboard';

function showView(name) {
  if (currentView === name) return;
  Object.entries(views).forEach(([key, el]) => {
    el.classList.toggle('active', key === name);
  });
  currentView = name;

  // Clean up replay stream when leaving replay view
  if (name !== 'replay') {
    stopReplayStream();
  }
}

// ----------------------------------------------------------------
// State
// ----------------------------------------------------------------

const appState = {
  team1: 'Team 1',
  team2: 'Team 2',
  scoreT1: 0,
  scoreT2: 0,
  matchT1: 0,
  matchT2: 0,
  history: [[0, 0]],
  replayActive: false,
};

// ----------------------------------------------------------------
// DOM refs
// ----------------------------------------------------------------

const $team1Name   = document.getElementById('team1-name');
const $team2Name   = document.getElementById('team2-name');
const $scoreT1     = document.getElementById('score-t1');
const $scoreT2     = document.getElementById('score-t2');
const $trailT1     = document.getElementById('trail-t1');
const $trailT2     = document.getElementById('trail-t2');
const $matchRecord = document.getElementById('match-record');
const $replayImg   = document.getElementById('replay-img');

const $gameoverTeam  = document.getElementById('gameover-team');
const $gameoverScore = document.getElementById('gameover-score');
const $gameoverMatch = document.getElementById('gameover-match');

const $inputTeam1    = document.getElementById('input-team1');
const $inputTeam2    = document.getElementById('input-team2');
const $settingsForm  = document.getElementById('settings-form');
const $settingsStatus = document.getElementById('settings-status');
const $btnResetMatch = document.getElementById('btn-reset-match');
const $btnBack       = document.getElementById('btn-back');
const $settingsLink  = document.getElementById('settings-link');

// ----------------------------------------------------------------
// Rendering helpers
// ----------------------------------------------------------------

function padScore(n) {
  return String(n).padStart(2, '0');
}

function renderScore(t1, t2) {
  $scoreT1.textContent = padScore(t1);
  $scoreT2.textContent = padScore(t2);
}

function bumpScore(team) {
  const el    = team === 1 ? $scoreT1 : $scoreT2;
  const panel = team === 1
    ? document.getElementById('team1-panel')
    : document.getElementById('team2-panel');
  const color = team === 1 ? '#4a9eff' : '#ff6b4a';

  // Score digit scale bump
  el.classList.remove('bump');
  void el.offsetWidth; // force reflow to restart animation
  el.classList.add('bump');
  setTimeout(() => el.classList.remove('bump'), 200);

  // Whole-panel flash
  panel.classList.remove('panel-flash');
  void panel.offsetWidth;
  panel.classList.add('panel-flash');
  setTimeout(() => panel.classList.remove('panel-flash'), 600);

  // Particle burst from the centre of the score element
  spawnParticles(el, color);
}

function spawnParticles(anchorEl, color) {
  const rect   = anchorEl.getBoundingClientRect();
  const cx     = rect.left + rect.width  / 2;
  const cy     = rect.top  + rect.height / 2;
  const count  = 8;
  const spread = 120; // max px travel

  for (let i = 0; i < count; i++) {
    const angle = (i / count) * Math.PI * 2;
    const dist  = spread * (0.6 + Math.random() * 0.4);
    const dx    = Math.round(Math.cos(angle) * dist);
    const dy    = Math.round(Math.sin(angle) * dist);

    const p = document.createElement('div');
    p.className = 'particle';
    p.style.cssText = [
      `left:${cx - 5}px`,
      `top:${cy - 5}px`,
      `background:${color}`,
      `--dx:${dx}px`,
      `--dy:${dy}px`,
    ].join(';');

    document.body.appendChild(p);
    setTimeout(() => p.remove(), 650);
  }
}

function renderTrail(history) {
  // Filled dots = current score for each team, unfilled = remaining slots up to TARGET.
  // This correctly shrinks filled dots when a point is subtracted.
  const TARGET = 11;
  const lastEntry = history[history.length - 1] || [0, 0];
  const t1Score = lastEntry[0];
  const t2Score = lastEntry[1];

  // Build boolean arrays: true = filled (scored), false = unfilled
  const t1Dots = Array.from({ length: TARGET }, (_, i) => i < t1Score);
  const t2Dots = Array.from({ length: TARGET }, (_, i) => i < t2Score);

  renderDots($trailT1, t1Dots);
  renderDots($trailT2, t2Dots);
}

function renderDots(container, filled) {
  container.innerHTML = '';
  filled.forEach(f => {
    const dot = document.createElement('div');
    dot.className = 'trail-dot' + (f ? ' filled' : '');
    container.appendChild(dot);
  });
}

function renderMatchRecord(t1, t2) {
  $matchRecord.textContent = `${t1} — ${t2}`;
}

function renderSettings(team1, team2) {
  $team1Name.textContent = team1;
  $team2Name.textContent = team2;
  appState.team1 = team1;
  appState.team2 = team2;
  // Pre-fill settings form
  $inputTeam1.value = team1;
  $inputTeam2.value = team2;
  // Keep mobile control labels in sync
  const $ml1 = document.getElementById('mobile-label-t1');
  const $ml2 = document.getElementById('mobile-label-t2');
  if ($ml1) $ml1.textContent = team1;
  if ($ml2) $ml2.textContent = team2;
}

// ----------------------------------------------------------------
// WebSocket
// ----------------------------------------------------------------

let ws = null;
let wsReconnectTimer = null;
const WS_RECONNECT_DELAY = 2000;

function connectWS() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${location.host}/ws`;

  ws = new WebSocket(url);

  ws.onopen = () => {
    console.log('[WS] Connected');
    if (wsReconnectTimer) {
      clearTimeout(wsReconnectTimer);
      wsReconnectTimer = null;
    }
  };

  ws.onmessage = (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }
    handleMessage(msg);
  };

  ws.onclose = () => {
    console.log('[WS] Disconnected. Reconnecting...');
    wsReconnectTimer = setTimeout(connectWS, WS_RECONNECT_DELAY);
  };

  ws.onerror = () => {
    ws.close();
  };
}

function sendWS(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
  }
}

// ----------------------------------------------------------------
// Message handler
// ----------------------------------------------------------------

function handleMessage(msg) {
  switch (msg.type) {

    case 'score': {
      const prevT1 = appState.scoreT1;
      const prevT2 = appState.scoreT2;
      appState.scoreT1 = msg.t1;
      appState.scoreT2 = msg.t2;
      appState.history = msg.history || appState.history;

      if (msg.team1) renderSettings(msg.team1, msg.team2);
      if (msg.match) renderMatchRecord(msg.match[0], msg.match[1]);

      renderScore(msg.t1, msg.t2);
      renderTrail(appState.history);

      if (msg.t1 > prevT1) bumpScore(1);
      if (msg.t2 > prevT2) bumpScore(2);

      if (currentView !== 'settings') showView('scoreboard');
      break;
    }

    case 'settings': {
      renderSettings(msg.team1, msg.team2);
      if (msg.match) {
        appState.matchT1 = msg.match[0];
        appState.matchT2 = msg.match[1];
        renderMatchRecord(msg.match[0], msg.match[1]);
      }
      break;
    }

    case 'replay_start': {
      appState.replayActive = true;
      startReplayStream();
      showView('replay');
      break;
    }

    case 'replay_stop': {
      appState.replayActive = false;
      showView('scoreboard');
      stopReplayStream();
      break;
    }

    case 'game_over': {
      appState.scoreT1 = msg.score[0];
      appState.scoreT2 = msg.score[1];
      if (msg.match) {
        appState.matchT1 = msg.match[0];
        appState.matchT2 = msg.match[1];
      }

      renderScore(msg.score[0], msg.score[1]);

      $gameoverTeam.textContent = msg.winner;
      $gameoverScore.textContent = `${msg.score[0]} — ${msg.score[1]}`;
      $gameoverMatch.textContent =
        `Match: ${appState.team1} ${appState.matchT1} — ${appState.matchT2} ${appState.team2}`;

      showView('gameover');
      spawnConfetti();
      break;
    }

    case 'reset': {
      appState.scoreT1 = 0;
      appState.scoreT2 = 0;
      appState.history = [[0, 0]];
      appState.replayActive = false;

      if (msg.team1) renderSettings(msg.team1, msg.team2);
      if (msg.match) {
        appState.matchT1 = msg.match[0];
        appState.matchT2 = msg.match[1];
        renderMatchRecord(msg.match[0], msg.match[1]);
      }

      renderScore(0, 0);
      renderTrail([[0, 0]]);
      if (currentView !== 'settings') showView('scoreboard');
      break;
    }

    case 'update_progress':
    case 'update_complete':
    case 'update_failed':
      handleUpdateMessage(msg);
      break;

    case 'setup_mode': {
      // Server is in first-boot setup — show appropriate view
      if (isMobile()) {
        showView('setup');
        setupScanOnce();
      } else {
        showView('tv-setup');
        initTvQrCode();
      }
      break;
    }

    case 'setup_complete': {
      // WiFi connected — show success then transition to scoreboard
      if (currentView === 'setup') {
        showSetupStatus(`Connected! IP: ${msg.ip}. Rejoining your home WiFi...`, 'success');
      }
      // Give user a moment to read the message then switch to scoreboard
      setTimeout(() => showView('scoreboard'), 3000);
      break;
    }

    case 'ping':
      // Server keepalive — no action needed
      break;

    default:
      break;
  }
}

// ----------------------------------------------------------------
// Replay stream
// ----------------------------------------------------------------

function startReplayStream() {
  // Add cache-busting param so browser doesn't serve stale frames
  $replayImg.src = `/replay/stream?t=${Date.now()}`;
}

function stopReplayStream() {
  // Setting src to empty stops the browser from consuming the MJPEG stream
  $replayImg.src = '';
}

// ----------------------------------------------------------------
// Settings page
// ----------------------------------------------------------------

$settingsLink.addEventListener('click', (e) => {
  e.preventDefault();
  $inputTeam1.value = appState.team1;
  $inputTeam2.value = appState.team2;
  $settingsStatus.textContent = '';
  showView('settings');
});

$btnBack.addEventListener('click', () => {
  showView('scoreboard');
});

const $btnChangeWifi = document.getElementById('btn-change-wifi');
if ($btnChangeWifi) {
  $btnChangeWifi.addEventListener('click', async () => {
    if (!confirm('This will disconnect Beer Pro from WiFi and restart setup. Continue?')) return;
    try {
      await fetch('/api/wifi/forget', { method: 'POST' });
      // Server broadcasts setup_mode via WS — views will update automatically
      showView('setup');
      _scannedOnce = false;
      setupScanOnce();
    } catch {
      alert('Failed to reset WiFi. Check connection.');
    }
  });
}

$settingsForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const team1 = $inputTeam1.value.trim() || 'Team 1';
  const team2 = $inputTeam2.value.trim() || 'Team 2';

  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ team1, team2 }),
    });
    if (res.ok) {
      $settingsStatus.textContent = 'Saved!';
      $settingsStatus.style.color = 'var(--success)';
      setTimeout(() => { $settingsStatus.textContent = ''; }, 2000);
    }
  } catch {
    $settingsStatus.textContent = 'Failed to save. Check connection.';
    $settingsStatus.style.color = 'var(--danger)';
  }
});

$btnResetMatch.addEventListener('click', async () => {
  if (!confirm('Reset match history? This clears all win counts.')) return;
  try {
    await fetch('/api/reset_match', { method: 'POST' });
    $settingsStatus.textContent = 'Match reset!';
    $settingsStatus.style.color = 'var(--success)';
    setTimeout(() => { $settingsStatus.textContent = ''; }, 2000);
  } catch {
    $settingsStatus.textContent = 'Failed.';
    $settingsStatus.style.color = 'var(--danger)';
  }
});

// ----------------------------------------------------------------
// Hash-based simple routing for /settings deep link
// ----------------------------------------------------------------

function handleHash() {
  if (location.hash === '#settings') {
    $inputTeam1.value = appState.team1;
    $inputTeam2.value = appState.team2;
    showView('settings');
  }
}

window.addEventListener('hashchange', handleHash);
handleHash();

// ----------------------------------------------------------------
// Software update UI (inside Settings view)
// ----------------------------------------------------------------

const $updateUrl          = document.getElementById('update-url');
const $btnUpdateCheck     = document.getElementById('btn-update-check');
const $btnUpdateApply     = document.getElementById('btn-update-apply');
const $btnUpdateRollback  = document.getElementById('btn-update-rollback');
const $updateInfo         = document.getElementById('update-info');
const $updateCurrentVer   = document.getElementById('update-current-version');
const $updateProgressWrap = document.getElementById('update-progress-wrap');
const $updateProgressFill = document.getElementById('update-progress-fill');
const $updateProgressLabel = document.getElementById('update-progress-label');

// Fetch and display current version on page load
async function loadCurrentVersion() {
  try {
    const res = await fetch('/api/update/version');
    const data = await res.json();
    if ($updateCurrentVer) $updateCurrentVer.textContent = 'v' + data.version;
  } catch { /* non-fatal */ }
}

function setUpdateInfo(msg, type) {
  // type: 'ok' | 'error' | 'info'
  if (!$updateInfo) return;
  $updateInfo.textContent = msg;
  $updateInfo.className = 'update-info update-info--' + type;
}

function showUpdateProgress(visible) {
  if (!$updateProgressWrap) return;
  $updateProgressWrap.classList.toggle('hidden', !visible);
}

function setUpdateProgress(stage, pct) {
  if ($updateProgressFill) $updateProgressFill.style.width = pct + '%';
  if ($updateProgressLabel) $updateProgressLabel.textContent = stage;
}

// Handle update_progress / update_complete / update_failed WS messages
// (called from handleMessage)
function handleUpdateMessage(msg) {
  switch (msg.type) {
    case 'update_progress':
      showUpdateProgress(true);
      setUpdateProgress(msg.stage, msg.pct);
      setUpdateInfo(msg.stage, 'info');
      break;

    case 'update_complete':
      showUpdateProgress(false);
      if (msg.version === 'rollback') {
        setUpdateInfo('Rollback applied. Restarting…', 'ok');
      } else {
        setUpdateInfo(`Updated to v${msg.version}. Restarting — reconnect in a moment.`, 'ok');
        if ($updateCurrentVer) $updateCurrentVer.textContent = 'v' + msg.version;
      }
      if ($btnUpdateApply) { $btnUpdateApply.disabled = true; $btnUpdateApply.textContent = 'Apply Update'; }
      if ($btnUpdateCheck) $btnUpdateCheck.disabled = false;
      break;

    case 'update_failed':
      showUpdateProgress(false);
      setUpdateInfo('Update failed: ' + msg.error, 'error');
      if ($btnUpdateApply) { $btnUpdateApply.disabled = false; $btnUpdateApply.textContent = 'Apply Update'; }
      if ($btnUpdateCheck) $btnUpdateCheck.disabled = false;
      break;
  }
}

let _pendingUpdateUrl = '';

if ($btnUpdateCheck) {
  $btnUpdateCheck.addEventListener('click', async () => {
    const url = $updateUrl ? $updateUrl.value.trim() : '';
    if (!url) { setUpdateInfo('Enter an update URL first.', 'error'); return; }

    $btnUpdateCheck.disabled = true;
    $btnUpdateCheck.textContent = 'Checking…';
    setUpdateInfo('', 'info');
    if ($btnUpdateApply) $btnUpdateApply.disabled = true;

    try {
      const res = await fetch('/api/update/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();

      if (!data.ok) {
        setUpdateInfo(data.error || 'Check failed.', 'error');
      } else if (data.is_newer) {
        setUpdateInfo(
          `v${data.new_version} available` +
          (data.changelog ? ` — ${data.changelog}` : '') +
          `. Current: v${data.current_version}`,
          'ok'
        );
        _pendingUpdateUrl = url;
        if ($btnUpdateApply) { $btnUpdateApply.disabled = false; }
      } else {
        setUpdateInfo(
          `Already on latest (v${data.current_version}).` +
          (data.new_version ? ` Package is v${data.new_version}.` : ''),
          'info'
        );
        _pendingUpdateUrl = url;
        if ($btnUpdateApply) $btnUpdateApply.disabled = false; // allow force-apply
      }
    } catch {
      setUpdateInfo('Request failed. Check connection.', 'error');
    } finally {
      $btnUpdateCheck.disabled = false;
      $btnUpdateCheck.textContent = 'Check';
    }
  });
}

if ($btnUpdateApply) {
  $btnUpdateApply.addEventListener('click', async () => {
    const url = _pendingUpdateUrl || ($updateUrl ? $updateUrl.value.trim() : '');
    if (!url) { setUpdateInfo('Enter an update URL first.', 'error'); return; }
    if (!confirm(`Apply update from:\n${url}\n\nThe device will restart automatically.`)) return;

    $btnUpdateApply.disabled = true;
    $btnUpdateApply.textContent = 'Updating…';
    $btnUpdateCheck.disabled = true;
    setUpdateInfo('Starting update…', 'info');
    showUpdateProgress(true);
    setUpdateProgress('Starting…', 0);

    try {
      await fetch('/api/update/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      // Progress and completion come via WebSocket
    } catch {
      setUpdateInfo('Failed to start update. Check connection.', 'error');
      $btnUpdateApply.disabled = false;
      $btnUpdateApply.textContent = 'Apply Update';
      $btnUpdateCheck.disabled = false;
      showUpdateProgress(false);
    }
  });
}

if ($btnUpdateRollback) {
  $btnUpdateRollback.addEventListener('click', async () => {
    if (!confirm('Roll back to the previous version? The device will restart.')) return;
    setUpdateInfo('Rolling back…', 'info');
    try {
      await fetch('/api/update/rollback', { method: 'POST' });
      // Result comes via WebSocket update_complete
    } catch {
      setUpdateInfo('Rollback request failed.', 'error');
    }
  });
}

// ----------------------------------------------------------------
// Setup view — WiFi configuration (phone)
// ----------------------------------------------------------------

const $networkList    = document.getElementById('network-list');
const $scanPlaceholder = document.getElementById('scan-placeholder');
const $setupSsid      = document.getElementById('setup-ssid');
const $setupPassword  = document.getElementById('setup-password');
const $setupForm      = document.getElementById('setup-form');
const $setupStatus    = document.getElementById('setup-status');
const $btnScan        = document.getElementById('btn-scan');
const $btnPwToggle    = document.getElementById('btn-pw-toggle');
const $btnConnect     = document.getElementById('btn-connect');

let _scannedOnce = false;

function showSetupStatus(msg, type) {
  // type: 'success' | 'error' | 'info'
  $setupStatus.textContent = msg;
  $setupStatus.className = 'setup-status setup-status--' + type;
}

function signalBars(pct) {
  // Returns 0-4 filled bars based on signal percentage
  if (pct >= 80) return 4;
  if (pct >= 55) return 3;
  if (pct >= 30) return 2;
  return 1;
}

function renderNetworkList(networks) {
  $networkList.innerHTML = '';
  if (!networks || networks.length === 0) {
    $networkList.innerHTML = '<div class="setup-no-networks">No networks found. Try scanning again.</div>';
    return;
  }

  networks.forEach(net => {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'setup-network-item';

    const bars = signalBars(net.signal);
    const lockIcon = net.secured ? '<span class="setup-lock">&#128274;</span>' : '';
    const barHtml = Array.from({ length: 4 }, (_, i) =>
      `<span class="signal-bar ${i < bars ? 'filled' : ''}"></span>`
    ).join('');

    item.innerHTML = `
      <span class="setup-net-name">${escapeHtml(net.ssid)}</span>
      ${lockIcon}
      <span class="setup-signal">${barHtml}</span>
    `;

    item.addEventListener('click', () => {
      // Select this network
      document.querySelectorAll('.setup-network-item').forEach(el => el.classList.remove('selected'));
      item.classList.add('selected');
      $setupSsid.value = net.ssid;
      if (net.secured) {
        $setupPassword.focus();
      }
    });

    $networkList.appendChild(item);
  });
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

async function scanNetworks() {
  $btnScan.disabled = true;
  $btnScan.textContent = 'Scanning…';
  $scanPlaceholder.style.display = 'flex';
  $networkList.innerHTML = '';
  $networkList.appendChild($scanPlaceholder);

  try {
    const res = await fetch('/api/wifi/scan');
    const data = await res.json();
    renderNetworkList(data.networks || []);
  } catch {
    $networkList.innerHTML = '<div class="setup-no-networks">Scan failed. Check connection.</div>';
  } finally {
    $btnScan.disabled = false;
    $btnScan.textContent = '↻ Scan';
    _scannedOnce = true;
  }
}

function setupScanOnce() {
  if (!_scannedOnce) scanNetworks();
}

// Scan button
if ($btnScan) {
  $btnScan.addEventListener('click', scanNetworks);
}

// Password show/hide toggle
if ($btnPwToggle) {
  $btnPwToggle.addEventListener('click', () => {
    const isPassword = $setupPassword.type === 'password';
    $setupPassword.type = isPassword ? 'text' : 'password';
    $btnPwToggle.textContent = isPassword ? '🙈' : '👁';
  });
}

// Connect form submit
if ($setupForm) {
  $setupForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const ssid = $setupSsid.value.trim();
    const password = $setupPassword.value;

    if (!ssid) {
      showSetupStatus('Please select or enter a network name.', 'error');
      return;
    }

    $btnConnect.disabled = true;
    $btnConnect.textContent = 'Connecting…';
    showSetupStatus('Connecting, please wait…', 'info');

    try {
      const res = await fetch('/api/wifi/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ssid, password }),
      });
      const data = await res.json();

      if (data.ok) {
        showSetupStatus(`Connected to "${ssid}"! IP: ${data.ip}`, 'success');
        // Server will broadcast setup_complete via WebSocket
      } else {
        showSetupStatus(data.error || 'Connection failed. Check your password.', 'error');
        $btnConnect.disabled = false;
        $btnConnect.textContent = 'Connect';
      }
    } catch {
      showSetupStatus('Request failed. Check device connection.', 'error');
      $btnConnect.disabled = false;
      $btnConnect.textContent = 'Connect';
    }
  });
}

// ----------------------------------------------------------------
// TV setup splash — QR code
// ----------------------------------------------------------------

let _qrGenerated = false;

function initTvQrCode() {
  if (_qrGenerated) return;
  const container = document.getElementById('tv-qr-code');
  if (!container || typeof QRCode === 'undefined') return;

  try {
    new QRCode(container, {
      text: 'http://192.168.4.1:8080/setup',
      width: 180,
      height: 180,
      colorDark: '#f5c518',
      colorLight: '#0d0d0d',
      correctLevel: QRCode.CorrectLevel.M,
    });
    _qrGenerated = true;
  } catch (err) {
    console.warn('QR code generation failed:', err);
  }
}

// ----------------------------------------------------------------
// Mobile controls
// ----------------------------------------------------------------

const $mobileControls  = document.getElementById('mobile-controls');
const $mobileLabelT1   = document.getElementById('mobile-label-t1');
const $mobileLabelT2   = document.getElementById('mobile-label-t2');

function isMobile() {
  // Touch device OR narrow viewport — covers phones and tablets
  return (
    ('ontouchstart' in window || navigator.maxTouchPoints > 0) ||
    window.innerWidth <= 900
  );
}

function initMobileControls() {
  if (!isMobile()) return;

  $mobileControls.classList.remove('hidden');
  document.body.classList.add('has-mobile-controls');

  async function pressKey(key) {
    // Prefer WebSocket (already open, zero extra round-trips).
    // Fall back to REST only if the WS connection is not yet open.
    if (ws && ws.readyState === WebSocket.OPEN) {
      sendWS({ type: 'key', key });
      return;
    }
    const restMap = {
      KEY_1: () => fetch('/api/score', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ team: 1, delta: 1  }) }),
      KEY_2: () => fetch('/api/score', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ team: 1, delta: -1 }) }),
      KEY_3: () => fetch('/api/score', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ team: 2, delta: 1  }) }),
      KEY_4: () => fetch('/api/score', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ team: 2, delta: -1 }) }),
      KEY_5: () => fetch('/api/replay', { method: 'POST' }),
    };
    if (restMap[key]) restMap[key]().catch(() => {});
  }

  document.getElementById('mbtn-t1-up').addEventListener('click',    () => pressKey('KEY_1'));
  document.getElementById('mbtn-t1-down').addEventListener('click',  () => pressKey('KEY_2'));
  document.getElementById('mbtn-t2-up').addEventListener('click',    () => pressKey('KEY_3'));
  document.getElementById('mbtn-t2-down').addEventListener('click',  () => pressKey('KEY_4'));
  document.getElementById('mbtn-replay').addEventListener('click',   () => pressKey('KEY_5'));
}

// ----------------------------------------------------------------
// Confetti (game win)
// ----------------------------------------------------------------

function spawnConfetti() {
  const container = document.getElementById('view-gameover');
  if (!container) return;

  const colors   = ['#f5c518', '#4a9eff', '#ff6b4a', '#ffffff'];
  const count    = 60;
  const pieces   = [];

  for (let i = 0; i < count; i++) {
    const p = document.createElement('div');
    p.className = 'confetti-piece';

    const color    = colors[i % colors.length];
    const x        = (Math.random() * 100).toFixed(1) + '%';
    const w        = (6 + Math.random() * 8).toFixed(1) + 'px';
    const h        = (10 + Math.random() * 12).toFixed(1) + 'px';
    const delay    = (Math.random() * 1.2).toFixed(2) + 's';
    const duration = (1.8 + Math.random() * 1.4).toFixed(2) + 's';
    // Random horizontal drift and rotation for each piece
    const drift    = ((Math.random() - 0.5) * 120).toFixed(0) + 'px';
    const spin     = ((Math.random() - 0.5) * 720).toFixed(0) + 'deg';

    p.style.cssText = [
      `--x:${x}`,
      `--w:${w}`,
      `--h:${h}`,
      `--color:${color}`,
      `--delay:${delay}`,
      `--duration:${duration}`,
      `--drift:${drift}`,
      `--spin:${spin}`,
    ].join(';');

    container.appendChild(p);
    pieces.push(p);
  }

  // Clean up after the longest possible animation finishes
  setTimeout(() => pieces.forEach(p => p.remove()), 4000);
}

// ----------------------------------------------------------------
// Boot
// ----------------------------------------------------------------

initMobileControls();
loadCurrentVersion();
connectWS();
