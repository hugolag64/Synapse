import requests
import re

url = "https://ednpro.app/fiches?tab=lisa2"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
r = requests.get(url, headers=headers)

scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', r.text)
print("Scripts found:", scripts)

# Search all script links or text
for s in scripts:
    full_url = s if s.startswith("http") else "https://ednpro.app" + s
    resp = requests.get(full_url, headers=headers)
    if "lisa2" in resp.text:
        print("FOUND lisa2 IN SCRIPT:", full_url)
        # Extract snippet around lisa2
        idx = resp.text.find("lisa2")
        snippet = resp.text[max(0, idx-200):min(len(resp.text), idx+300)]
        print("SNIPPET:", snippet)
