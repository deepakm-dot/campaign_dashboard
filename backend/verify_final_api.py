import urllib.request, json

res = urllib.request.urlopen('http://localhost:8000/api/campaign/731/store-sales')
data = json.loads(res.read())
print(f"Total Revenue: {data['total_revenue']}")
print(f"Total Qty: {data['total_qty']}")
print("Products:")
for p in data['products']:
    print(f"  {p['product']:18s}: qty={p['qty']:3d}, revenue={p['revenue']:12,.2f}")
print("POS Reconciliation:", data.get('pos_reconciliation'))
