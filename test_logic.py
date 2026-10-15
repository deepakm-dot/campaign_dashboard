import re

def _token_match_score(cname, dsrc, fname):
    c_tokens = set(re.findall(r'[a-z0-9]+', str(cname).lower()))
    d_tokens = set(re.findall(r'[a-z0-9]+', str(dsrc).lower()))
    target_tokens = c_tokens.union(d_tokens)
    f_tokens = set(re.findall(r'[a-z0-9]+', str(fname).lower()))
    
    if not target_tokens: return 0.0
    match_count = sum(1 for t in target_tokens if t in f_tokens)
    return match_count / len(target_tokens)

print("Kottakkal Future vs Kottakkal:", _token_match_score("Kottakkal Future", "Store Data Visited Last 3 year", "Kottakkal_Store Data Visited Last 3 year.xlsx"))
print("Kottakkal Future vs Kottayam Future:", _token_match_score("Kottakkal Future", "Store Data Visited Last 3 year", "Kottayam Future_Store Data Visited Last 3 year.xlsx"))
print("Kottakkal Future vs Kottakkal Future:", _token_match_score("Kottakkal Future", "Store Data Visited Last 3 year", "Kottakkal Future_Store Data Visited Last 3 year.xlsx"))

