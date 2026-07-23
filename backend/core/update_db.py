import re

with open('/Users/nito/Documents/GitHub/com_brasper_ia/backend/core/db.py', 'r') as f:
    c = f.read()

# 1. Schemas: Remove `tenants` table
c = re.sub(r'CREATE TABLE IF NOT EXISTS tenants \([\s\S]*?updated_at TIMESTAMPTZ NOT NULL\n\);\n*', '', c)
c = re.sub(r'CREATE TABLE IF NOT EXISTS tenants \([\s\S]*?updated_at TEXT NOT NULL\n\);\n*', '', c)

# 2. Schemas: Remove tenant_id from tables
c = re.sub(r'^\s*tenant_id TEXT NOT NULL,\n', '', c, flags=re.MULTILINE)
c = re.sub(r'^\s*tenant_id TEXT,\n', '', c, flags=re.MULTILINE)

# Primary Keys & Unique constraints
c = re.sub(r'PRIMARY KEY \(tenant_id, id\)', 'PRIMARY KEY (id)', c)
c = re.sub(r'UNIQUE \(tenant_id, (channel|connector_key)\)', r'UNIQUE (\1)', c)

# Indexes - remove tenant_id
# idx_conv_tenant -> idx_conv_updated, remove tenant_id
c = c.replace('idx_conv_tenant ON conversations(tenant_id, updated_at DESC)', 'idx_conv_updated ON conversations(updated_at DESC)')
c = c.replace('idx_msg_conv ON messages(tenant_id, conversation_id, id)', 'idx_msg_conv ON messages(conversation_id, id)')
c = c.replace('idx_usage_tenant ON usage_events(tenant_id, created_at DESC)', 'idx_usage_created ON usage_events(created_at DESC)')
c = c.replace('idx_audit_tenant ON audit_events(tenant_id, created_at DESC)', 'idx_audit_created ON audit_events(created_at DESC)')
c = c.replace('idx_appointments_tenant ON appointments(tenant_id, scheduled_for DESC)', 'idx_appointments_scheduled ON appointments(scheduled_for DESC)')
c = c.replace('idx_secret_rotations_tenant ON secret_rotations(tenant_id, rotated_at DESC)', 'idx_secret_rotations_rotated ON secret_rotations(rotated_at DESC)')

# ID in conversations needs to be PRIMARY KEY now
c = c.replace('id TEXT NOT NULL,', 'id TEXT PRIMARY KEY,')

# 3 & 4. Function Signatures & Queries
c = re.sub(r'tenant_id:\s*str(?:\s*\|\s*None)?\s*,\s*', '', c)
c = re.sub(r'tenant_id:\s*str(?:\s*\|\s*None)?\s*\)\s*->', ') ->', c)

# _usage_row
c = c.replace('q = ("SELECT tenant_id, COUNT(*) AS calls', 'q = ("SELECT COUNT(*) AS calls')
c = c.replace('if tenant_id:\n        q += " WHERE tenant_id=?"\n        args = (tenant_id,)', '')
c = c.replace('q += " GROUP BY tenant_id"', '')

# replace usage_summary signature which might have default None
c = re.sub(r'def usage_summary\(\)\s*->\s*list\[dict\]:', 'def usage_summary() -> dict:', c)
# actually, let\'s manually write out replacements for python queries

with open('/Users/nito/Documents/GitHub/com_brasper_ia/backend/core/update_db.py', 'w') as out:
    out.write(c)
