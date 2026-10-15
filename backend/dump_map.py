import openpyxl
import json
import re

wb = openpyxl.load_workbook('Book1.xlsx', data_only=True)
sheet = wb.active

branch_map = {}
for row in sheet.iter_rows(min_row=2, values_only=True):
    code, name = row
    if code and name:
        # Clean the name to create a good key
        # Remove common suffixes that might not be in the campaign name
        clean_name = re.sub(r'(?i)\s*(FUTURE|DIGITAL|STORE)$', '', str(name)).strip().lower()
        branch_map[clean_name] = str(code).strip()
        
        # Add a first-word fallback just in case, but prioritize the full cleaned name
        first_word = clean_name.split()[0]
        if first_word not in branch_map:
            branch_map[first_word] = str(code).strip()

print(json.dumps(branch_map, indent=2))
