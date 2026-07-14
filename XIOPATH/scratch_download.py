import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# Make directory
out_dir = "/Users/karmareturns/Desktop/XIOPATH/Cloudflare Products"
os.makedirs(out_dir, exist_ok=True)

url = "https://www.cloudflare.com/products/.md"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as response:
    content = response.read().decode('utf-8')

# Find all product links
links = re.findall(r'\[\*\*(.*?)\*\*.*?\]\((/products/.*?/?)\)', content)

print(f"Found {len(links)} products to download.")

def download_product(item):
    name, path = item
    if not path.endswith('/'):
        path += '/'
    md_url = f"https://www.cloudflare.com{path}.md"
    safe_name = name.replace('/', '-').replace('\\', '-')
    file_path = os.path.join(out_dir, f"{safe_name}.md")
    
    try:
        req = urllib.request.Request(md_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            md_content = response.read().decode('utf-8')
        with open(file_path, "w") as f:
            f.write(md_content)
        print(f"Downloaded: {name}")
    except Exception as e:
        # Fallback to HTML if markdown is not available
        try:
            fallback_url = f"https://www.cloudflare.com{path}"
            req = urllib.request.Request(fallback_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as resp:
                html_content = resp.read().decode('utf-8')
            with open(file_path, "w") as f:
                f.write(f"# {name}\n\nFetched as HTML due to error: {e}\n\nURL: {fallback_url}\n")
            print(f"Fallback downloaded: {name}")
        except Exception as e2:
            print(f"Failed to download {name}: {e2}")

with ThreadPoolExecutor(max_workers=10) as executor:
    executor.map(download_product, links)

print("Done downloading all products.")
