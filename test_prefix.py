import re

def test_match(camp_name, raw_file_name):
    # Split file name into the "store" part and the "data source" part.
    # Usually it's separated by '_' or the word 'store' or 'data'
    prefix = re.split(r'_|\bstore\b|\bdata\b', raw_file_name.lower())[0].strip()
    c_norm = re.sub(r'[^a-z0-9]', '', camp_name.lower())
    p_norm = re.sub(r'[^a-z0-9]', '', prefix)
    
    return c_norm == p_norm

print("Kottakkal Future vs Kottakkal Future_Store Data... ->", test_match("Kottakkal Future", "Kottakkal Future_Store Data Visited Last 3 year.xlsx"))
print("Kottakkal vs Kottakkal Future_Store Data... ->", test_match("Kottakkal", "Kottakkal Future_Store Data Visited Last 3 year.xlsx"))
print("Kottakkal vs Kottakkal_Store Data... ->", test_match("Kottakkal", "Kottakkal_Store Data Visited Last 3 year.xlsx"))
print("Kottakkal vs Kottakkal - Store Data... ->", test_match("Kottakkal", "Kottakkal - Store Data Visited Last 3 year.xlsx"))
print("Vypin vs Vypin onam offers store data.xlsx ->", test_match("Vypin", "Vypin onam offers store data.xlsx"))
