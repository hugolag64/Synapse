import requests
import re

url = "https://ednpro.app/_next/static/chunks/app/fiches/page-30588eaae2cc69eb.js"
headers = {"User-Agent": "Mozilla/5.0"}
text = requests.get(url, headers=headers).text

# Find all keys near useQueryState or useQueryStates
matches = re.findall(r'([a-zA-Z0-9_]+)\s*:\s*\(0\s*,\s*[a-zA-Z0-9_\$]+\.', text)
print("Keys:", set(matches))
