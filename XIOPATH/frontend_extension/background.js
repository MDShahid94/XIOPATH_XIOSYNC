/**
 * XIOPATH EXPLORER — Service Worker (Background)
 * =================================================
 * Manages: Side Panel behavior, recording pipeline,
 * image capture, workflow engine, and API bridge.
 */
const API_BASE = "http://127.0.0.1:8000/api/v1";

let last_node_id = null;
let llm_attempts = {};

// ─── Side Panel Setup ───────────────────────────────────────
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })
    .catch((err) => console.error("Failed to set panel behavior:", err));
});

// ─── Message Handler ────────────────────────────────────────
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {

  // ─── Recording Controls ─────────────────────
  if (request.action === "start_recording") {
    chrome.storage.local.set({
      is_recording: true,
      current_intent: request.intent,
      recorded_nodes: [],
    });
    last_node_id = null;
    sendResponse({ status: "started" });
    return false;
  }

  if (request.action === "stop_recording") {
    chrome.storage.local.set({ is_recording: false });
    last_node_id = null;
    sendResponse({ status: "stopped" });
    return false;
  }

  // ─── Record Action Event ────────────────────
  if (request.action === "record_action_event") {
    console.log("[XIOPATH] Recording action:", request.payload?.action_type);

    // Capture screenshot and crop to element bounds
    chrome.tabs.captureVisibleTab(null, { format: "png" }, (dataUrl) => {
      const payload = request.payload;
      const bbox = payload.face_value?.bounding_box;

      if (chrome.runtime.lastError || !dataUrl || !bbox) {
        console.warn("[XIOPATH] Screenshot capture failed or no bbox — recording without image");
        processRecordedAction(payload);
        sendResponse({ status: "recorded_no_image" });
        return;
      }

      // Crop using OffscreenCanvas
      try {
        const canvas = new OffscreenCanvas(bbox.width, bbox.height);
        const ctx = canvas.getContext("2d");

        fetch(dataUrl)
          .then((res) => res.blob())
          .then((blob) => createImageBitmap(blob))
          .then((img) => {
            if (bbox.effective_bg_color && bbox.effective_bg_color !== "transparent") {
              ctx.fillStyle = bbox.effective_bg_color;
              ctx.fillRect(0, 0, canvas.width, canvas.height);
            }
            ctx.drawImage(img, bbox.x, bbox.y, bbox.width, bbox.height, 0, 0, bbox.width, bbox.height);
            return canvas.convertToBlob({ type: "image/png" });
          })
          .then((blob) => {
            const reader = new FileReader();
            reader.onloadend = () => {
              payload.face_value = payload.face_value || {};
              payload.face_value.image_base64 = reader.result;
              processRecordedAction(payload);
              sendResponse({ status: "recorded_with_image" });
            };
            reader.readAsDataURL(blob);
          })
          .catch((err) => {
            console.error("[XIOPATH] Image crop failed:", err);
            processRecordedAction(payload);
            sendResponse({ status: "recorded_no_image" });
          });
      } catch (err) {
        console.error("[XIOPATH] OffscreenCanvas error:", err);
        processRecordedAction(payload);
        sendResponse({ status: "recorded_no_image" });
      }
    });

    return true; // Keep message channel open for async
  }

  // ─── Execute Workflow ───────────────────────
  if (request.action === "execute_workflow") {
    engine.executeSteps(request.steps, request.tabId, request.intent);
    sendResponse({ status: "execution_started" });
    return false;
  }

  // ─── Auto-Pilot (Legacy) ───────────────────
  if (request.action === "start_auto_pilot") {
    engine.startWorkflow(request.intent, sender.tab ? sender.tab.id : null);
    sendResponse({ status: "auto_pilot_started" });
    return false;
  }

  // ─── Auto-Pilot Failed → LLM Inference ────
  if (request.action === "auto_pilot_failed") {
    const node = request.node;
    const nodeId = node.id || `step_${Date.now()}`;
    llm_attempts[nodeId] = (llm_attempts[nodeId] || 0) + 1;

    if (llm_attempts[nodeId] > 3) {
      console.warn("[XIOPATH] LLM exhausted. Triggering HITL for:", nodeId);
      chrome.tabs.sendMessage(sender.tab.id, { action: "trigger_hitl", node });
      sendResponse({ status: "hitl_triggered" });
      return false;
    }

    console.log(`[XIOPATH] LLM inference attempt ${llm_attempts[nodeId]} for ${nodeId}`);

    // Request DOM snapshot → send to server for inference
    chrome.tabs.sendMessage(sender.tab.id, { action: "request_dom_snapshot" }, (domRes) => {
      if (!domRes?.dom) {
        chrome.tabs.sendMessage(sender.tab.id, { action: "trigger_hitl", node });
        return;
      }

      chrome.storage.local.get(["jwt_token"], async (result) => {
        if (!result.jwt_token) return;
        try {
          const res = await fetch(`${API_BASE}/agent/infer`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Authorization": `Bearer ${result.jwt_token}`,
            },
            body: JSON.stringify({
              intent: node.intent,
              dom: domRes.dom,
              previous_node_id: node.previous_node_id,
              execution_mode: node.execution_mode || "sequential",
            }),
          });

          if (res.ok) {
            const data = await res.json();
            chrome.tabs.sendMessage(sender.tab.id, {
              action: "execute_llm_action",
              action_data: data.action,
            }, (execRes) => {
              if (execRes?.status !== "success") {
                chrome.tabs.sendMessage(sender.tab.id, { action: "trigger_hitl", node });
              }
            });
          } else {
            chrome.tabs.sendMessage(sender.tab.id, { action: "trigger_hitl", node });
          }
        } catch (e) {
          console.error("[XIOPATH] LLM API error:", e);
          chrome.tabs.sendMessage(sender.tab.id, { action: "trigger_hitl", node });
        }
      });
    });

    sendResponse({ status: "inference_started" });
    return true;
  }

  return false;
});

// ─── Process & Store Recorded Action ────────────────────────
function processRecordedAction(payload) {
  chrome.storage.local.get(["jwt_token", "current_intent", "recorded_nodes"], (result) => {
    const nodes = result.recorded_nodes || [];

    payload.intent = result.current_intent || "unknown_intent";
    payload.context = {
      device_type: "desktop",
      os_name: navigator.platform || "unknown",
      browser: "chromium",
      viewport: "1280x800",
    };

    if (last_node_id) {
      payload.previous_node_id = last_node_id;
    }

    // Add to local steps
    nodes.push(payload);
    chrome.storage.local.set({ recorded_nodes: nodes });

    // Send to backend
    if (result.jwt_token) {
      fetch(`${API_BASE}/memory/record`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${result.jwt_token}`,
        },
        body: JSON.stringify(payload),
      })
        .then((res) => {
          if (!res.ok) throw new Error(`API ${res.status}`);
          return res.json();
        })
        .then((data) => {
          console.log("[XIOPATH] Action recorded:", data);
          if (data.node_id) last_node_id = data.node_id;
        })
        .catch((err) => console.warn("[XIOPATH] Backend record failed (offline mode):", err));
    }
  });
}

// ─── Workflow Engine ────────────────────────────────────────
class WorkflowEngine {
  constructor() {
    this.activeWorkflows = {};
  }

  async executeSteps(steps, tabId, intent) {
    console.log(`[XIOPATH] Executing ${steps.length} steps for "${intent}"`);

    for (let i = 0; i < steps.length; i++) {
      const step = steps[i];

      // Notify side panel of progress
      chrome.runtime.sendMessage({
        action: "execution_progress",
        current: i + 1,
        total: steps.length,
        step: step,
      }).catch(() => {}); // Panel might not be open

      // Send to content script
      try {
        await new Promise((resolve, reject) => {
          chrome.tabs.sendMessage(tabId, {
            action: "execute_node",
            node: step,
            stepIndex: i,
            totalSteps: steps.length,
          }, (response) => {
            if (chrome.runtime.lastError) {
              reject(chrome.runtime.lastError);
            } else if (response?.status === "success") {
              resolve();
            } else {
              reject(new Error("Step failed"));
            }
          });
        });

        // Wait between steps for page to settle
        await new Promise((r) => setTimeout(r, 800));
      } catch (err) {
        console.error(`[XIOPATH] Step ${i + 1} failed:`, err);
        // Trigger HITL for failed step
        chrome.tabs.sendMessage(tabId, { action: "trigger_hitl", node: step });
        break;
      }
    }

    chrome.runtime.sendMessage({
      action: "execution_complete",
      total: steps.length,
    }).catch(() => {});
  }

  async startWorkflow(intent, dashboardTabId) {
    chrome.storage.local.get(["jwt_token"], async (result) => {
      if (!result.jwt_token) return console.error("[XIOPATH] Not authenticated");

      try {
        const res = await fetch(`${API_BASE}/memory/search?intent=${encodeURIComponent(intent)}`, {
          headers: { "Authorization": `Bearer ${result.jwt_token}` },
        });
        const data = await res.json();
        if (data.data?.length > 0) {
          const rootNode = data.data[0];
          const url = rootNode.domain.startsWith("http") ? rootNode.domain : "https://" + rootNode.domain;
          chrome.tabs.create({ url, active: true }, (newTab) => {
            this.activeWorkflows[newTab.id] = { node: rootNode, status: "loading" };
          });
        }
      } catch (err) {
        console.error("[XIOPATH] Workflow fetch error:", err);
      }
    });
  }

  sendToContentScript(tabId, node) {
    chrome.tabs.sendMessage(tabId, { action: "execute_node", node }, (response) => {
      if (chrome.runtime.lastError) {
        setTimeout(() => this.sendToContentScript(tabId, node), 500);
      } else if (response?.status === "success" && node.next_nodes?.length > 0) {
        const nextId = typeof node.next_nodes[0] === "string" ? node.next_nodes[0] : node.next_nodes[0].id;
        console.log("[XIOPATH] Proceeding to next node:", nextId);
      }
    });
  }
}

const engine = new WorkflowEngine();

// Tab update listener for workflow engine
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "complete" && engine.activeWorkflows[tabId]) {
    const ws = engine.activeWorkflows[tabId];
    if (ws.status === "loading") {
      ws.status = "ready";
      engine.sendToContentScript(tabId, ws.node);
    }
  }
});
