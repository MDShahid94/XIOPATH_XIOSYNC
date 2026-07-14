/**
 * XIOPATH — Extension Context Menus & Commands (Phase E.3)
 * ==========================================================
 * Context menu integration and keyboard command handlers for
 * the Chrome extension. Imported by background.js.
 */

const API_BASE = 'http://127.0.0.1:8000/api/v1';

// ─── Context Menu Setup ──────────────────────────────────
function setupContextMenus() {
  chrome.contextMenus.removeAll(() => {
    // Parent menu
    chrome.contextMenus.create({
      id: 'xiopath-root',
      title: 'XIOPATH',
      contexts: ['all'],
    });

    // Record action on element
    chrome.contextMenus.create({
      id: 'xiopath-record-click',
      parentId: 'xiopath-root',
      title: '🎯 Record Click on Element',
      contexts: ['all'],
    });

    // Extract text
    chrome.contextMenus.create({
      id: 'xiopath-extract-text',
      parentId: 'xiopath-root',
      title: '📋 Extract Selected Text',
      contexts: ['selection'],
    });

    // Quick screenshot
    chrome.contextMenus.create({
      id: 'xiopath-screenshot',
      parentId: 'xiopath-root',
      title: '📸 Take Page Screenshot',
      contexts: ['all'],
    });

    // Separator
    chrome.contextMenus.create({
      id: 'xiopath-sep',
      parentId: 'xiopath-root',
      type: 'separator',
      contexts: ['all'],
    });

    // Run plugin on page
    chrome.contextMenus.create({
      id: 'xiopath-run-plugin',
      parentId: 'xiopath-root',
      title: '🧩 Run Plugin on Page',
      contexts: ['all'],
    });

    // Open dashboard
    chrome.contextMenus.create({
      id: 'xiopath-dashboard',
      parentId: 'xiopath-root',
      title: '🖥️ Open Dashboard',
      contexts: ['all'],
    });
  });
}

// ─── Context Menu Handler ────────────────────────────────
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  switch (info.menuItemId) {
    case 'xiopath-record-click':
      // Send message to content script to highlight and record click target
      chrome.tabs.sendMessage(tab.id, {
        type: 'XIOPATH_RECORD_ELEMENT',
        data: { x: info.x, y: info.y },
      });
      break;

    case 'xiopath-extract-text':
      if (info.selectionText) {
        // Store extracted text
        const extracted = {
          text: info.selectionText,
          url: info.pageUrl,
          timestamp: new Date().toISOString(),
        };
        const { extractions = [] } = await chrome.storage.local.get('extractions');
        extractions.push(extracted);
        await chrome.storage.local.set({ extractions });
        // Notify sidepanel
        chrome.runtime.sendMessage({
          type: 'TEXT_EXTRACTED',
          data: extracted,
        });
      }
      break;

    case 'xiopath-screenshot':
      try {
        const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' });
        // Notify sidepanel with screenshot data
        chrome.runtime.sendMessage({
          type: 'SCREENSHOT_TAKEN',
          data: { dataUrl, url: tab.url, timestamp: new Date().toISOString() },
        });
      } catch (err) {
        console.error('[XIOPATH] Screenshot failed:', err);
      }
      break;

    case 'xiopath-run-plugin':
      // Open sidepanel to plugin selector
      chrome.sidePanel.open({ tabId: tab.id });
      setTimeout(() => {
        chrome.runtime.sendMessage({ type: 'SHOW_PLUGIN_PANEL' });
      }, 500);
      break;

    case 'xiopath-dashboard':
      chrome.tabs.create({ url: 'http://localhost:5173/dashboard' });
      break;
  }
});

// ─── Keyboard Commands ───────────────────────────────────
chrome.commands.onCommand.addListener((command, tab) => {
  switch (command) {
    case 'toggle-sidebar':
      chrome.sidePanel.open({ tabId: tab.id });
      break;
    case 'quick-record':
      chrome.tabs.sendMessage(tab.id, { type: 'XIOPATH_TOGGLE_RECORD' });
      break;
  }
});

// ─── Initialize on Install ──────────────────────────────
chrome.runtime.onInstalled.addListener(() => {
  setupContextMenus();
});

export { setupContextMenus };
