import requests
import re

url = "https://ednpro.app/_next/static/chunks/app/fiches/page-30588eaae2cc69eb.js"
headers = {"User-Agent": "Mozilla/5.0"}
text = requests.get(url, headers=headers).text

# Find all chunks loaded on /fiches
chunks = re.findall(r'["\']([0-9a-f]{16,}\.js)["\']', text)
print("Chunks:", chunks)

# Look for router or query param parsing in the entire file
items = re.findall(r'item[A-Za-z0-9_-]*', text, flags=re.IGNORECASE)
print("Item occurrences:", set(list(items)[:30]))
