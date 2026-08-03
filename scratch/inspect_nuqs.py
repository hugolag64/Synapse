import requests
import re

url = "https://ednpro.app/_next/static/chunks/app/fiches/page-30588eaae2cc69eb.js"
headers = {"User-Agent": "Mozilla/5.0"}
text = requests.get(url, headers=headers).text

# Find all keys passed to nuqs / useQueryState
nuqs_matches = re.findall(r'parseAs[a-zA-Z0-9]+\.withDefault|\b([a-zA-Z0-9_]+):\s*parseAs', text)
print("NUQS MATCHES:", set(nuqs_matches))

# Look for string literals in array or object near lisa2
lisa_ctx = re.findall(r'.{0,100}lisa2.{0,100}', text)
for c in lisa_ctx[:5]:
    print("CTX:", c)
