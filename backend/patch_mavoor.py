import os

def patch_file(filepath, replacements):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    for old, new in replacements:
        content = content.replace(old, new)
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

# Patch kpicalc.py
patch_file('backend/kpicalc.py', [
    ("AND branch = '{branch}'", "AND {branch_cond}"),
    ('query = f"""', '''branch_cond = f"branch = '{branch}'"
        if "mavoor road" in campaign_name.lower():
            branch_cond = "branch IN ('KIN', 'LAN', 'MAH', 'PCT', 'PUT', 'SBM', 'CAM')"

        query = f"""''')
])

# Patch main.py queries
patch_file('backend/main.py', [
    # 1. Product Sales Query
    ("AND azure_sales_report.branch = '{branch}'", "AND {branch_cond}"),
    ('product_sales_sql = f"""', '''branch_cond = f"azure_sales_report.branch = '{branch}'"
        if "mavoor road" in camp.get('campaign_name', '').lower():
            branch_cond = "azure_sales_report.branch IN ('KIN', 'LAN', 'MAH', 'PCT', 'PUT', 'SBM', 'CAM')"
            display_name = "Mavoor Road (Group of Stores)"
            
        product_sales_sql = f"""'''),

    # 2. Total POS metrics
    ("AND branch = '{branch}'", "AND {branch_cond_pos}"),
    ('pos_totals_sql = f"""', '''branch_cond_pos = f"branch = '{branch}'"
        if "mavoor road" in camp.get('campaign_name', '').lower():
            branch_cond_pos = "branch IN ('KIN', 'LAN', 'MAH', 'PCT', 'PUT', 'SBM', 'CAM')"

        pos_totals_sql = f"""'''),

    # 3. Segmentation query
    ("AND branch = '{branch}'", "AND {branch_cond_pos}"),
    ('seg_sql = f"""', 'seg_sql = f"""'),

    # 4. Brand Breakdown Query
    ("AND azure_sales_report.branch = '{branch}'", "AND {branch_cond}"),
    ('brand_query = f"""', '''branch_cond = f"azure_sales_report.branch = '{branch}'"
        if "mavoor road" in camp.get('campaign_name', '').lower():
            branch_cond = "azure_sales_report.branch IN ('KIN', 'LAN', 'MAH', 'PCT', 'PUT', 'SBM', 'CAM')"

        brand_query = f"""''')
])

print('Patched successfully!')
