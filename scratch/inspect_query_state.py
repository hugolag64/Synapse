import requests
import re

url = "https://ednpro.app/_next/static/chunks/app/fiches/page-30588eaae2cc69eb.js"
headers = {"User-Agent": "Mozilla/5.0"}
text = requests.get(url, headers=headers).text

# Find all url parameter read statements like useQueryState or useSearchParams
url_params = re.findall(r'useQueryState\((["\'][^"\']+["\'])', text)
print("useQueryState keys:", set(url_params))

# Find all param getters
get_calls = re.findall(r'\.get\((["\'][a-zA-Z0-9_-]+["\'])\)', text)
print(".get() keys:", set(get_calls))
