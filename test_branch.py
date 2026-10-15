import openpyxl
import re

wb = openpyxl.load_workbook('Book1.xlsx', data_only=True)
sheet = wb.active

branch_map = {}
for row in sheet.iter_rows(min_row=2, values_only=True):
    code, name = row
    if code and name:
        clean_name = re.sub(r'(?i)\s*(FUTURE|DIGITAL|STORE)$', '', str(name)).strip().lower()
        print(f"Original: {name} -> Clean: {clean_name} -> Code: {code}")
