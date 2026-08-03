import requests
import re

url = "https://ednpro.app/_next/static/chunks/app/fiches/page-30588eaae2cc69eb.js"
headers = {"User-Agent": "Mozilla/5.0"}
text = requests.get(url, headers=headers).text

# Find all occurrences of searchParams or query params
params = re.findall(r'searchParams[^\.]{0,30}\.get\((["\'][^"\']+["\'])\)', text)
print("SearchParams get():", set(params))

# Find all strings containing id, item, slug or fiche
strings = re.findall(r'["\']([a-zA-Z0-9_-]*(?:item|fiche|lisa|slug|id|card|select|active)[a-zA-Z0-9_-]*)["\']', text, flags=re.IGNORECASE)
print("Relevant key strings:", set(list(strings)[:40]))
