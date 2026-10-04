import json
import re
import functools
from datetime import datetime
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
    "ccc": "Community — All",
    "act": "Community — Activities",
    "ats": "Community — Artists",
    "kid": "Community — Childcare",
    "cls": "Community — Classes",
    "eve": "Community — Events",
    "grp": "Community — Groups",
    "lnw": "Community — Local News",
    "vol": "Community — Volunteers",
    "community": "Community — All",
    "pet": "Community — Pets",
    "pol": "Community — Politics",
    "com": "Community — General",
    "lnf": "Community — Lost & Found",
    "msc": "Community — Missed Connections",
    "muc": "Community — Musicians",
    "rid": "Community — Rideshare",
    "rnr": "Community — Rants & Raves",
}


def normalize_category(category):
    """Map human-friendly category labels to the canonical Craigslist code."""
    if category is None:
        return "sss"

    value = str(category).strip().strip("/")
    if not value:
        return "sss"

    lowered = value.lower()
    if lowered == "community":
        return "ccc"
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

STATE_NAMES = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas",
    "ca": "california", "co": "colorado", "ct": "connecticut", "de": "delaware",
    "fl": "florida", "ga": "georgia", "hi": "hawaii", "id": "idaho",
    "il": "illinois", "in": "indiana", "ia": "iowa", "ks": "kansas",
    "ky": "kentucky", "la": "louisiana", "me": "maine", "md": "maryland",
    "ma": "massachusetts", "mi": "michigan", "mn": "minnesota", "ms": "mississippi",
    "mo": "missouri", "mt": "montana", "ne": "nebraska", "nv": "nevada",
    "nh": "new hampshire", "nj": "new jersey", "nm": "new mexico", "ny": "new york",
    "nc": "north carolina", "nd": "north dakota", "oh": "ohio", "ok": "oklahoma",
    "or": "oregon", "pa": "pennsylvania", "ri": "rhode island", "sc": "south carolina",
    "sd": "south dakota", "tn": "tennessee", "tx": "texas", "ut": "utah",
    "vt": "vermont", "va": "virginia", "wa": "washington", "wv": "west virginia",
    "wi": "wisconsin", "wy": "wyoming", "dc": "district of columbia",
}


def _location_aliases(location):
    """Return useful search forms for city/state input."""
    raw = str(location).strip()
    normalized = _normalize_location(raw)
    forms = {normalized}
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if parts:
        forms.add(_normalize_location(parts[0]))
    if len(parts) > 1:
        state = _normalize_location(parts[-1])
        forms.add(f"{_normalize_location(parts[0])} {state}")
    return {x for x in forms if x}


def _requested_state(location):
    """Return normalized state forms when the user supplied a state."""
    parts = [p.strip() for p in str(location).strip().split(",") if p.strip()]
    if len(parts) < 2:
        return set()
    state = _normalize_location(parts[-1])
    full_name = STATE_NAMES.get(state)
    return {state, full_name} if full_name else {state}


def _site_state_forms(site):
    """Infer a site's state from its directory context and hostname."""
    forms = set()
    context = _normalize_location(site.get("context", ""))
    if context:
        for abbreviation, full_name in STATE_NAMES.items():
            if full_name in context:
                forms.update({abbreviation, full_name})

    hostname = urlparse(site["url"]).hostname or ""
    host = hostname.split(".")[0].lower()
    for abbreviation in STATE_NAMES:
        if host.endswith(abbreviation):
            forms.add(abbreviation)
    return forms


def resolve_craigslist_site(location):
    """Find the Craigslist regional site for a city or city/state."""
    if not location or not str(location).strip():
        raise ValueError("Location is required.")

    requested_forms = _location_aliases(location)
    requested_states = _requested_state(location)

    try:
        sites = _craigslist_sites()
    except requests.RequestException as exc:
        raise ValueError(f"Could not load Craigslist site directory: {exc}") from exc

    # When a state is supplied, discard same-named cities from other states
    # before doing the normal city/region matching.
    candidate_sites = sites
    if requested_states:
        state_matches = [
            site for site in sites
            if requested_states.intersection(_site_state_forms(site))
        ]
        if state_matches:
            candidate_sites = state_matches

    # First prefer an exact match. Then allow a city name to occur inside a
    # regional Craigslist name, e.g. Dallas -> Dallas / Fort Worth.
    exact = []
    partial = []
    for site in candidate_sites:
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
    """Build a search URL for any Craigslist-supported city or regional site."""
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
        if radius:
            params["search_distance"] = radius

    raw_location = str(location).strip()
    parts = [part.strip() for part in raw_location.split(",") if part.strip()]

    # Craigslist's regional city URLs are the most reliable form for
    # city/state searches. For example, Athens, TX is served by East Texas
    # at /search/athens-tx/pet rather than the old /search/area/ URL form.
    if len(parts) >= 2:
        city = re.sub(r"[^a-z0-9]+", "-", parts[0].lower()).strip("-")
        state = re.sub(r"[^a-z0-9]+", "-", parts[-1].lower()).strip("-")
        if city and state:
            # Craigslist's public city endpoint accepts city-state slugs
            # directly on www.craigslist.org, avoiding ambiguity between
            # identically named cities such as Athens, TX and Athens, GA.
            params["cat"] = category
            query_string = urlencode(params)
            return f"https://www.craigslist.org/search/city/{city}-{state}" + (
                f"?{query_string}" if query_string else ""
            )

    site_url = resolve_craigslist_site(location)
    if category in {
        "ccc", "act", "ats", "kid", "cls", "eve", "grp", "com", "lnw",
        "lnf", "msc", "muc", "pet", "pol", "rid", "rnr", "vol"
    }:
        params["cat"] = category
        query_string = urlencode(params)
        site_name = urlparse(site_url).hostname.split(".")[0]
        return f"{site_url}/search/area/{site_name}" + (
            f"?{query_string}" if query_string else ""
        )

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


def _image_url(element, base_url):
    """Extract a usable image URL from Craigslist result/detail markup."""
    if element is None:
        return None

    for attribute in ("data-img-src", "data-src", "data-original", "src", "content"):
        value = element.get(attribute)
        if value:
            return urljoin(base_url, value.strip())

    srcset = element.get("srcset")
    if srcset:
        candidates = [item.strip().split(" ")[0] for item in srcset.split(",")]
        if candidates:
            return urljoin(base_url, candidates[-1])

    return None


def _listing_image(row, base_url):
    """Find an image from the result markup or Craigslist image metadata."""
    image = row.select_one(
        "img[data-src], img[data-original], img[data-img-src], img[src], "
        ".thumb img, .cl-thumb img, a.result-image img"
    )

    image_url = _image_url(image, base_url)
    if image_url and "images.craigslist.org" in image_url:
        return image_url

    # Craigslist may put the image identifier on the result link instead
    # of rendering an img tag in the raw HTML.
    for element in row.select("[data-ids], [data-id]"):
        raw = element.get("data-ids") or element.get("data-id")
        if not raw:
            continue

        candidate = re.split(r"[,\s]+", raw.strip())[0]

        if ":" in candidate:
            candidate = candidate.rsplit(":", 1)[-1]

        candidate = candidate.split("/")[-1]
        candidate = re.sub(
            r"\.(?:jpg|jpeg|png|webp)$",
            "",
            candidate,
            flags=re.I,
        )

        if re.fullmatch(r"[A-Za-z0-9_-]+", candidate):
            return f"https://images.craigslist.org/{candidate}_300x300.jpg"

    return None

def enrich_missing_images(db, limit=None):
    """Backfill images for stored listings without making a large scrape request."""
    sql = """SELECT id, craigslist_id, listing_url
             FROM craigslist_postings
             WHERE image_url IS NULL OR image_url = ''
             ORDER BY id DESC"""
    params = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (limit,)

    rows = db.execute(sql, params).fetchall()

    enriched = 0
    for row in rows:
        post_url = row["listing_url"]
        if not post_url:
            continue

        try:
            detail = requests.get(
                post_url,
                headers=DEFAULT_HEADERS,
                timeout=15,
            )
            if not detail.ok:
                continue

            ds = BeautifulSoup(detail.text, "html.parser")
            image_url = (
                _image_url(
                    ds.select_one('meta[property="og:image"]'),
                    post_url,
                )
                or _image_url(
                    ds.select_one(
                        ".gallery img, .swipe-wrap img, #thumbs img, "
                        "img[data-img-src], img[data-src]"
                    ),
                    post_url,
                )
            )
            if not image_url:
                continue

            cursor = db.execute(
                """UPDATE craigslist_postings
                   SET image_url=?
                   WHERE id=?
                     AND (image_url IS NULL OR image_url='')""",
                (image_url, row["id"]),
            )
            if cursor.rowcount == 1:
                enriched += 1
        except requests.RequestException:
            continue

    db.commit()
    return enriched


def _jsonld_search_items(soup, base_url):
    """Extract Craigslist search results from its structured JSON-LD when present."""
    script = soup.select_one("script#ld_searchpage_results")
    if not script:
        return []

    try:
        payload = json.loads(script.string or script.get_text())
    except (TypeError, json.JSONDecodeError):
        return []

    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict):
        entries = payload.get("itemListElement") or []
    else:
        entries = []

    results = []
    for entry in entries:
        item = entry.get("item", entry) if isinstance(entry, dict) else {}
        if not isinstance(item, dict):
            continue
        title = item.get("name") or item.get("headline")
        url = item.get("url")
        if not title or not url:
            continue

        offers = item.get("offers") if isinstance(item.get("offers"), dict) else {}
        price = offers.get("price")
        price_text = None if price in (None, "") else str(price)
        image = item.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        address = item.get("address")
        location = None
        if isinstance(address, dict):
            location = address.get("addressLocality") or address.get("name")
        elif isinstance(address, str):
            location = address

        posted = item.get("datePosted") or item.get("datePublished")
        results.append({
            "title": str(title).strip(),
            "url": urljoin(base_url, str(url)),
            "price_text": price_text,
            "location": location,
            "posted_at": _posted_at(str(posted)) if posted else None,
            "image_url": urljoin(base_url, image) if image else None,
        })
    return results


def _html_search_rows(soup):
    """Find current and legacy Craigslist result containers."""
    rows = soup.select(
        ".cl-search-result, li.cl-search-result, li.cl-static-search-result, "
        ".result-row, li[data-pid], [data-pid].cl-search-result"
    )
    if rows:
        return rows

    rows = []
    seen_nodes = set()
    for link in soup.select('a[href*="/d/"], a[href*="/view/d/"]'):
        node = link.find_parent(["li", "article", "div"])
        if node is not None and id(node) not in seen_nodes:
            seen_nodes.add(id(node))
            rows.append(node)
    return rows


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
    structured = _jsonld_search_items(soup, target_url)
    rows = _html_search_rows(soup)
    print(f"Craigslist structured results found: {len(structured)}")
    print(f"Craigslist result rows found: {len(rows)}")

    listings, seen = [], set()
    detail_enrichment_limit = 25

    def add_listing(cid, title, post_url, price_text=None, location=None,
                    posted=None, image_url=None):
        if not cid or cid in known or cid in seen or not title:
            return False
        seen.add(cid)

        description = None
        if post_url and len(listings) < detail_enrichment_limit:
            try:
                detail = requests.get(post_url, headers=DEFAULT_HEADERS, timeout=15)
                if detail.ok:
                    ds = BeautifulSoup(detail.text, "html.parser")
                    if not image_url:
                        image_url = (
                            _image_url(ds.select_one('meta[property="og:image"]'), target_url)
                            or _image_url(
                                ds.select_one(
                                    ".gallery img, .swipe-wrap img, #thumbs img, "
                                    "img[data-img-src], img[data-src]"
                                ),
                                target_url,
                            )
                        )
                    body = ds.select_one("#postingbody, .postingbody")
                    desc = ds.select_one(
                        'meta[property="og:description"], meta[name="description"]'
                    )
                    description = _description(
                        body.get_text(" ", strip=True)
                        if body else (desc.get("content") if desc else None)
                    )
                    address = ds.select_one(".mapaddress")
                    if address and not location:
                        location = address.get_text(" ", strip=True)
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
        return True

    # JSON-LD is the preferred source on current Craigslist search pages.
    for item in structured:
        post_url = item["url"]
        cid_match = re.search(r"(\\d{8,})(?:\\.html)?$", urlparse(post_url).path)
        cid = cid_match.group(1) if cid_match else None
        if not cid:
            cid = _listing_id(BeautifulSoup("", "html.parser"), post_url)
        add_listing(
            cid,
            item["title"],
            post_url,
            item.get("price_text"),
            item.get("location"),
            item.get("posted_at"),
            item.get("image_url"),
        )
        if max_results is not None and len(listings) >= max_results:
            break

    # Community, pets, jobs, gigs, and services may not expose JSON-LD.
    # Fall back to the rendered search-result markup for those categories.
    if max_results is None or len(listings) < max_results:
        for row in rows:
            title_el = row.select_one(
                ".posting-title a, a.posting-title, .result-title, .titlestring, .title, a[href*='/d/'], a[href*='/view/d/']"
            )
            if not title_el:
                continue
            title = title_el.get_text(" ", strip=True)
            if not title or "modem" in title.lower():
                continue

            link = row.select_one(
                "a.posting-title, .posting-title a, a.result-title, a[href*='/d/'], a[href*='/view/d/'], a[href]"
            )
            post_url = urljoin(target_url, link.get("href", "")) if link else ""
            cid = _listing_id(row, post_url)
            if not cid:
                match = re.search(r"(\\d{8,})(?:\\.html)?$", urlparse(post_url).path)
                cid = match.group(1) if match else None

            time_el = row.select_one("time, .result-posted-date, .result-date")
            posted = _posted_at(time_el.get("datetime") if time_el else None)
            price_el = row.select_one(".priceinfo, .result-price, .price")
            location_el = row.select_one(
                ".result-location, .result-hood, .meta .result-hood, .nearby, .location"
            )
            price_text = price_el.get_text(strip=True) if price_el else None
            location = location_el.get_text(" ", strip=True).strip(" ()") if location_el else None
            image_url = _listing_image(row, target_url)

            add_listing(cid, title, post_url, price_text, location, posted, image_url)
            if max_results is not None and len(listings) >= max_results:
                break

    return listings


def store_listing(listing, db):
    cursor = db.execute(
        """INSERT INTO craigslist_postings
           (craigslist_id,title,price_text,price_amount,location,
            listing_url,category,search_query,posted_at,image_url,description)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT (craigslist_id) DO NOTHING""",
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

        enriched = enrich_missing_images(db)
        if enriched:
            print(f"Image enrichment: {enriched} stored listings updated.")

        return inserted

