import openpyxl
import sys
import re

wb = openpyxl.load_workbook('Book1.xlsx', data_only=True)
sheet = wb.active

# Let's inspect the headers (row 1 or 2)
for i, row in enumerate(sheet.iter_rows(min_row=1, max_row=5, values_only=True)):
    print(f"Row {i+1}: {row}")
