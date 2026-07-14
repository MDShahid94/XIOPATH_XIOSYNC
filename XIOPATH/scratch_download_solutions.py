import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

out_dir = "/Users/karmareturns/Desktop/XIOPATH/Cloudflare Products/Solutions and Plans"
os.makedirs(out_dir, exist_ok=True)

def fetch_md(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        return response.read().decode('utf-8')

# Download plans
try:
    plans_md = fetch_md("https://www.cloudflare.com/plans/.md")
    with open(os.path.join(out_dir, "Plans.md"), "w") as f:
        f.write(plans_md)
    print("Downloaded: Plans")
except Exception as e:
    print(f"Failed to download Plans: {e}")

# Download solutions hub
try:
    solutions_md = fetch_md("https://www.cloudflare.com/solutions/.md")
    with open(os.path.join(out_dir, "Solutions Hub.md"), "w") as f:
        f.write(solutions_md)
    print("Downloaded: Solutions Hub")
    
    # Extract links from solutions_md
    links = re.findall(r'\]\((/solutions/[^)]+)\)', solutions_md)
    
    # Combine and deduplicate by path
    all_links = set()
    for path in links:
        if path != "/solutions/" and not path.startswith("/solutions/?"):
            if not path.endswith('/'):
                path += '/'
            all_links.add(path)

    def download_solution(path):
        name = path.strip('/').split('/')[-1]
        md_url = f"https://www.cloudflare.com{path}.md"
        safe_name = name.replace('/', '-').replace('\\', '-')
        if not safe_name:
            safe_name = "index"
        file_path = os.path.join(out_dir, f"Solution - {safe_name.title()}.md")
        try:
            content = fetch_md(md_url)
            with open(file_path, "w") as f:
                f.write(content)
            print(f"Downloaded: {name}")
        except Exception as e:
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

    print(f"Found {len(all_links)} solutions to download.")
    with ThreadPoolExecutor(max_workers=10) as executor:
        executor.map(download_solution, all_links)

except Exception as e:
    print(f"Failed to process solutions: {e}")

print("Done.")
