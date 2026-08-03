import requests
import re

url = "https://ednpro.app/fiches?tab=lisa2"
headers = {"User-Agent": "Mozilla/5.0"}
r = requests.get(url, headers=headers)
print("STATUS:", r.status_code)
js_files = re.findall(r'src=["\']([^"\']+\.js)["\']', r.text)
print("JS FILES:", js_files)

# Look for router or path logic in scripts
for js_path in js_files:
    if not js_path.startswith("http"):
        js_url = "https://ednpro.app" + js_path
    else:
        js_url = js_path
    res = requests.get(js_url, headers=headers)
    if res.status_code == 200:
        matches = re.findall(r'(\/fiches[^\s"\'\`]+)', res.text)
        if matches:
            print(f"MATCHES IN {js_path}:", set(matches[:20]))
        tab_matches = re.findall(r'tab=([a-zA-Z0-9_-]+)', res.text)
        if tab_matches:
            print(f"TAB PARAMS IN {js_path}:", set(tab_matches))
        query_matches = re.findall(r'[\?&]([a-zA-Z0-9_-]+)=', res.text)
        relevant = [q for q in set(query_matches) if any(w in q.lower() for w in ['fiche', 'item', 'id', 'slug', 'lisa', 'card', 'active'])]
        if relevant:
            print(f"QUERY PARAMS IN {js_path}:", relevant[:20])
