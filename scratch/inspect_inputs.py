import requests
import re

url = "https://ednpro.app/_next/static/chunks/app/fiches/page-30588eaae2cc69eb.js"
headers = {"User-Agent": "Mozilla/5.0"}
text = requests.get(url, headers=headers).text

# Search for placeholders in input fields
placeholders = re.findall(r'placeholder=["\']([^"\']+)["\']', text)
print("Placeholders:", placeholders)

# Search for search / query input handlers
inputs = re.findall(r'([a-zA-Z0-9_]*search[a-zA-Z0-9_]*)', text, flags=re.IGNORECASE)
print("Search variables:", set(inputs[:30]))
