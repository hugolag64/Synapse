import requests
import re

url = "https://ednpro.app/_next/static/chunks/app/fiches/page-30588eaae2cc69eb.js"
headers = {"User-Agent": "Mozilla/5.0"}
text = requests.get(url, headers=headers).text

# Find where tab= is checked or used
idx = 0
while True:
    idx = text.find("tab", idx)
    if idx == -1:
        break
    snippet = text[max(0, idx-80):min(len(text), idx+120)]
    print("TAB SNIPPET:", snippet)
    idx += 3
