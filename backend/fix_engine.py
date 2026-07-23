import os, re

def fix_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    original = content

    # Strip tenant, from engine.handle_message(
    # e.g. engine.handle_message(user_ref... -> engine.handle_message(user_ref...
    pattern = r'(engine\.handle_message\(\s*)(?:tenant|t|tenant_cfg|clinica)\s*,\s*'
    content = re.sub(pattern, r'\1', content)

    if content != original:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Fixed engine calls in {filepath}")

for root, _, files in os.walk('backend'):
    if '.venv' in root or '__pycache__' in root:
        continue
    for file in files:
        if file.endswith('.py'):
            fix_file(os.path.join(root, file))
