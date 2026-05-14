import asyncio
import json
import os
import httpx
from playwright.async_api import async_playwright

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
COOKIES_JSON = os.environ["FB_COOKIES"]
SEEN_FILE = "seen_listings.json"

# FB Marketplace — vehicles near Hastings NZ, under $4000 NZD, ~100km radius
MARKETPLACE_URL = (
    "https://www.facebook.com/marketplace/hastings/"
    "vehicles?minPrice=0&maxPrice=4000&exact=false"
)

async def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        })
        resp.raise_for_status()

def load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

async def scrape():
    cookies = json.loads(COOKIES_JSON)
    seen = load_seen()
    new_listings = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-NZ",
        )
        await context.add_cookies(cookies)
        page = await context.new_page()

        print(f"Loading: {MARKETPLACE_URL}")
        await page.goto(MARKETPLACE_URL, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)  # let JS render listings

        # Grab all marketplace item links
        listing_elements = await page.query_selector_all('a[href*="/marketplace/item/"]')
        print(f"Found {len(listing_elements)} listing elements")

        for el in listing_elements:
            href = await el.get_attribute("href")
            if not href:
                continue

            # Extract clean listing ID
            try:
                listing_id = href.split("/marketplace/item/")[1].split("/")[0].split("?")[0]
            except IndexError:
                continue

            if listing_id in seen:
                continue

            # Pull visible text (title + price usually combined)
            raw_text = (await el.inner_text()).strip()
            lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
            title = lines[0] if lines else "No title"
            price = lines[1] if len(lines) > 1 else "Price not listed"

            full_link = (
                f"https://www.facebook.com{href}"
                if href.startswith("/") else href
            )
            # Strip tracking params for cleaner link
            full_link = full_link.split("?")[0]

            seen.add(listing_id)
            new_listings.append({
                "title": title[:120],
                "price": price[:40],
                "link": full_link,
            })

        await browser.close()

    save_seen(seen)

    for item in new_listings:
        msg = (
            f"🚗 <b>New Vehicle — Hawke's Bay</b>\n\n"
            f"<b>{item['title']}</b>\n"
            f"💰 {item['price']}\n\n"
            f"<a href='{item['link']}'>View on Marketplace →</a>"
        )
        await send_telegram(msg)
        print(f"Alert sent: {item['title']} — {item['price']}")

    if not new_listings:
        print("No new listings this run.")
    else:
        print(f"Done — {len(new_listings)} alert(s) sent.")

if __name__ == "__main__":
    asyncio.run(scrape())
