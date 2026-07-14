-- XIOPATH Phantom Infrastructure — D1 Schema Migration
-- Vault tables for the Cloudflare Workers Control Plane
-- Educational purpose only

-- ════════════════════════════════════════════════
-- Phantom Identity Vault (encrypted records)
-- ════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS phantom_identities (
    id              TEXT PRIMARY KEY,
    ontology_agent_id TEXT,                  -- FK → mesh_nodes.id (ontology agent for this phantom)
    encrypted_data  TEXT NOT NULL,          -- AES-256-GCM encrypted JSON blob
    state           TEXT NOT NULL DEFAULT 'provisioning',  -- provisioning/aging/active/locked/dead/revoked
    member_donor_id TEXT,                   -- Who donated compute for this phantom
    trust_score     REAL DEFAULT 0.5,       -- 0.0-1.0 trust score
    mesh_node_id    TEXT,                   -- Assigned mesh node ID
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at      TEXT,
    revoke_reason   TEXT
);

CREATE INDEX IF NOT EXISTS idx_phantom_state ON phantom_identities(state);
CREATE INDEX IF NOT EXISTS idx_phantom_donor ON phantom_identities(member_donor_id);

-- ════════════════════════════════════════════════
-- Browser Profiles (encrypted binary data)
-- ════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS browser_profiles (
    phantom_id        TEXT PRIMARY KEY REFERENCES phantom_identities(id),
    encrypted_profile BLOB NOT NULL,       -- AES-256-GCM encrypted browser profile
    fingerprint_hash  TEXT,                -- SHA-256 of the fingerprint for dedup detection
    profile_state     TEXT DEFAULT 'new',  -- new/warming/aged/active/locked
    age_days          INTEGER DEFAULT 0,
    cookies_count     INTEGER DEFAULT 0,
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ════════════════════════════════════════════════
-- Vault Audit Log
-- ════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS vault_log (
    id          TEXT PRIMARY KEY,
    phantom_id  TEXT NOT NULL,
    action      TEXT NOT NULL,             -- store/retrieve/update/revoke/export
    details     TEXT,                       -- JSON details of the action
    ip_address  TEXT,
    timestamp   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_vault_log_phantom ON vault_log(phantom_id);
CREATE INDEX IF NOT EXISTS idx_vault_log_action ON vault_log(action);

-- ════════════════════════════════════════════════
-- Harvested Resources Registry
-- ════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS harvested_resources (
    id             TEXT PRIMARY KEY,
    phantom_id     TEXT NOT NULL REFERENCES phantom_identities(id),
    ontology_agent_id TEXT,                  -- FK → mesh_nodes.id (child agent for this resource)
    service        TEXT NOT NULL,           -- cloudflare/google/kaggle/github
    resource_type  TEXT NOT NULL,           -- worker/d1/r2/kv/gpu/actions
    resource_id    TEXT NOT NULL,           -- Service-specific resource ID
    capabilities   TEXT,                    -- JSON array of capabilities
    limits         TEXT,                    -- JSON dict of free-tier limits
    state          TEXT DEFAULT 'pending',  -- pending/deploying/active/suspended/dead
    endpoint       TEXT,                    -- URL/endpoint
    metadata       TEXT,                    -- JSON metadata
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    last_health    TEXT                     -- Last health check timestamp
);

CREATE INDEX IF NOT EXISTS idx_resource_phantom ON harvested_resources(phantom_id);
CREATE INDEX IF NOT EXISTS idx_resource_type ON harvested_resources(resource_type);
CREATE INDEX IF NOT EXISTS idx_resource_state ON harvested_resources(state);

-- ════════════════════════════════════════════════
-- Provisioning Jobs
-- ════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS provisioning_jobs (
    id              TEXT PRIMARY KEY,
    phantom_id      TEXT REFERENCES phantom_identities(id),
    ontology_operation_id TEXT,              -- Links to operation record chain in event_log
    member_donor_id TEXT NOT NULL,
    status          TEXT DEFAULT 'queued',   -- queued/running/verified/completed/failed
    current_phase   TEXT NOT NULL DEFAULT 'identity_forge',
    config          TEXT,                    -- JSON config (locale, etc.)
    phases_done     TEXT,                   -- JSON array of completed phases
    error           TEXT,
    verification_pending INTEGER DEFAULT 0,
    verification_data    TEXT,              -- JSON verification data for member
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT,
    completed_at    TEXT
);

-- ════════════════════════════════════════════════
-- Migration Schedules
-- ════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS migration_steps (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    phantom_id    TEXT NOT NULL REFERENCES phantom_identities(id),
    step_number   INTEGER NOT NULL,
    day           INTEGER NOT NULL,
    hour          INTEGER NOT NULL,
    proxy_country TEXT,
    proxy_type    TEXT,
    description   TEXT,
    activity      TEXT,                     -- JSON array of activities
    completed     INTEGER DEFAULT 0,
    completed_at  TEXT,
    error         TEXT
);

CREATE INDEX IF NOT EXISTS idx_migration_phantom ON migration_steps(phantom_id);

-- ════════════════════════════════════════════════
-- Aging Progress
-- ════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aging_progress (
    phantom_id     TEXT NOT NULL REFERENCES phantom_identities(id),
    day            INTEGER NOT NULL,
    tasks_total    INTEGER DEFAULT 0,
    tasks_done     INTEGER DEFAULT 0,
    tasks_failed   INTEGER DEFAULT 0,
    executed_at    TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (phantom_id, day)
);

-- ════════════════════════════════════════════════
-- Fleet Health Snapshots
-- ════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS health_checks (
    id               TEXT PRIMARY KEY,
    phantom_id       TEXT NOT NULL REFERENCES phantom_identities(id),
    overall_status   TEXT NOT NULL,          -- healthy/degraded/locked/dead
    google_alive     INTEGER DEFAULT 0,
    cloudflare_alive INTEGER DEFAULT 0,
    github_alive     INTEGER DEFAULT 0,
    worker_alive     INTEGER DEFAULT 0,
    issues           TEXT,                   -- JSON array of issues
    checked_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_health_phantom ON health_checks(phantom_id);
CREATE INDEX IF NOT EXISTS idx_health_status ON health_checks(overall_status);
