import html
import re
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://easttexas.craigslist.org/search/sss"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def base_location_search_url(city, state=None, category="sss"):
    """Build a Craigslist search URL centered on a city or city/state."""
    if not city or not str(city).strip():
        raise ValueError("City is required.")

    location = str(city).strip()
    if state and str(state).strip():
        location = f"{location}, {str(state).strip()}"

    if not re.fullmatch(r"[^,]+(?:,\\s*[A-Za-z]{2})?", location):
        raise ValueError(
            "Location must be a city or city/state, such as 'Athens' or 'Athens, TX'."
        )

    category = (category or "sss").strip().strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", category):
        raise ValueError("Invalid Craigslist category.")

    return (
        f"https://www.craigslist.org/search/{category}"
        f"?search_location={quote_plus(location)}"
    )


def get_base_location_search_url(location, category="sss"):
    """Resolve a city or city/state string into a Craigslist search URL."""
    if not location or not str(location).strip():
        raise ValueError("Location is required.")

    parts = [part.strip() for part in str(location).split(",", 1)]
    if len(parts) == 1:
        return base_location_search_url(parts[0], category=category)
    return base_location_search_url(parts[0], parts[1], category=category)

def _listing_id(row, url):
    value = row.get("data-pid") or row.get("data-id")
    if value:
        return str(value)
    match = re.search(r"(\d{8,})(?:\.html)?$", urlparse(url).path)
    return match.group(1) if match else None

def _posted_at(value):
    if not value:
        return None
    for parser in (
        lambda v: datetime.fromisoformat(v.replace("Z", "+00:00")),
        lambda v: datetime.strptime(v, "%Y-%m-%d %H:%M"),
    ):
        try:
            result = parser(value)
            if result.tzinfo:
                result = result.astimezone().replace(tzinfo=None)
            return result
        except ValueError:
            continue
    return None

def _price(value):
    if not value:
        return None
    match = re.search(r"\d[\d,]*(?:\.\d{1,2})?", value)
    return float(match.group(0).replace(",", "")) if match else None

def _description(value):
    if not value:
        return None
    value = re.sub(r"\bQR\s+Code\s+Link\s+to\s+This\s+Post\b", "", value, flags=re.I)
    return re.sub(r"\s+", " ", value).strip() or None

def get_craigslist_listings(query="surfboard", max_results=5, known_listing_ids=None,
                            search_url=None, category=None,
                            area_label="100 miles of Athens, TX", radius=100):
    if search_url:
        target_url, _ = urldefrag(search_url)
    else:
        encoded = quote_plus(query)
        suffix = "zip" if category == "zip" else "sss"
        target_url = f"{BASE_URL.rsplit('/',1)[0]}/{suffix}?query={encoded}&search_distance={radius}&postal=75751"

    known = {str(x) for x in (known_listing_ids or ())}
    try:
        response = requests.get(target_url, headers=DEFAULT_HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    listings, seen = [], set()
    now = datetime.now()

    for row in soup.select(".result-row, .cl-search-result, li.cl-static-search-result"):
        title_el = row.select_one(".result-title, .titlestring, .title, a.posting-title, a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if "modem" in title.lower():
            continue
        link = row.select_one("a.posting-title, a[href]")
        post_url = urljoin(target_url, link.get("href", "")) if link else ""
        cid = _listing_id(row, post_url)
        if not cid or cid in known or cid in seen:
            continue
        seen.add(cid)

        time_el = row.select_one("time, .result-date")
        posted = _posted_at(time_el.get("datetime") if time_el else None)
        if posted and now - posted > timedelta(days=1):
            continue

        price_el = row.select_one(".result-price, .price, .priceinfo")
        location_el = row.select_one(".result-hood, .nearby, .location")
        price_text = price_el.get_text(strip=True) if price_el else None
        location = location_el.get_text(" ", strip=True).strip(" ()") if location_el else None
        image_url = None
        description = None

        if post_url:
            try:
                detail = requests.get(post_url, headers=DEFAULT_HEADERS, timeout=15)
                if detail.ok:
                    ds = BeautifulSoup(detail.text, "html.parser")
                    img = ds.select_one('meta[property="og:image"]')
                    image_url = img.get("content") if img else None
                    body = ds.select_one("#postingbody, .postingbody")
                    desc = ds.select_one('meta[property="og:description"], meta[name="description"]')
                    description = _description(body.get_text(" ", strip=True) if body else (desc.get("content") if desc else None))
                    address = ds.select_one(".mapaddress")
                    if address:
                        location = location or address.get_text(" ", strip=True)
            except requests.RequestException:
                pass

        listings.append({
            "craigslist_id": cid, "title": title,
            "price_text": price_text, "price_amount": _price(price_text),
            "location": location, "listing_url": post_url,
            "category": category or urlparse(target_url).path.rstrip("/").split("/")[-1],
            "search_query": query,
            "posted_at": posted.isoformat(sep=" ") if posted else None,
            "image_url": image_url, "description": description,
        })
        if max_results is not None and len(listings) >= max_results:
            break
    return listings

def store_listing(listing, db):
    cursor = db.execute(
        """INSERT OR IGNORE INTO craigslist_postings
           (craigslist_id,title,price_text,price_amount,location,latitude,longitude,
            listing_url,category,search_query,posted_at,image_url,description)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (listing["craigslist_id"], listing["title"], listing.get("price_text"),
         listing.get("price_amount"), listing.get("location"), listing.get("latitude"),
         listing.get("longitude"), listing["listing_url"], listing.get("category"),
         listing.get("search_query"), listing.get("posted_at"), listing.get("image_url"),
         listing.get("description")),
    )
    return cursor.rowcount == 1

def run_scraper(query="surfboard", max_results=5, **kwargs):
    from . import create_app, get_db
    app = create_app()
    with app.app_context():
        db = get_db()
        known = {r["craigslist_id"] for r in db.execute("SELECT craigslist_id FROM craigslist_postings")}
        listings = get_craigslist_listings(query=query, max_results=max_results, known_listing_ids=known, **kwargs)
        inserted = sum(store_listing(item, db) for item in listings)
        db.commit()
        return inserted

def run_pet_scraper():
    return run_scraper(query="pets", max_results=None,
                       search_url="https://www.craigslist.org/search/area/easttexas?cat=pet#search=2~list~0",
                       category="pet", area_label="East Texas")
