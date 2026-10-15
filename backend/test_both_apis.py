import urllib.request, json

for cid in [731, 732]:
    res = urllib.request.urlopen(f'http://localhost:8000/api/campaign/{cid}/store-sales')
    d = json.loads(res.read())
    print(f"\n=== Campaign {cid}: {d.get('campaign')} ===")
    print(f"Branch: {d.get('branch_name')} ({d.get('branch')})")
    print(f"Total Revenue: {d.get('total_revenue')}")
    print(f"Total Qty: {d.get('total_qty')}")
    print("Products:")
    for p in d.get('products', []):
        print(f"  {p['product']:18s}: qty={p['qty']:4d}, rev={p['revenue']:12,.2f}")
