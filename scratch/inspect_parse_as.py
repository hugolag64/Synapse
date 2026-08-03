import requests
import re

url = "https://ednpro.app/_next/static/chunks/app/fiches/page-30588eaae2cc69eb.js"
headers = {"User-Agent": "Mozilla/5.0"}
text = requests.get(url, headers=headers).text

# Find all parseAs usages
matches = re.findall(r'parseAs[a-zA-Z0-9_]*', text)
print("parseAs usages:", set(matches))

# Look for URL search params reading logic in JS
search_matches = re.findall(r'\.get\(["\']([^"\']+)["\']\)', text)
print("Get calls:", set(search_matches))
