import openpyxl, re
branch_map = {}
wb = openpyxl.load_workbook('Book1.xlsx', data_only=True)
for row in wb.active.iter_rows(min_row=2, values_only=True):
    if row[0] and row[1]:
        full_clean = re.sub(r'[^a-z0-9]', '', str(row[1]).lower())
        branch_map[full_clean] = str(row[0]).strip()
        clean_name = re.sub(r'(?i)\s*(FUTURE|DIGITAL|STORE)$', '', str(row[1])).strip().lower()
        first_word = clean_name.split()[0]
        if first_word not in branch_map:
            branch_map[first_word] = str(row[0]).strip()

print("mannarkkadfuture mapped to:", branch_map.get('mannarkkadfuture'))
print("mannarkkad mapped to:", branch_map.get('mannarkkad'))
