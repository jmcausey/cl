import re
import functools
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlencode, urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

CATEGORY_LABELS = {
    "sss": "For Sale — All",
    "ata": "Antiques",
    "ppa": "Appliances",
    "art": "Arts + Crafts",
    "sna": "ATV / UTV / Sno",
    "aut": "Auto Parts",
    "ava": "Aviation",
    "bab": "Baby + Kids",
    "bar": "Barter",
    "bip": "Bikes",
    "boa": "Boats",
    "bpa": "Boat Parts",
    "bks": "Books",
    "bfs": "Business",
    "car": "Cars + Trucks",
    "clo": "Clothing + Accessories",
    "clt": "Collectibles",
    "cps": "Computer Parts",
    "sys": "Computers",
    "ele": "Electronics",
    "ela": "Farm + Garden",
    "zip": "Free",
    "fuo": "Furniture",
    "gms": "Garage Sale",
    "for": "General",
    "hvo": "Heavy Equipment",
    "hsh": "Household",
    "jwl": "Jewelry",
    "mat": "Materials",
    "mpa": "Motorcycle Parts",
    "mcy": "Motorcycles",
    "msg": "Music Instruments",
    "pho": "Photo + Video",
    "rvs": "RVs + Camp",
    "spo": "Sporting",
    "tia": "Tickets",
    "tls": "Tools",
    "tag": "Toys + Games",
    "tra": "Trailers",
    "vga": "Video Gaming",
    "wto": "Wanted",
    "wta": "Wheels + Tires",
    "services": "Services",
    "jobs": "Jobs",
    "housing": "Housing",
    "gigs": "Gigs",
    "res": "Resumes",
    "community": "Community",
}


def normalize_category(category):
    """Map human-friendly category labels to the canonical Craigslist code."""
    if category is None:
        return "sss"

    value = str(category).strip().strip("/")
    if not value:
        return "sss"

    lowered = value.lower()
    if lowered in CATEGORY_LABELS:
        return lowered

    label_map = {label.lower(): code for code, label in CATEGORY_LABELS.items()}
    if lowered in label_map:
        return label_map[lowered]

    if re.fullmatch(r"[A-Za-z0-9_-]+", value):
        return value

    raise ValueError(f"Invalid Craigslist category: {category!r}.")


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

CRAILSITES_URL = "https://www.craigslist.org/about/sites"

def _normalize_site_url(url):
    """Convert Craigslist directory /area/<site> links to the actual site."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    if host in {"www.craigslist.org", "craigslist.org"}:
        match = re.fullmatch(r"/area/([^/]+)", path)
        if match:
            return f"https://{match.group(1)}.craigslist.org"
    return url.rstrip("/")


def _normalize_location(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

@functools.lru_cache(maxsize=1)
def _craigslist_sites():
    response = requests.get(CRAILSITES_URL, headers=DEFAULT_HEADERS, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    rows = soup.select(
        "li.cl-static-search-result, "
        "li.cl-search-result, "
        ".cl-search-result, "
        ".result-row, "
        "li[data-pid]"
    )

    # Craigslist can serve result markup without the legacy result-row classes.
    if not rows:
        rows = []
        seen_nodes = set()
        for link in soup.select('a[href*="/d/"]'):
            node = link.find_parent(["li", "article", "div"])
            if node is not None and id(node) not in seen_nodes:
                seen_nodes.add(id(node))
                rows.append(node)

    print(f"Craigslist result rows found: {len(rows)}")
    sites = []
    context = ""
    for element in soup.find_all(["h2", "h3", "a"]):
        if element.name in ("h2", "h3"):
            context = element.get_text(" ", strip=True)
            continue
        href = element.get("href")
        name = element.get_text(" ", strip=True)
        if not href or not name or "craigslist.org" not in href:
            continue
        sites.append({"name": name, "url": _normalize_site_url(href), "context": context})
    return sites

def _location_aliases(location):
    """Return useful search forms for city/state input."""
    raw = str(location).strip()
    normalized = _normalize_location(raw)
    forms = {normalized}
    # "Dallas, TX" should match Craigslist's "Dallas / Fort Worth" region.
    parts = [p for p in re.split(r"[,]+", raw) if p.strip()]
    if parts:
        forms.add(_normalize_location(parts[0]))
    state = ""
    if len(parts) > 1:
        state = _normalize_location(parts[-1])
        forms.add(f"{forms.copy().pop()} {state}" if state else normalized)
    return {x for x in forms if x}


def resolve_craigslist_site(location):
    """Find the Craigslist regional site for a city or city/state."""
    if not location or not str(location).strip():
        raise ValueError("Location is required.")

    requested_forms = _location_aliases(location)

    try:
        sites = _craigslist_sites()
    except requests.RequestException as exc:
        raise ValueError(f"Could not load Craigslist site directory: {exc}") from exc

    # First prefer an exact match. Then allow a city name to occur inside a
    # regional Craigslist name, e.g. Dallas -> Dallas / Fort Worth.
    exact = []
    partial = []
    for site in sites:
        name = _normalize_location(site["name"])
        if name in requested_forms or requested_forms.intersection({name}):
            exact.append(site)
        elif any(form and (form in name or name in form) for form in requested_forms):
            partial.append(site)

    matches = exact or partial

    # Craigslist uses regional names. These aliases make common city/state
    # input resolve naturally without requiring users to know the region name.
    aliases = {
        "dallas": ("dallas fort worth", "dallas"),
        "fort worth": ("dallas fort worth",),
        "san francisco": ("san francisco bay area",),
        "new york": ("new york city",),
        "washington dc": ("washington",),
        "washington d c": ("washington",),
        "miami": ("miami dade",),
        "orlando": ("orlando",),
    }
    requested = next(iter(requested_forms), "")
    for alias in aliases.get(requested, ()):
        for site in sites:
            if _normalize_location(site["name"]) == alias:
                return site["url"]

    if not matches:
        raise ValueError(
            f"No Craigslist site was found for {location!r}. "
            "Enter a Craigslist city or regional site name, such as "
            "'Dallas, TX' or 'Dallas / Fort Worth'."
        )

    # If several regional names contain the city, don't silently choose.
    unique = {site["url"]: site for site in matches}
    if len(unique) > 1:
        exact_names = { _normalize_location(site["name"]) for site in matches }
        if len(exact_names) == 1:
            return next(iter(unique.values()))["url"]
        raise ValueError(
            f"Multiple Craigslist sites match {location!r}. "
            "Use the regional Craigslist name shown in the site directory."
        )
    return next(iter(unique.values()))["url"]

def base_location_search_url(location, category="sss", query=None, radius=None):
    """Build a search URL for any Craigslist-supported worldwide site."""
    site_url = resolve_craigslist_site(location)
    category = normalize_category(category)
    params = {}
    if query:
        params["query"] = str(query).strip()
    if radius is not None:
        try:
            radius = int(radius)
        except (TypeError, ValueError) as exc:
            raise ValueError("Radius must be an integer.") from exc
        if radius < 0:
            raise ValueError("Radius cannot be negative.")
        params["search_distance"] = radius
    query_string = urlencode(params)
    return f"{site_url}/search/{category}" + (f"?{query_string}" if query_string else "")

def get_base_location_search_url(location, category="sss", query=None, radius=None):
    """Backward-compatible alias for base_location_search_url."""
    return base_location_search_url(location, category=category, query=query, radius=radius)

def _listing_id(row, url):
    value = row.get("data-pid") or row.get("data-id")
    if value:
        return str(value)
    if not url:
        return None

    path = urlparse(url).path.rstrip("/")
    if not path:
        return None

    match = re.search(r"(\d{8,})(?:\.html)?$", path)
    if match:
        return match.group(1)

    last_segment = path.rsplit("/", 1)[-1]
    if last_segment and last_segment not in {"view", "d"}:
        return last_segment
    return None

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
                            area_label=None, radius=100):
    if not search_url:
        raise ValueError("A Craigslist search URL is required.")

    target_url, _ = urldefrag(search_url)
    known = {str(x) for x in (known_listing_ids or ())}

    try:
        print(f"Craigslist search: {target_url}")
        response = requests.get(target_url, headers=DEFAULT_HEADERS, timeout=20)
        print(f"Craigslist response: HTTP {response.status_code} ({len(response.text)} bytes)")
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Craigslist request failed: {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")
    rows = soup.select(
        "li.cl-static-search-result, li.cl-search-result, "
        ".cl-search-result, .result-row, li[data-pid]"
    )

    if not rows:
        rows = []
        seen_nodes = set()
        for link in soup.select('a[href*="/d/"]'):
            node = link.find_parent(["li", "article", "div"])
            if node is not None and id(node) not in seen_nodes:
                seen_nodes.add(id(node))
                rows.append(node)

    print(f"Craigslist result rows found: {len(rows)}")

    listings, seen = [], set()
    now = datetime.now()

    for row in rows:
        title_el = row.select_one(
            ".result-title, .titlestring, .title, a.posting-title, a"
        )
        if not title_el:
            continue

        title = title_el.get_text(" ", strip=True)
        if "modem" in title.lower():
            continue

        link = row.select_one("a.posting-title, a.result-title, a[href]")
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
        location = (
            location_el.get_text(" ", strip=True).strip(" ()")
            if location_el else None
        )

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
                    desc = ds.select_one(
                        'meta[property="og:description"], meta[name="description"]'
                    )
                    description = _description(
                        body.get_text(" ", strip=True)
                        if body else (desc.get("content") if desc else None)
                    )
                    address = ds.select_one(".mapaddress")
                    if address:
                        location = location or address.get_text(" ", strip=True)
            except requests.RequestException:
                pass

        category_key = normalize_category(
            category or urlparse(target_url).path.rstrip("/").split("/")[-1]
        )
        listings.append({
            "craigslist_id": cid,
            "title": title,
            "price_text": price_text,
            "price_amount": _price(price_text),
            "location": location,
            "listing_url": post_url,
            "category": CATEGORY_LABELS.get(category_key, category_key),
            "search_query": query,
            "posted_at": posted.isoformat(sep=" ") if posted else None,
            "image_url": image_url,
            "description": description,
        })

        if max_results is not None and len(listings) >= max_results:
            break

    return listings


def store_listing(listing, db):
    cursor = db.execute(
        """INSERT OR IGNORE INTO craigslist_postings
           (craigslist_id,title,price_text,price_amount,location,
            listing_url,category,search_query,posted_at,image_url,description)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (listing["craigslist_id"], listing["title"], listing.get("price_text"),
         listing.get("price_amount"), listing.get("location"),
         listing["listing_url"], listing.get("category"),
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

