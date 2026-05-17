import asyncio
import json
import os
import time
import httpx

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
APIFY_TOKEN = os.environ["APIFY_TOKEN"]
SEEN_FILE = "seen_listings.json"

ACTOR_ID = "U5DUNxhH3qKt5PnCf"
MARKETPLACE_URL = "https://www.facebook.com/marketplace/104080902963296/vehicles?maxPrice=4000&exact=false"

def load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = httpx.post(url, json={
        "chat_id": CHAT_ID,
        "text": message,
    })
    resp.raise_for_status()

def run_apify_actor():
    headers = {"Authorization": f"Bearer {APIFY_TOKEN}"}
    
    # Start the actor run
    print("Starting Apify actor...")
    resp = httpx.post(
        f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs",
        headers=headers,
        json={
            "startUrls": [{"url": MARKETPLACE_URL}],
            "maxItems": 40,
        },
        timeout=30
    )
    resp.raise_for_status()
    run_id = resp.json()["data"]["id"]
    print(f"Run started: {run_id}")

    # Wait for it to finish (max 3 minutes)
    for _ in range(18):
        time.sleep(10)
        status_resp = httpx.get(
            f"https://api.apify.com/v2/actor-runs/{run_id}",
            headers=headers,
            timeout=30
        )
        status = status_resp.json()["data"]["status"]
        print(f"Status: {status}")
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break

    if status != "SUCCEEDED":
        print(f"Actor run did not succeed: {status}")
        return []

    # Get results
    results_resp = httpx.get(
        f"https://api.apify.com/v2/actor-runs/{run_id}/dataset/items",
        headers=headers,
        params={"limit": 40},
        timeout=30
    )
    results_resp.raise_for_status()
    return results_resp.json()

def main():
    seen = load_seen()
    listings = run_apify_actor()
    print(f"Got {len(listings)} listings from Apify")

    new_count = 0
    for item in listings:
        listing_id = str(item.get("id") or item.get("listingId") or "")
        if not listing_id or listing_id in seen:
            continue

        title = item.get("title") or item.get("name") or "No title"
        price = item.get("price") or item.get("priceAmount") or "Price not listed"
        url = item.get("url") or item.get("listingUrl") or ""

        seen.add(listing_id)
        new_count += 1

        msg = (
            f"New Vehicle - Hawke's Bay\n\n"
            f"{title}\n"
            f"{price}\n\n"
            f"{url}"
        )
        send_telegram(msg)
        print(f"Alert sent: {title} - {price}")

    save_seen(seen)

    if new_count == 0:
        print("No new listings this run.")
    else:
        print(f"Done - {new_count} alert(s) sent.")

if __name__ == "__main__":
    main()
