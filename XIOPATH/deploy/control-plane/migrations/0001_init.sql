-- ==================================================
-- XIOPATH Control Plane — D1 Schema (Migration 0001)
-- ==================================================
-- Ported from SQLite schema in core/database.py
-- Adapted for Cloudflare D1 (serverless SQLite)
-- ==================================================

-- ── Node Registry ───────────────────────────────
-- Every mesh participant (CF account, Colab, Kaggle, personal machine)
CREATE TABLE IF NOT EXISTS mesh_nodes (
    id TEXT PRIMARY KEY,                    -- UUIDv7
    agent_type TEXT NOT NULL DEFAULT 'compute',
    agent_subtype TEXT NOT NULL,            -- edge_node, gpu_node, data_node, storage_node, dev_node, browser_node
    alias TEXT,                             -- Human-readable name
    owner_id TEXT NOT NULL,                 -- User who donated this node
    
    -- Capabilities (what this node can do)
    capabilities TEXT NOT NULL DEFAULT '[]', -- JSON array of capability declarations
    
    -- Connection details
    endpoint_url TEXT,                      -- Public URL (workers.dev or custom domain)
    ws_connected INTEGER NOT NULL DEFAULT 0,
    last_heartbeat TEXT,
    last_task_at TEXT,
    
    -- Resource contribution
    contributed_storage_gb REAL DEFAULT 0,
    contributed_compute_requests INTEGER DEFAULT 0,
    consumed_storage_gb REAL DEFAULT 0,
    consumed_compute_requests INTEGER DEFAULT 0,
    
    -- Trust & reputation
    trust_score REAL NOT NULL DEFAULT 0.0,
    trust_tier TEXT NOT NULL DEFAULT 'newcomer', -- newcomer, contributor, trusted, core, admin
    uptime_ratio REAL DEFAULT 0.0,
    task_success_count INTEGER DEFAULT 0,
    task_failure_count INTEGER DEFAULT 0,
    joined_at TEXT NOT NULL,
    
    -- State
    state TEXT NOT NULL DEFAULT 'initializing', -- initializing, active, suspended, terminated
    region TEXT,                             -- Geographic region hint
    metadata TEXT DEFAULT '{}',              -- JSON metadata
    
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mesh_nodes_state ON mesh_nodes(state);
CREATE INDEX IF NOT EXISTS idx_mesh_nodes_subtype ON mesh_nodes(agent_subtype);
CREATE INDEX IF NOT EXISTS idx_mesh_nodes_trust ON mesh_nodes(trust_tier, trust_score DESC);
CREATE INDEX IF NOT EXISTS idx_mesh_nodes_owner ON mesh_nodes(owner_id);

-- ── Users ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,                    -- UUIDv7
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',    -- admin, creator, member
    
    -- Mesh contribution stats
    nodes_contributed INTEGER DEFAULT 0,
    total_tasks_completed INTEGER DEFAULT 0,
    member_since TEXT NOT NULL DEFAULT (datetime('now')),
    
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Task Queue ──────────────────────────────────
CREATE TABLE IF NOT EXISTS task_queue (
    id TEXT PRIMARY KEY,                    -- UUIDv7
    task_type TEXT NOT NULL,                -- inference, browser, data, storage, embed
    payload TEXT NOT NULL,                  -- JSON task definition
    
    -- Routing
    required_capability TEXT NOT NULL,       -- What capability the node needs
    min_trust_tier TEXT DEFAULT 'newcomer',
    preferred_region TEXT,
    
    -- Assignment
    assigned_node_id TEXT,
    assigned_at TEXT,
    
    -- Result
    result TEXT,                            -- JSON result
    error TEXT,
    
    -- Lifecycle
    state TEXT NOT NULL DEFAULT 'pending',  -- pending, assigned, running, completed, failed, dead
    priority INTEGER NOT NULL DEFAULT 5,    -- 1 (highest) - 10 (lowest)
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    timeout_ms INTEGER DEFAULT 90000,
    
    submitted_by TEXT NOT NULL,             -- User who submitted
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    
    FOREIGN KEY (assigned_node_id) REFERENCES mesh_nodes(id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_state ON task_queue(state, priority);
CREATE INDEX IF NOT EXISTS idx_tasks_node ON task_queue(assigned_node_id);
CREATE INDEX IF NOT EXISTS idx_tasks_capability ON task_queue(required_capability, state);

-- ── Data Locations (Storage Federation) ─────────
CREATE TABLE IF NOT EXISTS data_locations (
    id TEXT PRIMARY KEY,                    -- UUIDv7
    data_type TEXT NOT NULL,                -- memory_node, profile, bundle, plugin, asset
    data_id TEXT NOT NULL,                  -- ID of the stored object
    
    -- Where it lives
    node_id TEXT NOT NULL,                  -- Which mesh node stores this
    storage_type TEXT NOT NULL,             -- r2, d1, drive, local
    storage_url TEXT NOT NULL,              -- Public URL to fetch
    
    -- Metadata
    size_bytes INTEGER DEFAULT 0,
    checksum TEXT,
    encrypted INTEGER DEFAULT 0,
    
    -- Replication
    replica_of TEXT,                        -- ID of the primary copy (NULL if this IS primary)
    replica_count INTEGER DEFAULT 1,        -- How many copies exist total
    
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT,
    
    FOREIGN KEY (node_id) REFERENCES mesh_nodes(id)
);

CREATE INDEX IF NOT EXISTS idx_data_type_id ON data_locations(data_type, data_id);
CREATE INDEX IF NOT EXISTS idx_data_node ON data_locations(node_id);

-- ── Memory Nodes (Global Tier) ──────────────────
-- Only server_secondary and server_primary memory lives here.
-- Client-tier memory stays on member nodes.
CREATE TABLE IF NOT EXISTS memory_nodes (
    id TEXT PRIMARY KEY,
    tier TEXT NOT NULL,                     -- server_secondary, server_primary
    domain TEXT NOT NULL,
    intent TEXT NOT NULL,
    
    -- Context
    device_type TEXT DEFAULT '',
    os_name TEXT DEFAULT '',
    browser TEXT DEFAULT '',
    viewport_width INTEGER DEFAULT 0,
    viewport_height INTEGER DEFAULT 0,
    
    -- Values
    visibility TEXT DEFAULT 'public',
    face_value TEXT DEFAULT '{}',           -- JSON
    place_value TEXT DEFAULT '{}',          -- JSON
    action_type TEXT DEFAULT '',
    action_params TEXT DEFAULT '{}',        -- JSON
    
    -- Graph
    previous_intent TEXT,
    next_nodes TEXT DEFAULT '[]',           -- JSON array
    
    -- Scoring
    promotions INTEGER DEFAULT 0,
    bayesian_score REAL DEFAULT 0.5,
    ema_score REAL DEFAULT 0.5,
    total_vote_weight REAL DEFAULT 0.0,
    ref_count INTEGER DEFAULT 0,
    
    -- Provenance
    client_id TEXT,
    owner_node_id TEXT,                     -- Which mesh node contributed this
    lookup_key TEXT,
    status TEXT DEFAULT 'active',
    
    last_used TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_memory_domain ON memory_nodes(domain, intent);
CREATE INDEX IF NOT EXISTS idx_memory_tier ON memory_nodes(tier, status);
CREATE INDEX IF NOT EXISTS idx_memory_score ON memory_nodes(bayesian_score DESC);
CREATE INDEX IF NOT EXISTS idx_memory_lookup ON memory_nodes(lookup_key);

-- ── Client Votes ────────────────────────────────
CREATE TABLE IF NOT EXISTS client_votes (
    node_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    voted_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (node_id, client_id)
);

-- ── Vote Counts (Anti-spam) ─────────────────────
CREATE TABLE IF NOT EXISTS client_vote_counts (
    client_id TEXT PRIMARY KEY,
    vote_count INTEGER DEFAULT 0,
    last_voted TEXT
);

-- ── Event Log (Append-only Audit Ledger) ────────
CREATE TABLE IF NOT EXISTS event_log (
    id TEXT PRIMARY KEY,                    -- UUIDv7
    node_id TEXT,
    agent_id TEXT,
    event_type TEXT NOT NULL,
    severity TEXT DEFAULT 'info',           -- debug, info, warning, error, critical
    summary TEXT,
    payload TEXT DEFAULT '{}',              -- JSON
    correlation_id TEXT,
    source_ip TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_node ON event_log(node_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_type ON event_log(event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_correlation ON event_log(correlation_id);

-- ── Capability Grants ───────────────────────────
CREATE TABLE IF NOT EXISTS capability_grants (
    id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,                  -- Mesh node receiving the capability
    capability TEXT NOT NULL,               -- What capability is granted
    scope TEXT DEFAULT 'execute_only',      -- full, read_only, execute_only, limited
    constraints TEXT DEFAULT '{}',          -- JSON (rate limits, time windows, etc.)
    granted_by TEXT NOT NULL,               -- Admin who granted
    expires_at TEXT,
    state TEXT DEFAULT 'active',            -- active, revoked, expired
    revoked_at TEXT,
    revoked_by TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    FOREIGN KEY (node_id) REFERENCES mesh_nodes(id)
);

CREATE INDEX IF NOT EXISTS idx_grants_node ON capability_grants(node_id, state);

-- ── Marketplace Listings ────────────────────────
CREATE TABLE IF NOT EXISTS marketplace_listings (
    id TEXT PRIMARY KEY,
    environment_id TEXT UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT,
    tags TEXT DEFAULT '[]',                 -- JSON array
    creator_id TEXT NOT NULL,
    install_count INTEGER DEFAULT 0,
    rating_sum REAL DEFAULT 0,
    review_count INTEGER DEFAULT 0,
    published_at TEXT,
    updated_at TEXT,
    state TEXT DEFAULT 'draft'
);

-- ── Marketplace Reviews ─────────────────────────
CREATE TABLE IF NOT EXISTS marketplace_reviews (
    id TEXT PRIMARY KEY,
    listing_id TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    rating INTEGER NOT NULL,
    comment TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(listing_id, reviewer_id),
    FOREIGN KEY (listing_id) REFERENCES marketplace_listings(id)
);
