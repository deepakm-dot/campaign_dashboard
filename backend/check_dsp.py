from check_missing import ch_query

r = ch_query("SELECT * FROM item_master WHERE item_code LIKE '%DSP%' LIMIT 5")
print(r)

r2 = ch_query("SELECT * FROM item_master WHERE trim(upper(item_code)) = 'DSP60701'")
print(r2)
