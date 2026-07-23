import os
import re
from pathlib import Path

BASE_DIR = Path('/Users/nito/Documents/GitHub/com_brasper_ia/backend')

def replace_in_file(path, replacements):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = content
    for pattern, repl in replacements:
        new_content = re.sub(pattern, repl, new_content)
        
    if content != new_content:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {path}")

def main():
    # 1. Update DB file
    db_path = BASE_DIR / 'core' / 'db.py'
    db_replacements = [
        # Remove tenant_id from schema
        (r'tenant_id TEXT( NOT NULL)?,\n\s*', r''),
        (r'tenant_id TEXT,\n\s*', r''),
        (r'tenant_id TEXT NOT NULL,\n\s*', r''),
        (r'PRIMARY KEY \(tenant_id, id\)', r'PRIMARY KEY (id)'),
        (r'CREATE INDEX IF NOT EXISTS idx_conv_tenant ON conversations\(tenant_id, updated_at DESC\);', r'CREATE INDEX IF NOT EXISTS idx_conv_updated ON conversations(updated_at DESC);'),
        (r'CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages\(tenant_id, conversation_id, id\);', r'CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, id);'),
        (r'CREATE INDEX IF NOT EXISTS idx_usage_tenant ON usage_events\(tenant_id, created_at DESC\);', r'CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_events(created_at DESC);'),
        (r'CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_events\(tenant_id, created_at DESC\);', r'CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at DESC);'),
        (r'CREATE INDEX IF NOT EXISTS idx_appointments_tenant ON appointments\(tenant_id, scheduled_for DESC\);', r'CREATE INDEX IF NOT EXISTS idx_appointments_scheduled ON appointments(scheduled_for DESC);'),
        (r'CREATE INDEX IF NOT EXISTS idx_secret_rotations_tenant ON secret_rotations\(tenant_id, rotated_at DESC\);', r'CREATE INDEX IF NOT EXISTS idx_secret_rotations_rotated ON secret_rotations(rotated_at DESC);'),
        (r'UNIQUE \(tenant_id, channel\)', r'UNIQUE (channel)'),
        (r'UNIQUE \(tenant_id, connector_key\)', r'UNIQUE (connector_key)'),
        
        # Remove tenants table
        (r'CREATE TABLE IF NOT EXISTS tenants \([\s\S]*?\);\n', r''),
        
        # Function parameters
        (r'tenant_id: str( \| None)?(, )?', r''),
        (r'tenant_id: str( \| None)?', r''),
        (r'tenant_id(, )?', r''),
        
        # SQL Queries
        (r' AND tenant_id=\?', r''),
        (r' AND c\.tenant_id=\?', r''),
        (r' WHERE tenant_id=\?', r''),
        (r' WHERE c\.tenant_id=\?', r''),
        (r' AND m\.tenant_id=c\.tenant_id', r''),
        (r'tenant_id, ', r''),
        (r'c\.tenant_id=?', r'1=1'),
        (r'\?,tenant_id', r''),
        (r'\, tenant_id', r''),
        
        # Special replacements
        (r'def get_or_create_conversation\(user_ref: str, channel: str,\s*conversation_id: str \| None = None\) -> str:', 
         r'def get_or_create_conversation(user_ref: str, channel: str, conversation_id: str | None = None) -> str:'),
         
        (r'tenant_id=\?, ', r''),
        (r'\(tenant_id, ', r'('),
        (r'tenant_id, \?', r''),
        (r'tenant_id, \)', r')'),
    ]
    replace_in_file(db_path, db_replacements)

    # We will refine db_path manually if needed, but let's do a broad replacement on all python files
    for root, _, files in os.walk(BASE_DIR):
        for f in files:
            if not f.endswith('.py'): continue
            path = Path(root) / f
            
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            new_content = content
            
            # Remove tenant_id from API paths
            new_content = re.sub(r'/api/\{tenant_id\}/', r'/api/', new_content)
            new_content = re.sub(r'tenant_id: str, ', r'', new_content)
            
            # Remove tenant parameter
            new_content = re.sub(r'tenant: dict, ', r'', new_content)
            new_content = re.sub(r'tenant, ', r'', new_content)
            
            # Update tenants reference
            new_content = re.sub(r'T\.get_tenant\(tenant_id\)', r'T.get_config()', new_content)
            new_content = re.sub(r'T\.all_tenants\(\)', r'{"brasper": T.get_config()}', new_content)
            new_content = re.sub(r'_tenant_or_404\(.*?\)', r'T.get_config()', new_content)
            
            if content != new_content:
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                print(f"Updated {path}")

if __name__ == '__main__':
    main()
