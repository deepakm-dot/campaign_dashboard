from backend.main import query_clickhouse
res = query_clickhouse("SELECT * FROM branch_master WHERE code = 'KJF'")
print("KJF:", res)
res2 = query_clickhouse("SELECT * FROM branch_master WHERE branch_name LIKE '%Kanjirappally%'")
print("Like:", res2)
