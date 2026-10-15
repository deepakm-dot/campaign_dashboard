from check_missing import ch_query

r = ch_query("""
SELECT code, branch_name, district
FROM branch_master
ORDER BY branch_name
""")
print(f"Total branches in branch_master: {len(r)}")
for b in r:
    name = b['branch_name'].lower()
    if 'par' in name or 'ernakulam' in b['district'].lower():
        print(f"  {b['code']:10s} | {b['branch_name']:30s} | {b['district']}")
