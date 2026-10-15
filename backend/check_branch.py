import openpyxl
wb = openpyxl.load_workbook('../Book1.xlsx', data_only=True)
for row in wb.active.iter_rows(min_row=2, values_only=True):
    if row[0] and row[1]:
        if 'kottakkal' in str(row[1]).lower():
            print(f"Code: {row[0]}, Name: {row[1]}")
