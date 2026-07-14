const fs = require('fs');
const { JSDOM } = require('jsdom');
const path = require('path');

// Read the content.js file
const contentJsCode = fs.readFileSync(path.join(__dirname, 'content.js'), 'utf8');

// Mock HTML
const html = `
<!DOCTYPE html>
<html>
<head>
    <style>body { color: red; }</style>
    <script>console.log('test');</script>
</head>
<body>
    <button id="login-btn">Login</button>
    <input type="email" id="email-input" />
</body>
</html>
`;

// Setup JSDOM
const dom = new JSDOM(html, { runScripts: "dangerously" });
const window = dom.window;
const document = window.document;

// Mock Chrome API
const messageListeners = [];
window.chrome = {
    storage: {
        local: {
            get: (keys, callback) => callback({ is_recording: false }),
            set: (data) => {}
        },
        onChanged: {
            addListener: () => {}
        }
    },
    runtime: {
        onMessage: {
            addListener: (listener) => {
                messageListeners.push(listener);
            }
        },
        sendMessage: (msg, callback) => {
            window.lastMessageSent = msg;
            if (callback) callback();
        }
    }
};

// Execute content.js within the JSDOM context
// We wrap it in a function to avoid polluting the global Node scope, but pass in the mock window/document
const script = document.createElement("script");
script.textContent = `
    const chrome = window.chrome;
    ${contentJsCode}
`;
document.body.appendChild(script);

// Utility to dispatch message to content.js
function sendMessageToContentScript(msg) {
    return new Promise((resolve) => {
        messageListeners.forEach(listener => {
            listener(msg, {}, (response) => {
                resolve(response);
            });
        });
    });
}

async function runTests() {
    console.log("Starting Rigorous Extension Logic Tests...\n");
    let passed = 0;
    let failed = 0;

    function assert(condition, message) {
        if (condition) {
            console.log(`✅ PASS: ${message}`);
            passed++;
        } else {
            console.error(`❌ FAIL: ${message}`);
            failed++;
        }
    }

    try {
        // Test 1: request_dom_snapshot should strip scripts and styles
        const domRes = await sendMessageToContentScript({ action: "request_dom_snapshot" });
        assert(domRes.status === "success", "DOM Snapshot returned success status");
        assert(!domRes.dom.includes("<style>"), "DOM Snapshot successfully stripped <style> tags");
        assert(!domRes.dom.includes("<script>"), "DOM Snapshot successfully stripped <script> tags");
        assert(domRes.dom.includes('id="login-btn"'), "DOM Snapshot retained visible elements");

        // Test 2: execute_node with BAD selector triggers fallback
        window.lastMessageSent = null;
        const badNode = {
            id: "node-1",
            place_value: { selector: "#does-not-exist" }
        };
        const execBadRes = await sendMessageToContentScript({ action: "execute_node", node: badNode });
        assert(execBadRes.status === "failed", "execute_node fails gracefully on bad selector");
        assert(window.lastMessageSent && window.lastMessageSent.action === "auto_pilot_failed", "Fired auto_pilot_failed fallback message to background script");

        // Test 3: execute_llm_action correctly executes dynamic inferences
        let clicked = false;
        document.getElementById('login-btn').addEventListener('click', () => { clicked = true; });
        
        const llmAction = { action: "click", selector: "#login-btn" };
        const llmRes = await sendMessageToContentScript({ action: "execute_llm_action", action_data: llmAction });
        assert(llmRes.status === "success", "execute_llm_action returned success");
        assert(clicked === true, "execute_llm_action successfully triggered click event on the DOM element");

        // Test 4: HITL Overlay injection
        await sendMessageToContentScript({ action: "trigger_hitl", node: { id: "node-1", intent: "Click login" } });
        const hitlOverlay = document.getElementById("antigravity-hitl-overlay");
        assert(hitlOverlay !== null, "HITL Overlay successfully injected into DOM upon exhaustion");
        assert(hitlOverlay.innerHTML.includes("Agent Stuck"), "HITL Overlay displays correct warning text");

    } catch (e) {
        console.error("Test execution threw error:", e);
        failed++;
    }

    console.log(`\nTest Summary: ${passed} Passed, ${failed} Failed.`);
    if (failed > 0) process.exit(1);
}

runTests();
