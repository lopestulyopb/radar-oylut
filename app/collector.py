
from bs4 import BeautifulSoup
import httpx
from urllib.parse import urljoin
async def collect_links(sources):
    links=[]
    async with httpx.AsyncClient(headers={"User-Agent":"Mozilla/5.0"},follow_redirects=True,timeout=20) as client:
        for source in sources:
            try:
                r=await client.get(source)
                soup=BeautifulSoup(r.text,"html.parser")
                for a in soup.select("a[href]"):
                    href=urljoin(source,a.get("href",""))
                    if href.startswith(source.rstrip("/")) and href not in links:
                        links.append(href)
            except Exception:
                pass
    return links
