import nest_asyncio
import asyncio
from fastapi import FastAPI
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import requests
import httpx
import redis

nest_asyncio.apply()
app = FastAPI()

# Initialize Redis client
redis_client = redis.StrictRedis(host='redis', port=6379, decode_responses=True)

# Replace the synchronous get_published_time with an asynchronous version
async def get_published_time(article_url):
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(article_url, timeout=30)
        soup = BeautifulSoup(res.content, 'html.parser')

        time_tag = soup.find('time')
        if time_tag and time_tag.has_attr('datetime'):
            published_str = time_tag['datetime']
            published_dt = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
            now = datetime.now(published_dt.tzinfo)
            hours_ago = (now - published_dt).total_seconds() / 3600
            return f"{hours_ago:.1f} hours ago"
    except Exception as e:
        print(f"[Time Parse Error] {e}")
    return "Unknown"

# Update fetch_prothomalo_h3s to use the async get_published_time
async def fetch_prothomalo_h3s(link):
    results = []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(link, timeout=60000)

            h3s = await page.query_selector_all("h3")

            for h3 in h3s:
                text = await h3.inner_text()
                link_tag = await h3.query_selector("a")
                href = await link_tag.get_attribute("href") if link_tag else None
                full_href = href if href and href.startswith("http") else f"https://www.prothomalo.com{href}" if href else None
                if text and full_href:
                    time_ago = await get_published_time(full_href)
                    results.append({
                        "headline": text,
                        "link": full_href,
                        "published": time_ago
                    })
            await browser.close()
    except Exception as e:
        print(f"[Fetch H3 Error] {e}")
    return results

async def fetch_navbar_links():
    links = []

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("https://www.prothomalo.com", timeout=60000)

            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            nav = soup.find('nav')
            if nav:
                for a_tag in nav.find_all('a', href=True):
                    name = a_tag.get_text(strip=True)
                    href = a_tag['href']
                    print(href)
                    if name and href:
                        full_url = href if href.startswith('http') else 'https://www.prothomalo.com' + href
                        links.append({'name': name, 'link': full_url})
            await browser.close()
    except Exception as e:
        print(f"[Fetch Navbar Error] {e}")
    return links

@app.get("/")
def read_root():
    return {"message": "Welcome to the Prothom Alo Scraper API"}

@app.get("/scrape")
async def scrape():
    try:

        # If no cache, scrape the website
        navbar_data = await fetch_navbar_links()
        results = []

        for item in navbar_data:
            headlines = await fetch_prothomalo_h3s(item['link'])
            results.append({
                "category": item['name'],
                "url": item['link'],
                "headlines": headlines
            })
        
        redis_client.delete("scraped_data")

        # Store the scraped data in Redis cache with a timeout of 1 hour
        redis_client.setex("scraped_data", 3600, str(results))

        return {"data": results}
    except Exception as e:
        print(f"[Scrape Error] {e}")
        return {"error": "Something went wrong while scraping."}

@app.get("/news-paper")
async def get_news_paper():
    try:
        cached_data = redis_client.get("scraped_data")
        redis_client.delete("scraped_data")
        if cached_data:
            return {"data": (cached_data)}
    except Exception as e:
        print(f"[News Paper Error] {e}")
    return {"error": "Failed to fetch news paper."}

@app.get("/shamim")
def shamim():
    try:
        # Set a test value in Redis with a 1-hour expiration
        redis_client.setex("scraped_data", 3600, "shamim")
        print("Test value 'shamim' has been set in Redis.")
        return {"message": "Test value 'shamim' has been set in Redis."}
    except Exception as e:
        print(f"[Shamim Endpoint Error] {e}")
        return {"error": f"Failed to set test value in Redis: {e}"}
