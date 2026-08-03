import requests
import re

url = "https://ednpro.app/fiches?tab=lisa2"
headers = {"User-Agent": "Mozilla/5.0"}
r = requests.get(url, headers=headers)

# Find all script src
scripts = re.findall(r'src=["\']([^"\']+\.js)["\']', r.text)
for s in scripts:
    full_url = s if s.startswith("http") else "https://ednpro.app" + s
    res = requests.get(full_url, headers=headers)
    text = res.text
    # Search for router / query params / searchParams / tab
    matches = re.findall(r'\.get\(["\']([a-zA-Z0-9_-]+)["\']\)', text)
    if matches:
        print(f"File {s} HAS GET PARAMS:", set(matches))
