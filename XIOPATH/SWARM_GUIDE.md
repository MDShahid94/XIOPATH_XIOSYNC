# Joining the XIOPATH Swarm

Welcome to the XIOPATH Swarm Mesh! By connecting your local machine or Google Colab instance, you are volunteering compute power (LLM Inference, Browser Automation) to help the decentralized XIOPATH network execute highly complex, parallelized workflows.

## Prerequisites
- Python 3.10+
- Chrome/Chromium installed (for Browser Automation capabilities)

## 1. Getting your Authentication Token
Before you can join the swarm, you need an authorization token.
1. Log in to the **XIOPATH Super-Dashboard**.
2. Navigate to **Resources > Actors**.
3. Click **Provision New Node**.
4. The dashboard will provide a secure JSON Web Token (JWT). Keep this safe.

## 2. Joining the Swarm via CLI
If you have the source code downloaded, joining is as simple as using the Antigravity (agy) CLI.

Run the following command from your terminal:
```bash
./agy swarm join \
    --url "wss://api.xiopath.com/api/ws/worker" \
    --token "eyJhbGciOiJIUzI1NiIsIn..." \
    --worker-id "my_home_desktop" \
    --capabilities web_browse llm_inference
```

### What happens next?
1. **Registration:** Your node connects to the Control Plane and registers itself dynamically in the Type Registry as a `colab_runtime` compute actor.
2. **Execution:** The central `WorkflowManager` assigns you task segments from the global DAG that match your declared `--capabilities`.
3. **CRDT Sync:** As you execute tasks, your local node generates a Memory Graph. It periodically syncs this graph to the master plane using conflict-free (CRDT) merge algorithms.

## 3. The Trust Ledger
In a decentralized network, security is paramount. When you first join the Swarm, your node starts at **Tier 0 (UNTRUSTED)**.
- **Untrusted** nodes are given low-risk, sandboxed workflows.
- As you consistently return successful execution proofs, the central **Trust Ledger** automatically promotes you to **Tier 1 (VERIFIED)** and **Tier 2 (TRUSTED)**.
- Higher tiers receive high-priority, high-clearance tasks.
- **Warning:** Failing tasks consistently or returning malformed data will result in a demotion back to Tier 0, and the **Policy Enforcer** will block your node from participating in core network functions.

Happy Swarming! 🐝
