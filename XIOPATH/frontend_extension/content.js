/**
 * XIOPATH EXPLORER — Content Script
 * =====================================
 * Premium element inspector, smart action capture,
 * step preview, validation, execution, and HITL overlays.
 */

let isRecording = false;
let hoveredElement = null;
let overlayVisible = true;
let inspectorBadge = null;

// ─── Initialize State ───────────────────────────────────────
chrome.storage.local.get(["is_recording"], (data) => {
  isRecording = data.is_recording || false;
});

chrome.storage.onChanged.addListener((changes, namespace) => {
  if (namespace === "local" && changes.is_recording) {
    isRecording = changes.is_recording.newValue;
    if (!isRecording) {
      removeHighlight();
      removeInspectorBadge();
    }
  }
});

// ─── Dashboard Bridge ───────────────────────────────────────
window.addEventListener("ANTIGRAVITY_START_AUTOPILOT", (e) => {
  chrome.runtime.sendMessage({
    action: "start_auto_pilot",
    intent: e.detail.intent,
  });
});

// ═══════════════════════════════════════════════════════════
// ELEMENT INSPECTOR (Recording Mode)
// ═══════════════════════════════════════════════════════════

document.addEventListener("mouseover", (e) => {
  if (!isRecording || !overlayVisible) return;
  if (isXiopathElement(e.target)) return;

  if (hoveredElement && hoveredElement !== e.target) {
    hoveredElement.classList.remove("xp-inspector-highlight");
  }

  hoveredElement = e.target;
  hoveredElement.classList.add("xp-inspector-highlight");
  showInspectorBadge(e.target, e.clientX, e.clientY);
}, true);

document.addEventListener("mouseout", (e) => {
  if (!isRecording || !overlayVisible) return;
  if (hoveredElement === e.target) {
    removeHighlight();
  }
}, true);

function removeHighlight() {
  if (hoveredElement) {
    hoveredElement.classList.remove("xp-inspector-highlight");
    hoveredElement = null;
  }
  removeInspectorBadge();
}

// ─── Inspector Badge ────────────────────────────────────────
function showInspectorBadge(el, mouseX, mouseY) {
  if (!inspectorBadge) {
    inspectorBadge = document.createElement("div");
    inspectorBadge.className = "xp-inspector-badge";
    document.body.appendChild(inspectorBadge);
  }

  const tag = el.tagName.toLowerCase();
  const cls = el.className && typeof el.className === "string"
    ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".")
    : "";
  const id = el.id ? `#${el.id}` : "";
  const rect = el.getBoundingClientRect();
  const dims = `${Math.round(rect.width)}×${Math.round(rect.height)}`;

  inspectorBadge.innerHTML = `
    <span class="xp-ib-tag">${tag}${id}${cls.substring(0, 30)}</span>
    <span class="xp-ib-dims">${dims}</span>
  `;

  // Position: below the element, avoid viewport edges
  let top = rect.bottom + 6;
  let left = rect.left;

  if (top + 30 > window.innerHeight) top = rect.top - 34;
  if (left + 200 > window.innerWidth) left = window.innerWidth - 210;
  if (left < 5) left = 5;

  inspectorBadge.style.top = `${top}px`;
  inspectorBadge.style.left = `${left}px`;
  inspectorBadge.style.display = "flex";
}

function removeInspectorBadge() {
  if (inspectorBadge) inspectorBadge.style.display = "none";
}

// ═══════════════════════════════════════════════════════════
// ACTION CAPTURE
// ═══════════════════════════════════════════════════════════

// ─── Click Capture ──────────────────────────────────────────
document.addEventListener("click", (e) => {
  if (!isRecording) return;
  if (isXiopathElement(e.target)) return;

  const target = e.target;

  // Remove highlight BEFORE capture to prevent washout in base64 screenshots
  target.classList.remove("xp-inspector-highlight");
  removeInspectorBadge();

  const locators = extractLocators(target);
  const boundingBox = extractBoundingBox(target);
  const elemSig = extractElementSignature(target);

  const text = target.innerText || target.value || target.getAttribute("aria-label") || target.alt || "";

  const payload = {
    url: window.location.href,
    action_type: "click",
    face_value: {
      description: `Clicked ${target.tagName.toLowerCase()} element`,
      text: text.trim().substring(0, 100),
      bounding_box: boundingBox,
      element_signature: elemSig,
    },
    place_value: {
      ...locators,
      method: "playwright_locator",
    },
    action_params: {},
  };

  chrome.runtime.sendMessage({ action: "record_action_event", payload });

  // Visual feedback: cyan flash (replaces the highlight)
  showCaptureFlash(target);
}, true);

// ─── Fill Capture ───────────────────────────────────────────
document.addEventListener("change", (e) => {
  if (!isRecording) return;
  const target = e.target;
  if (!["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
  if (isXiopathElement(target)) return;

  // Remove highlight BEFORE capture to prevent washout in base64 screenshots
  target.classList.remove("xp-inspector-highlight");
  removeInspectorBadge();

  const locators = extractLocators(target);
  const boundingBox = extractBoundingBox(target);
  const elemSig = extractElementSignature(target);

  const payload = {
    url: window.location.href,
    action_type: "fill",
    face_value: {
      description: `Filled ${target.tagName.toLowerCase()} element`,
      placeholder: target.placeholder || "",
      bounding_box: boundingBox,
      element_signature: elemSig,
    },
    place_value: {
      ...locators,
      method: "playwright_locator",
    },
    action_params: {
      text: target.value,
    },
  };

  chrome.runtime.sendMessage({ action: "record_action_event", payload });
  showCaptureFlash(target);
}, true);

// ═══════════════════════════════════════════════════════════
// LOCATOR EXTRACTION (9-Tier Stability-Ordered Cascade)
// ═══════════════════════════════════════════════════════════

function extractLocators(el) {
  return {
    selector: getCssSelector(el),
    xpath: getXPath(el),
    axes_xpath: getAxesXPaths(el),
    test_id: el.getAttribute("data-testid") || el.getAttribute("data-test-id") || el.getAttribute("data-test")
          || el.getAttribute("data-cy") || el.getAttribute("data-automation-id") || el.getAttribute("data-qa") || null,
    aria: el.getAttribute("aria-label") || null,
    inner_text: el.innerText ? el.innerText.trim().substring(0, 80) : null,
    role: el.getAttribute("role") || null,
    name: el.getAttribute("name") || null,
  };
}

function extractBoundingBox(el) {
  const rect = el.getBoundingClientRect();
  let effectiveBg = "rgb(255, 255, 255)";
  let parent = el;
  let bgDepth = 0;
  while (parent && parent !== document && bgDepth < 10) {
    const bg = window.getComputedStyle(parent).backgroundColor;
    if (bg !== "rgba(0, 0, 0, 0)" && bg !== "transparent") {
      effectiveBg = bg;
      break;
    }
    parent = parent.parentNode;
    bgDepth++;
  }
  return {
    x: rect.x, y: rect.y,
    width: rect.width, height: rect.height,
    // Cross-resolution normalized coordinates (0.0 – 1.0)
    nx: rect.x / window.innerWidth,
    ny: rect.y / window.innerHeight,
    nw: rect.width / window.innerWidth,
    nh: rect.height / window.innerHeight,
    windowWidth: window.innerWidth,
    windowHeight: window.innerHeight,
    // Scroll-aware: store page scroll offset at capture time
    scrollX: window.scrollX,
    scrollY: window.scrollY,
    effective_bg_color: effectiveBg,
  };
}

function extractElementSignature(el) {
  const cs = window.getComputedStyle(el);
  return {
    tag: el.tagName.toLowerCase(),
    classes: (el.className && typeof el.className === "string")
      ? el.className.trim().split(/\s+/).slice(0, 5)
      : [],
    computed_color: cs.color,
    computed_font_size: cs.fontSize,
    computed_bg: cs.backgroundColor,
  };
}

// ━━━ SECURITY: XPath/CSS Injection Prevention ━━━━━━━━━━━━━━━━━━━━━━
function escapeXPathString(str) {
  if (!str) return '""';
  if (!str.includes('"')) return '"' + str + '"';
  if (!str.includes("'")) return "'" + str + "'";
  return "concat(" + str.split('"').map(s => '"' + s + '"').join(",'\"',") + ")";
}

function escapeCssId(id) {
  if (!id) return "";
  return id.replace(/([\\!"#$%&'()*+,./:;<=>?@[\]^`{|}~])/g, "\\$1");
}

function getCssSelector(el) {
  if (!(el instanceof Element)) return "";
  const path = [];
  while (el.nodeType === Node.ELEMENT_NODE) {
    let selector = el.nodeName.toLowerCase();
    if (el.id) {
      selector += "#" + escapeCssId(el.id);
      path.unshift(selector);
      break;
    } else {
      let sib = el, nth = 1;
      while ((sib = sib.previousElementSibling)) {
        if (sib.nodeName.toLowerCase() === selector) nth++;
      }
      if (nth !== 1) selector += `:nth-of-type(${nth})`;
    }
    path.unshift(selector);
    el = el.parentNode;
  }
  return path.join(" > ");
}

function getXPath(el) {
  if (el.id) return `//*[@id=${escapeXPathString(el.id)}]`;
  if (el === document.body) return el.tagName;
  let ix = 0;
  const siblings = el.parentNode ? el.parentNode.childNodes : [];
  for (let i = 0; i < siblings.length; i++) {
    if (siblings[i] === el) {
      const parentXPath = getXPath(el.parentNode);
      return parentXPath ? `${parentXPath}/${el.tagName}[${ix + 1}]` : null;
    }
    if (siblings[i].nodeType === 1 && siblings[i].tagName === el.tagName) ix++;
  }
  return null;
}

/**
 * AxesXPath — Uniqueness-Validated Relational XPath Generator.
 * Each generated XPath is validated to match exactly 1 element.
 * Non-unique matches get a stability penalty (×0.6).
 */
function countXPathMatches(xpath) {
  try {
    const xr = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
    return xr.snapshotLength;
  } catch { return 0; }
}

function getAxesXPaths(el) {
  const axes = [];
  const elTag = el.tagName.toLowerCase();
  const MAX_ANCESTOR_DEPTH = 20;

  // Strategy 1: Ancestor-anchored — nearest ancestor with id or data-testid
  let ancestor = el.parentNode;
  let depth = 0;
  while (ancestor && ancestor !== document.body && ancestor !== document && depth < MAX_ANCESTOR_DEPTH) {
    depth++;
    let anchorAttr = null, anchorVal = null, strategy = null, baseStability = 0;

    if (ancestor.id) {
      anchorAttr = "id"; anchorVal = ancestor.id;
      strategy = "ancestor_id"; baseStability = 0.95;
    } else if (ancestor.getAttribute && ancestor.getAttribute("data-testid")) {
      anchorAttr = "data-testid"; anchorVal = ancestor.getAttribute("data-testid");
      strategy = "ancestor_testid"; baseStability = 0.92;
    }

    if (anchorAttr) {
      let xpath = `//*[@${anchorAttr}=${escapeXPathString(anchorVal)}]//${elTag}`;
      let matchCount = countXPathMatches(xpath);

      // If ambiguous, add discriminating attributes
      if (matchCount > 1) {
        const elName = el.getAttribute("name");
        const elType = el.getAttribute("type");
        const elPlaceholder = el.getAttribute("placeholder");
        if (elName) {
          xpath += `[@name=${escapeXPathString(elName)}]`;
        } else if (elType) {
          xpath += `[@type=${escapeXPathString(elType)}]`;
        } else if (elPlaceholder) {
          xpath += `[contains(@placeholder,${escapeXPathString(elPlaceholder.substring(0, 40))})]`;
        } else {
          const siblings = ancestor.querySelectorAll(elTag);
          let pos = 0;
          for (let i = 0; i < siblings.length; i++) {
            if (siblings[i] === el) { pos = i + 1; break; }
          }
          if (pos > 0) xpath = `//*[@${anchorAttr}=${escapeXPathString(anchorVal)}]//${elTag}[${pos}]`;
        }
        matchCount = countXPathMatches(xpath);
      }

      axes.push({
        strategy, xpath,
        stability: matchCount === 1 ? baseStability : baseStability * 0.6,
        unique: matchCount === 1,
      });
      break;
    }
    ancestor = ancestor.parentNode;
  }

  // Strategy 2: Sibling-anchored — preceding label/heading text
  let prevSib = el.previousElementSibling;
  let sibDepth = 0;
  while (prevSib && sibDepth < 5) {
    sibDepth++;
    const sibText = prevSib.innerText?.trim() || "";
    if (sibText.length > 0 && sibText.length <= 60) {
      const sibTag = prevSib.tagName.toLowerCase();
      const xpath = `//${sibTag}[normalize-space()=${escapeXPathString(sibText)}]/following-sibling::${elTag}[1]`;
      const matchCount = countXPathMatches(xpath);
      axes.push({
        strategy: "sibling_text", xpath,
        stability: matchCount === 1 ? 0.85 : 0.50,
        unique: matchCount === 1,
      });
      break;
    }
    prevSib = prevSib.previousElementSibling;
  }

  // Strategy 3: Parent-label association (<label for="...">)
  if (el.id) {
    try {
      const labelFor = document.querySelector(`label[for=${JSON.stringify(el.id)}]`);
      if (labelFor?.innerText) {
        const xpath = `//label[normalize-space()=${escapeXPathString(labelFor.innerText.trim())}]/following::${elTag}[1]`;
        const matchCount = countXPathMatches(xpath);
        axes.push({
          strategy: "label_for", xpath,
          stability: matchCount === 1 ? 0.90 : 0.55,
          unique: matchCount === 1,
        });
      }
    } catch {}
  }

  // Strategy 4: Semantic-anchored — element's own attributes
  const ariaLabel = el.getAttribute("aria-label");
  const placeholder = el.getAttribute("placeholder");
  const elName = el.getAttribute("name");
  if (ariaLabel) {
    const xpath = `//${elTag}[@aria-label=${escapeXPathString(ariaLabel)}]`;
    const matchCount = countXPathMatches(xpath);
    axes.push({
      strategy: "semantic_aria", xpath,
      stability: matchCount === 1 ? 0.88 : 0.52,
      unique: matchCount === 1,
    });
  } else if (placeholder) {
    const xpath = `//${elTag}[contains(@placeholder,${escapeXPathString(placeholder.substring(0, 40))})]`;
    const matchCount = countXPathMatches(xpath);
    axes.push({
      strategy: "semantic_placeholder", xpath,
      stability: matchCount === 1 ? 0.80 : 0.48,
      unique: matchCount === 1,
    });
  } else if (elName) {
    const xpath = `//${elTag}[@name=${escapeXPathString(elName)}]`;
    const matchCount = countXPathMatches(xpath);
    axes.push({
      strategy: "semantic_name", xpath,
      stability: matchCount === 1 ? 0.85 : 0.50,
      unique: matchCount === 1,
    });
  }

  // Sort by stability (highest first), return top 3
  axes.sort((a, b) => b.stability - a.stability);
  return axes.slice(0, 3);
}

// ═══════════════════════════════════════════════════════════
// MESSAGE HANDLERS
// ═══════════════════════════════════════════════════════════

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {

  // ─── Execute Node ─────────────────────────
  if (request.action === "execute_node") {
    const node = request.node;
    const place = node.place_value || {};
    const params = node.action_params || {};

    // Show execution progress overlay
    if (request.stepIndex !== undefined) {
      showExecutionProgress(request.stepIndex + 1, request.totalSteps, node);
    }

    let targetElement = resolveElement(place);

    if (targetElement) {
      if (node.action_type === "click") {
        targetElement.click();
      } else if (node.action_type === "fill" && params.text) {
        targetElement.value = params.text;
        targetElement.dispatchEvent(new Event("input", { bubbles: true }));
        targetElement.dispatchEvent(new Event("change", { bubbles: true }));
      }
      showCaptureFlash(targetElement);
      sendResponse({ status: "success" });
    } else {
      console.error("[XIOPATH] Element not found:", place);
      chrome.runtime.sendMessage({ action: "auto_pilot_failed", node });
      sendResponse({ status: "failed" });
    }
    return true;
  }

  // ─── Preview Step ─────────────────────────
  if (request.action === "preview_step") {
    removeHighlight();
    const el = resolveElement({ selector: request.selector, xpath: request.xpath });
    if (el) {
      el.classList.add("xp-preview-highlight");
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setTimeout(() => el.classList.remove("xp-preview-highlight"), 3000);
    }
    sendResponse({ status: el ? "found" : "not_found" });
    return true;
  }

  // ─── Validate Selectors ───────────────────
  if (request.action === "validate_selectors") {
    const results = request.selectors.map((s) => {
      let count = 0;
      try {
        if (s.selector) count = document.querySelectorAll(s.selector).length;
      } catch {}
      if (count === 0 && s.xpath) {
        try {
          const xr = document.evaluate(s.xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
          count = xr.snapshotLength;
        } catch {}
      }
      return { found: count };
    });
    sendResponse({ results });
    return true;
  }

  // ─── Toggle Overlay ───────────────────────
  if (request.action === "toggle_overlay") {
    overlayVisible = request.visible;
    if (!overlayVisible) removeHighlight();
    sendResponse({ status: "ok" });
    return true;
  }

  // ─── HITL Trigger ─────────────────────────
  if (request.action === "trigger_hitl") {
    triggerHITLOverlay(request.node);
    chrome.storage.local.set({ is_recording: true, current_intent: request.node.intent });
    sendResponse({ status: "acknowledged" });
    return true;
  }

  // ─── DOM Snapshot ─────────────────────────
  if (request.action === "request_dom_snapshot") {
    const clone = document.documentElement.cloneNode(true);
    clone.querySelectorAll("script, style, link, meta, noscript, svg, .xp-inspector-badge, .xp-hitl-overlay, .xp-execution-progress")
      .forEach((s) => s.remove());
    sendResponse({ status: "success", dom: clone.outerHTML });
    return true;
  }

  // ─── Execute LLM Action ───────────────────
  if (request.action === "execute_llm_action") {
    const action = request.action_data;
    try {
      const el = document.querySelector(action.selector);
      if (el) {
        if (action.action === "click") el.click();
        else if (action.action === "fill" && action.text) {
          el.value = action.text;
          el.dispatchEvent(new Event("change", { bubbles: true }));
        }
        sendResponse({ status: "success" });
        return true;
      }
    } catch {}
    sendResponse({ status: "failed" });
    return true;
  }

  return false;
});

// ═══════════════════════════════════════════════════════════
// ELEMENT RESOLUTION (9-Tier Stability-Ordered Cascade)
// with Telemetry — returns { el, tier, locator } for observability
// ═══════════════════════════════════════════════════════════

function resolveElement(place) {
  let el = null;
  let resolvedTier = null;
  let resolvedLocator = null;

  // Tier 1: test-id (highest stability — explicit developer markers)
  if (!el && place.test_id) {
    el = document.querySelector(`[data-testid="${place.test_id}"]`)
      || document.querySelector(`[data-test-id="${place.test_id}"]`)
      || document.querySelector(`[data-cy="${place.test_id}"]`)
      || document.querySelector(`[data-automation-id="${place.test_id}"]`)
      || document.querySelector(`[data-qa="${place.test_id}"]`);
    if (el) { resolvedTier = 1; resolvedLocator = `test-id:${place.test_id}`; }
  }

  // Tier 2: CSS selector
  if (!el && place.selector) {
    try {
      el = document.querySelector(place.selector);
      if (el) { resolvedTier = 2; resolvedLocator = `css:${place.selector.substring(0, 60)}`; }
    } catch {}
  }

  // Tier 3: AxesXPath — relational, stability-ordered (more stable than positional XPath)
  if (!el && place.axes_xpath && Array.isArray(place.axes_xpath)) {
    for (const axe of place.axes_xpath) {
      const axeXp = typeof axe === "string" ? axe : axe?.xpath;
      if (!axeXp) continue;
      try {
        const xr = document.evaluate(
          axeXp, document, null,
          XPathResult.FIRST_ORDERED_NODE_TYPE, null
        );
        el = xr.singleNodeValue;
        if (el) {
          resolvedTier = 3;
          resolvedLocator = `axes:${axe?.strategy || "unknown"}:${axeXp.substring(0, 60)}`;
          break;
        }
      } catch {}
    }
  }

  // Tier 4: Standard XPath (positional — more fragile on dynamic pages)
  if (!el && place.xpath) {
    try {
      const xr = document.evaluate(place.xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
      el = xr.singleNodeValue;
      if (el) { resolvedTier = 4; resolvedLocator = `xpath:${place.xpath.substring(0, 60)}`; }
    } catch {}
  }

  // Tier 5: ARIA label
  if (!el && place.aria) {
    el = document.querySelector(`[aria-label="${place.aria}"]`);
    if (el) { resolvedTier = 5; resolvedLocator = `aria:${place.aria}`; }
  }

  // Tier 6: Role + name
  if (!el && place.role && place.name) {
    el = document.querySelector(`[role="${place.role}"][name="${place.name}"]`);
    if (el) { resolvedTier = 6; resolvedLocator = `role:${place.role}+${place.name}`; }
  }

  // Tier 7: Inner text match
  if (!el && place.inner_text) {
    const all = document.querySelectorAll("a, button, span, div, label, li, td, th, h1, h2, h3, h4, p");
    for (const candidate of all) {
      if (candidate.innerText?.trim() === place.inner_text.trim()) {
        el = candidate;
        resolvedTier = 7;
        resolvedLocator = `text:${place.inner_text.substring(0, 40)}`;
        break;
      }
    }
  }

  // Log resolution telemetry
  if (resolvedTier) {
    console.log(`[XIOPATH] Element resolved at Tier ${resolvedTier}: ${resolvedLocator}`);
  } else {
    console.warn(`[XIOPATH] Element resolution FAILED across all 7 tiers`, place);
  }

  return el;
}

// ═══════════════════════════════════════════════════════════
// VISUAL OVERLAYS
// ═══════════════════════════════════════════════════════════

function showCaptureFlash(el) {
  el.classList.add("xp-capture-flash");
  setTimeout(() => el.classList.remove("xp-capture-flash"), 400);
}

function showExecutionProgress(current, total, step) {
  let bar = document.getElementById("xp-execution-progress");
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "xp-execution-progress";
    bar.className = "xp-execution-progress";
    document.body.appendChild(bar);
  }

  const pct = Math.round((current / total) * 100);
  const desc = step.face_value?.text || step.face_value?.description || step.action_type || "...";

  bar.innerHTML = `
    <div class="xp-ep-inner">
      <div class="xp-ep-info">
        <span class="xp-ep-brand">XIOPATH</span>
        <span class="xp-ep-step">Step ${current} of ${total}</span>
      </div>
      <div class="xp-ep-bar-track">
        <div class="xp-ep-bar-fill" style="width:${pct}%"></div>
      </div>
      <div class="xp-ep-desc">${desc}</div>
    </div>
  `;
  bar.style.display = "block";

  if (current >= total) {
    setTimeout(() => { bar.style.display = "none"; }, 2000);
  }
}

function triggerHITLOverlay(node) {
  // Remove existing
  const existing = document.getElementById("xp-hitl-overlay");
  if (existing) existing.remove();

  const overlay = document.createElement("div");
  overlay.id = "xp-hitl-overlay";
  overlay.className = "xp-hitl-overlay";
  overlay.innerHTML = `
    <div class="xp-hitl-badge">
      <div class="xp-hitl-icon">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#FFB800" stroke-width="2">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
      </div>
      <div class="xp-hitl-text">
        <strong>XIOPATH needs your help!</strong>
        <span>Please manually perform the next action to teach me.</span>
        <span class="xp-hitl-intent">Intent: ${node.intent || "unknown"}</span>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  chrome.storage.onChanged.addListener(function listener(changes) {
    if (changes.is_recording && !changes.is_recording.newValue) {
      const el = document.getElementById("xp-hitl-overlay");
      if (el) el.remove();
      chrome.storage.onChanged.removeListener(listener);
    }
  });
}

// ─── Utility ────────────────────────────────────────────────
function isXiopathElement(el) {
  if (!el) return false;
  return el.closest(".xp-inspector-badge, .xp-hitl-overlay, .xp-execution-progress, #xp-hitl-overlay, #xp-execution-progress") !== null;
}
