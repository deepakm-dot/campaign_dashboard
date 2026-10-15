import urllib.request
try:
    response = urllib.request.urlopen("https://script.google.com/macros/s/AKfycbx8RQoxU-Js-kQuY7cs90K7Rc1-pDUxq7OzLM1Oj9G5q2Kw5otr-gsJI66f_lJ1KXJCSQ/exec")
    print(response.read().decode()[:500])
except Exception as e:
    print("ERROR:", e)
