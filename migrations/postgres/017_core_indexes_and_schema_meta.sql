-- AtlasBahamas PostgreSQL migration 017
-- Adds missing operational indexes and schema version tracking metadata.

BEGIN;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS') || '+00:00')
);

CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_sessions_user_expires ON sessions(user_id, expires_at);
CREATE INDEX IF NOT EXISTS idx_sessions_ip_hash ON sessions(ip_hash);
CREATE INDEX IF NOT EXISTS idx_properties_owner ON properties(owner_account, id);
CREATE INDEX IF NOT EXISTS idx_units_property ON units(property_id, id);
CREATE INDEX IF NOT EXISTS idx_leases_tenant_active ON tenant_leases(tenant_account, is_active, id);
CREATE INDEX IF NOT EXISTS idx_leases_property_active ON tenant_leases(property_id, is_active, id);
CREATE INDEX IF NOT EXISTS idx_maintenance_status_created ON maintenance_requests(status, created_at, id);
CREATE INDEX IF NOT EXISTS idx_password_resets_user_expires ON password_resets(user_id, expires_at, used);
CREATE INDEX IF NOT EXISTS idx_listing_requests_prop_status ON listing_requests(property_id, status, id);

ALTER TABLE tenant_property_invites ADD COLUMN IF NOT EXISTS expires_at TEXT;
ALTER TABLE tenant_property_invites ADD COLUMN IF NOT EXISTS revoke_reason TEXT;
CREATE INDEX IF NOT EXISTS idx_tp_invites_pending_expiry ON tenant_property_invites(status, expires_at, created_at);

INSERT INTO schema_meta(key, value, updated_at)
VALUES ('schema_version', '17', (to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS') || '+00:00'))
ON CONFLICT(key) DO UPDATE SET
    value = EXCLUDED.value,
    updated_at = EXCLUDED.updated_at;

COMMIT;


