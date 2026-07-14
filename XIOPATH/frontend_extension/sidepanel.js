/**
 * XIOPATH EXPLORER — Side Panel Controller
 * ===========================================
 * State machine: idle → recording → reviewing → executing
 * Manages auth, tab navigation, live feed, step review, DAG, status.
 */
const API_BASE = "http://127.0.0.1:8000/api/v1";

// ─── State ──────────────────────────────────────────────────
const state = {
  mode: "idle",          // idle | recording | reviewing | executing
  steps: [],             // Recorded action steps
  currentIntent: "",
  editingStepIdx: null,
  overlayVisible: true,
};

// ─── DOM References ─────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const $$ = (sel) => document.querySelectorAll(sel);

document.addEventListener("DOMContentLoaded", async () => {
  // ─── Auth ───────────────────────────────────
  const authView = $("auth-view");
  const mainView = $("main-view");
  const loginBtn = $("login-btn");
  const authError = $("auth-error");
  const usernameInput = $("username");
  const passwordInput = $("password");
  const userBadge = $("user-badge");
  const logoutBtn = $("logout-btn");

  // ─── Recording ──────────────────────────────
  const intentInput = $("intent-name");
  const recordBtn = $("record-btn");
  const recordText = $("record-text");
  const liveFeed = $("live-feed");
  const liveCount = $("live-count");
  const stepsBadge = $("steps-badge");

  // ─── Steps ──────────────────────────────────
  const stepsList = $("steps-list");
  const executeBtn = $("execute-btn");
  const validateBtn = $("validate-btn");
  const clearStepsBtn = $("clear-steps-btn");

  // ─── Status ─────────────────────────────────
  const connectionDot = $("connection-dot");
  const apiStatus = $("api-status");
  const apiLatency = $("api-latency");
  const serverVersion = $("server-version");
  const sessionUser = $("session-user");
  const sessionRole = $("session-role");
  const jwtStatus = $("jwt-status");

  // ══════════════════════════════════════════════
  // AUTH LOGIC
  // ══════════════════════════════════════════════
  const data = await chrome.storage.local.get(["jwt_token", "username", "role"]);
  if (data.jwt_token) {
    showMain(data.username, data.role);
  }

  loginBtn.addEventListener("click", async () => {
    const username = usernameInput.value.trim();
    const password = passwordInput.value;
    if (!username || !password) return;

    loginBtn.disabled = true;
    loginBtn.querySelector(".btn-text").textContent = "Connecting...";
    loginBtn.querySelector(".btn-loader").style.display = "inline-block";
    authError.textContent = "";

    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, role: "client" }),
      });
      const result = await res.json();
      if (res.ok && result.token) {
        await chrome.storage.local.set({
          jwt_token: result.token,
          username: result.username,
          role: result.role || "client",
        });
        showMain(result.username, result.role || "client");
      } else {
        authError.textContent = result.detail || "Authentication failed";
      }
    } catch {
      authError.textContent = "Cannot reach XIOPATH server at " + API_BASE;
    } finally {
      loginBtn.disabled = false;
      loginBtn.querySelector(".btn-text").textContent = "Connect to XIOPATH";
      loginBtn.querySelector(".btn-loader").style.display = "none";
    }
  });

  // Allow Enter to submit
  passwordInput.addEventListener("keydown", (e) => { if (e.key === "Enter") loginBtn.click(); });

  logoutBtn.addEventListener("click", async () => {
    await chrome.storage.local.remove(["jwt_token", "username", "role"]);
    authView.classList.add("active");
    mainView.classList.remove("active");
    state.steps = [];
    state.mode = "idle";
    renderSteps();
    renderLiveFeed();
  });

  function showMain(username, role) {
    authView.classList.remove("active");
    mainView.classList.add("active");
    userBadge.textContent = username || "—";
    if (sessionUser) sessionUser.textContent = username || "—";
    if (sessionRole) sessionRole.textContent = role || "client";
    checkHealth();
  }

  // ══════════════════════════════════════════════
  // TAB NAVIGATION
  // ══════════════════════════════════════════════
  $$(".xp-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      $$(".xp-tab").forEach((t) => { t.classList.remove("active"); t.setAttribute("aria-selected", "false"); });
      $$(".xp-panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      tab.setAttribute("aria-selected", "true");
      const panel = $(`panel-${tab.dataset.tab}`);
      if (panel) panel.classList.add("active");

      // Refresh status on Status tab
      if (tab.dataset.tab === "status") checkHealth();
      // Render DAG when switching
      if (tab.dataset.tab === "dag") renderDAG();
    });
  });

  // ══════════════════════════════════════════════
  // RECORDING LOGIC
  // ══════════════════════════════════════════════
  // Restore recording state on panel open
  const storedState = await chrome.storage.local.get(["is_recording", "current_intent", "recorded_nodes"]);
  if (storedState.is_recording) {
    state.mode = "recording";
    state.currentIntent = storedState.current_intent || "";
    state.steps = storedState.recorded_nodes || [];
    intentInput.value = state.currentIntent;
    intentInput.disabled = true;
    recordBtn.classList.add("recording");
    recordText.textContent = "Stop Recording";
    renderLiveFeed();
    updateStepsBadge();
  }

  recordBtn.addEventListener("click", async () => {
    if (state.mode === "recording") {
      // Stop
      state.mode = "idle";
      await chrome.storage.local.set({ is_recording: false });
      recordBtn.classList.remove("recording");
      recordText.textContent = "Start Recording";
      intentInput.disabled = false;
      renderSteps(); // Populate steps tab
    } else {
      // Start
      const intent = intentInput.value.trim();
      if (!intent) {
        intentInput.style.borderColor = "var(--xp-danger)";
        setTimeout(() => { intentInput.style.borderColor = ""; }, 1500);
        return;
      }
      state.mode = "recording";
      state.currentIntent = intent;
      state.steps = [];
      intentInput.disabled = true;
      recordBtn.classList.add("recording");
      recordText.textContent = "Stop Recording";
      await chrome.storage.local.set({
        is_recording: true,
        current_intent: intent,
        recorded_nodes: [],
      });
      renderLiveFeed();
      updateStepsBadge();
    }
  });

  // Listen for new recorded nodes from background
  chrome.storage.onChanged.addListener((changes, namespace) => {
    if (namespace === "local" && changes.recorded_nodes) {
      state.steps = changes.recorded_nodes.newValue || [];
      renderLiveFeed();
      updateStepsBadge();
    }
    if (namespace === "local" && changes.is_recording) {
      if (!changes.is_recording.newValue && state.mode === "recording") {
        state.mode = "idle";
        recordBtn.classList.remove("recording");
        recordText.textContent = "Start Recording";
        intentInput.disabled = false;
      }
    }
  });

  // ══════════════════════════════════════════════
  // LIVE FEED RENDERER
  // ══════════════════════════════════════════════
  function renderLiveFeed() {
    if (state.steps.length === 0) {
      liveFeed.innerHTML = `
        <div class="xp-empty-state">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><circle cx="12" cy="12" r="10"/><path d="M8 12h8"/></svg>
          <span>No actions captured yet</span>
          <span class="xp-empty-hint">Start recording, then interact with a webpage</span>
        </div>`;
      liveCount.textContent = "0";
      return;
    }

    liveCount.textContent = state.steps.length;

    liveFeed.innerHTML = state.steps.map((step, i) => {
      const type = step.action_type || "click";
      const iconClass = type === "fill" ? "fill" : type === "navigate" ? "nav" : "click";
      const iconLetter = type === "fill" ? "F" : type === "navigate" ? "N" : "C";
      const selector = step.place_value?.selector || step.selector || "—";
      const text = step.face_value?.text || step.face_value?.description || `${type} action`;
      const isVar = detectVariable(step);

      return `
        <div class="xp-feed-item" data-step="${i}">
          <div class="xp-feed-icon ${iconClass}">${iconLetter}</div>
          <div class="xp-feed-body">
            <div class="xp-feed-title">${escapeHtml(text)}</div>
            <div class="xp-feed-selector">${escapeHtml(truncate(selector, 50))}</div>
            <div class="xp-feed-meta">
              <span>${type.toUpperCase()}</span>
              <span>Step ${i + 1}</span>
              ${isVar ? `<span class="xp-feed-var">⚡ Variable detected</span>` : ""}
            </div>
          </div>
        </div>`;
    }).join("");

    // Auto-scroll to latest
    liveFeed.scrollTop = liveFeed.scrollHeight;
  }

  // ══════════════════════════════════════════════
  // STEPS TAB RENDERER
  // ══════════════════════════════════════════════
  function renderSteps() {
    if (state.steps.length === 0) {
      stepsList.innerHTML = `<div class="xp-empty-state"><span>No steps recorded</span></div>`;
      executeBtn.style.display = "none";
      return;
    }

    executeBtn.style.display = "flex";

    stepsList.innerHTML = state.steps.map((step, i) => {
      const type = step.action_type || "click";
      const selector = step.place_value?.selector || "—";
      const text = step.face_value?.text || step.face_value?.description || `${type} action`;
      const isEditing = state.editingStepIdx === i;
      const fillValue = step.action_params?.text || "";
      const isVar = detectVariable(step);

      return `
        <div class="xp-step-card" data-step="${i}">
          <div class="xp-step-num">${i + 1}</div>
          <div class="xp-step-body">
            <div class="xp-step-title">
              ${escapeHtml(text)}
              ${isVar ? `<span class="xp-feed-var">⚡</span>` : ""}
            </div>
            <div class="xp-step-detail">${escapeHtml(truncate(selector, 60))}</div>
            ${fillValue ? `<div class="xp-step-detail" style="color:var(--xp-purple);">Value: "${escapeHtml(truncate(fillValue, 30))}"</div>` : ""}
            <div class="xp-step-actions-row">
              <button class="xp-btn-sm" onclick="editStep(${i})">Edit</button>
              <button class="xp-btn-sm" onclick="previewStep(${i})">Preview</button>
              <button class="xp-btn-sm xp-btn-danger-sm" onclick="deleteStep(${i})">Delete</button>
            </div>
            ${isEditing ? renderEditor(step, i) : ""}
          </div>
          <div class="xp-step-validation" id="validation-${i}"></div>
        </div>`;
    }).join("");
  }

  function renderEditor(step, idx) {
    const selector = step.place_value?.selector || "";
    const xpath = step.place_value?.xpath || "";
    const fillVal = step.action_params?.text || "";
    return `
      <div class="xp-step-editor">
        <label style="font-size:10px;color:var(--xp-text-secondary);">Selector (CSS)</label>
        <input type="text" value="${escapeHtml(selector)}" id="edit-selector-${idx}" />
        <label style="font-size:10px;color:var(--xp-text-secondary);">XPath</label>
        <input type="text" value="${escapeHtml(xpath)}" id="edit-xpath-${idx}" />
        ${step.action_type === "fill" ? `
          <label style="font-size:10px;color:var(--xp-text-secondary);">Fill Value</label>
          <input type="text" value="${escapeHtml(fillVal)}" id="edit-value-${idx}" placeholder="vault://key_name or literal" />
        ` : ""}
        <div style="display:flex;gap:4px;justify-content:flex-end;">
          <button class="xp-btn-sm" onclick="saveEdit(${idx})">Save</button>
          <button class="xp-btn-sm" onclick="cancelEdit()">Cancel</button>
        </div>
      </div>`;
  }

  // Expose to inline onclick handlers
  window.editStep = (idx) => {
    state.editingStepIdx = state.editingStepIdx === idx ? null : idx;
    renderSteps();
  };

  window.cancelEdit = () => {
    state.editingStepIdx = null;
    renderSteps();
  };

  window.saveEdit = (idx) => {
    const step = state.steps[idx];
    if (!step) return;
    const selectorEl = $(`edit-selector-${idx}`);
    const xpathEl = $(`edit-xpath-${idx}`);
    const valueEl = $(`edit-value-${idx}`);
    if (selectorEl) step.place_value.selector = selectorEl.value;
    if (xpathEl) step.place_value.xpath = xpathEl.value;
    if (valueEl && step.action_params) step.action_params.text = valueEl.value;
    state.editingStepIdx = null;
    chrome.storage.local.set({ recorded_nodes: state.steps });
    renderSteps();
  };

  window.deleteStep = (idx) => {
    state.steps.splice(idx, 1);
    chrome.storage.local.set({ recorded_nodes: state.steps });
    renderSteps();
    updateStepsBadge();
  };

  window.previewStep = (idx) => {
    const step = state.steps[idx];
    if (!step) return;
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) {
        chrome.tabs.sendMessage(tabs[0].id, {
          action: "preview_step",
          selector: step.place_value?.selector,
          xpath: step.place_value?.xpath,
        });
      }
    });
  };

  // Validate all selectors
  validateBtn?.addEventListener("click", () => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs[0]) return;
      const selectors = state.steps.map((s) => ({
        selector: s.place_value?.selector,
        xpath: s.place_value?.xpath,
      }));
      chrome.tabs.sendMessage(tabs[0].id, {
        action: "validate_selectors",
        selectors: selectors,
      }, (response) => {
        if (!response?.results) return;
        response.results.forEach((r, i) => {
          const el = $(`validation-${i}`);
          if (!el) return;
          if (r.found === 1) {
            el.className = "xp-step-validation valid";
            el.innerHTML = "✓";
          } else if (r.found > 1) {
            el.className = "xp-step-validation ambiguous";
            el.innerHTML = `${r.found}`;
          } else {
            el.className = "xp-step-validation invalid";
            el.innerHTML = "✕";
          }
        });
      });
    });
  });

  // Clear steps
  clearStepsBtn?.addEventListener("click", () => {
    state.steps = [];
    chrome.storage.local.set({ recorded_nodes: [] });
    renderSteps();
    renderLiveFeed();
    updateStepsBadge();
  });

  // Execute workflow
  executeBtn?.addEventListener("click", () => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs[0]) return;
      chrome.runtime.sendMessage({
        action: "execute_workflow",
        steps: state.steps,
        intent: state.currentIntent,
        tabId: tabs[0].id,
      });
    });
  });

  // ══════════════════════════════════════════════
  // DAG RENDERER (Pure SVG)
  // ══════════════════════════════════════════════
  function renderDAG() {
    const canvas = $("dag-canvas");
    if (state.steps.length === 0) {
      canvas.innerHTML = `<div class="xp-empty-state"><span>Record steps to visualize the workflow graph</span></div>`;
      return;
    }

    const nodeW = 150, nodeH = 36, gapY = 50, padX = 20, padY = 20;
    const totalH = state.steps.length * (nodeH + gapY) + padY;

    const typeColors = {
      click: "#00E5FF", fill: "#B388FF", navigate: "#06D6A0", wait: "#FFB800",
    };

    let svg = `<svg width="100%" height="${totalH}" xmlns="http://www.w3.org/2000/svg">`;

    // Edges
    for (let i = 0; i < state.steps.length - 1; i++) {
      const y1 = padY + i * (nodeH + gapY) + nodeH;
      const y2 = padY + (i + 1) * (nodeH + gapY);
      const cx = padX + nodeW / 2;
      svg += `<line x1="${cx}" y1="${y1}" x2="${cx}" y2="${y2}" stroke="rgba(0,229,255,0.3)" stroke-width="2" stroke-dasharray="4,4"/>`;
      // Arrow
      svg += `<polygon points="${cx - 4},${y2 - 4} ${cx + 4},${y2 - 4} ${cx},${y2 + 2}" fill="rgba(0,229,255,0.5)"/>`;
    }

    // Nodes
    state.steps.forEach((step, i) => {
      const x = padX, y = padY + i * (nodeH + gapY);
      const type = step.action_type || "click";
      const color = typeColors[type] || typeColors.click;
      const label = step.face_value?.text || step.face_value?.description || `${type} action`;

      svg += `
        <g class="xp-dag-svg-node" data-index="${i}">
          <rect x="${x}" y="${y}" width="${nodeW}" height="${nodeH}" rx="8"
                fill="#161B22" stroke="${color}" stroke-width="1.5"/>
          <circle cx="${x + 14}" cy="${y + nodeH/2}" r="5" fill="${color}" opacity="0.3"/>
          <text x="${x + 24}" y="${y + nodeH/2 + 4}" fill="${color}"
                font-size="10" font-family="Inter, sans-serif" font-weight="600">
            ${escapeHtml(truncate(label, 16))}
          </text>
          <text x="${x + nodeW - 8}" y="${y + 12}" fill="rgba(255,255,255,0.2)"
                font-size="9" font-family="JetBrains Mono, monospace" text-anchor="end">
            ${i + 1}
          </text>
        </g>`;
    });

    svg += `</svg>`;
    canvas.innerHTML = svg;
  }

  // Export DAG
  $("export-dag-btn")?.addEventListener("click", () => {
    const workflow = {
      intent: state.currentIntent,
      steps: state.steps,
      exported_at: new Date().toISOString(),
      version: "2.0.0",
    };
    const blob = new Blob([JSON.stringify(workflow, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `xiopath_${state.currentIntent || "workflow"}_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  });

  // ══════════════════════════════════════════════
  // STATUS & HEALTH
  // ══════════════════════════════════════════════
  async function checkHealth() {
    const start = Date.now();
    try {
      const res = await fetch(`${API_BASE}/health`);
      const ms = Date.now() - start;
      if (res.ok) {
        const data = await res.json();
        apiStatus.innerHTML = `<span class="xp-dot xp-dot-online"></span> Online`;
        apiLatency.textContent = `${ms}ms`;
        serverVersion.textContent = data.version || "2.0.0";
        connectionDot.classList.add("connected");
        connectionDot.title = "Connected";
      } else {
        setOffline();
      }
    } catch {
      setOffline();
    }

    // JWT check
    const stored = await chrome.storage.local.get(["jwt_token"]);
    if (stored.jwt_token) {
      try {
        const payload = JSON.parse(atob(stored.jwt_token.split(".")[1]));
        const exp = payload.exp ? new Date(payload.exp * 1000) : null;
        if (exp && exp > new Date()) {
          const mins = Math.round((exp - new Date()) / 60000);
          jwtStatus.innerHTML = `<span style="color:var(--xp-success)">Valid</span> · ${mins}m remaining`;
        } else {
          jwtStatus.innerHTML = `<span style="color:var(--xp-danger)">Expired</span>`;
        }
      } catch {
        jwtStatus.textContent = "Present";
      }
    } else {
      jwtStatus.textContent = "Not set";
    }
  }

  function setOffline() {
    apiStatus.innerHTML = `<span class="xp-dot xp-dot-offline"></span> Offline`;
    apiLatency.textContent = "—";
    connectionDot.classList.remove("connected");
    connectionDot.title = "Disconnected";
  }

  // ══════════════════════════════════════════════
  // QUICK ACTIONS
  // ══════════════════════════════════════════════
  $("open-dashboard-btn")?.addEventListener("click", () => {
    chrome.tabs.create({ url: "http://localhost:5173/dashboard" });
  });

  $("toggle-overlay-btn")?.addEventListener("click", () => {
    state.overlayVisible = !state.overlayVisible;
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) {
        chrome.tabs.sendMessage(tabs[0].id, {
          action: "toggle_overlay",
          visible: state.overlayVisible,
        });
      }
    });
  });

  $("copy-debug-btn")?.addEventListener("click", async () => {
    const stored = await chrome.storage.local.get(null);
    const debugInfo = {
      extension: "XIOPATH EXPLORER v2.0.0",
      state: state.mode,
      steps: state.steps.length,
      intent: state.currentIntent,
      username: stored.username,
      api: API_BASE,
      timestamp: new Date().toISOString(),
    };
    navigator.clipboard.writeText(JSON.stringify(debugInfo, null, 2));
    const btn = $("copy-debug-btn");
    const orig = btn.textContent;
    btn.textContent = "Copied!";
    setTimeout(() => { btn.textContent = orig; }, 1500);
  });

  // ══════════════════════════════════════════════
  // UTILITIES
  // ══════════════════════════════════════════════
  function updateStepsBadge() {
    const badge = $("steps-badge");
    if (state.steps.length > 0) {
      badge.textContent = state.steps.length;
      badge.style.display = "inline-block";
    } else {
      badge.style.display = "none";
    }
  }

  function detectVariable(step) {
    if (step.action_type === "fill") {
      const val = step.action_params?.text || "";
      const placeholder = step.face_value?.placeholder || "";
      if (val.includes("vault://")) return true;
      if (/password|email|token|secret|api.key/i.test(placeholder)) return true;
      if (/password|email|token|secret|api.key/i.test(step.place_value?.aria || "")) return true;
    }
    return false;
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function truncate(str, max) {
    if (!str) return "";
    return str.length > max ? str.substring(0, max) + "…" : str;
  }

  // Health check interval
  setInterval(checkHealth, 30000);
});
