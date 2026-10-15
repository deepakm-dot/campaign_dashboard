from check_missing import ch_query

print("=== Check DISTINCT years and date range in azure_sales_report for PAVR ===")
r = ch_query("""
    SELECT 
        toYear(date) as yr,
        toMonth(date) as mo,
        min(date) as min_date,
        max(date) as max_date,
        count() as cnt
    FROM azure_sales_report
    WHERE branch = 'PAVR'
    GROUP BY yr, mo
    ORDER BY yr DESC, mo DESC
""")
for x in r:
    print(x)
