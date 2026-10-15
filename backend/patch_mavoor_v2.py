import os

def patch_file(filepath, replacements):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
        else:
            print(f"Warning: could not find \n{old}\nin {filepath}")
            
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

patch_file('backend/main.py', [
    (
        "AND s.branch        = '{branch}'",
        "AND {branch_cond_s}"
    ),
    (
        "AND branch = '{branch}'",
        "AND {branch_cond}"
    ),
    (
        "AND azure_sales_report.branch = '{branch}'",
        "AND {branch_cond_full}"
    ),
    (
        "AND s.branch = '{branch}'",
        "AND {branch_cond_s}"
    )
])

print("Patched main.py logic branches!")
