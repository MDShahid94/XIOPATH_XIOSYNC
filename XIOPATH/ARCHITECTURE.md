# XIOPATH v5.0 — Architecture Manifesto

XIOPATH is a distributed, intelligent, and autonomous agentic workflow orchestration platform. 
Version 5.0 marks the transition from a monolithic local application to a horizontally scalable, multi-tenant Swarm mesh.

## 1. The Universal Ontology
At the core of XIOPATH is the Universal Agent Ontology, managed by the `TypeRegistry` (Phase 1). 
Instead of hardcoding what an "Agent" or a "Tool" is, all entities are defined dynamically in the database.
- **Actors**: `human`, `ai`, `compute`
- **Capabilities**: Dynamically registered JSON schemas defining inputs/outputs.
- **Edges & Operations**: Traceable, version-controlled relationships mapping the exact execution history of the system.

## 2. The Execution Engine (Phase 6)
Workflows are defined as Directed Acyclic Graphs (DAGs) and managed by the `WorkflowManager`. 
When a workflow executes:
1. The **Policy Enforcer** intercepts the request.
2. Background tasks process the nodes sequentially (or via delegation).
3. Real-time telemetry is streamed to the React Super-Dashboard via **WebSockets**.

## 3. The Phantom Abstraction (Phase 7)
All highly-opinionated or potentially restricted behaviors (like Residential IP harvesting, browser identity forgery, and synthetic profile generation) are completely decoupled from the core orchestration engine. They operate as isolated **Plugins**.
The **Policy Enforcer** ensures that only authorized tenants with specific clearances can execute Phantom workflows in sandboxed environments.

## 4. The Decentralized Swarm Mesh (Phase S)
XIOPATH offloads heavy compute (LLM inference, headless browsers) to external, volunteer edge nodes.
To maintain integrity in a zero-trust environment, we use the **Trust & Reputation Ledger**.
- Edge nodes are promoted across 5 tiers: `UNTRUSTED` ➡️ `VERIFIED` ➡️ `TRUSTED` ➡️ `CORE` ➡️ `ADMIN`.
- Nodes are promoted automatically upon submitting successful execution proofs and demoted upon failure.
- Untrusted nodes are barred from modifying global state.

## 5. Advanced Intelligence (Phase X)
The Swarm operates as a unified brain through the **Universal Memory Graph**.
- **CRDT Memory Merge**: Edge nodes construct localized memory graphs (Observations, Intents, Outcomes) and merge them into the central Control Plane using Last-Write-Wins (LWW) CRDT logic to prevent collisions.
- **DLQ Reinforcement Learning**: When an execution fails, it is sent to the Dead Letter Queue. The **Self-Learning Engine** autonomously retrieves the execution trace, queries the central LLM for a diagnosis, and dynamically proposes a corrected workflow spec, allowing the platform to literally learn from its mistakes.
