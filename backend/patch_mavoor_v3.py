import os

with open('backend/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('{branch_cond_pos}', '{branch_cond}')
content = content.replace("branch = '{branch}'", "{branch_cond}")
content = content.replace("azure_sales_report.branch = '{branch}'", "{branch_cond_full}")
content = content.replace("s.branch = '{branch}'", "{branch_cond_s}")

# Clean up any double replacements if they occurred (like {{branch_cond}})
content = content.replace("{{branch_cond}}", "{branch_cond}")
content = content.replace("{{branch_cond_full}}", "{branch_cond_full}")
content = content.replace("{{branch_cond_s}}", "{branch_cond_s}")

with open('backend/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Main.py perfectly patched")
