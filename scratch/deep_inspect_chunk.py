import requests
import re

url = "https://ednpro.app/_next/static/chunks/app/fiches/page-30588eaae2cc69eb.js"
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, headers=headers)
text = resp.text

# Look for query parameters or state keys
matches = re.findall(r'[a-zA-Z0-9_]+\.get\(["\']([^"\']+)["\']\)', text)
print("URL Search Params get():", set(matches))

# Look for router.push or link patterns
router_matches = re.findall(r'fiches\?[^"\']*', text)
print("Fiches URL patterns:", set(router_matches))
