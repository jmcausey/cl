import hashlib
import json
import re
import unicodedata
import uuid
from urllib.parse import urlparse


AUTO_CODES = {
    "aut", "sna", "pta", "wta", "ava", "bpa", "boo", "cta",
    "hva", "mpa", "mca", "rva", "tra",
}
COMMUNITY_CODES = {
    "ccc", "act", "ats", "kid", "cls", "eve", "grp", "vnn", "laf",
    "mis", "muc", "pet", "pol", "rid", "rnr", "vol", "com",
}
SECTION_NAMES = {
    "sss": "For Sale",
    "aut": "Autos",
    "ccc": "Community",
    "bbb": "Services",
    "jjj": "Jobs",
    "hhh": "Housing",
    "ggg": "Gigs",
    "res": "Resumes",
}

COUNTRY_CODES = {
    "united states": "US", "canada": "CA", "austria": "AT", "belgium": "BE",
    "bulgaria": "BG", "croatia": "HR", "czech republic": "CZ", "denmark": "DK",
    "finland": "FI", "france": "FR", "germany": "DE", "greece": "GR",
    "hungary": "HU", "iceland": "IS", "ireland": "IE", "italy": "IT",
    "luxembourg": "LU", "netherlands": "NL", "norway": "NO", "poland": "PL",
    "portugal": "PT", "romania": "RO", "russian federation": "RU", "spain": "ES",
    "sweden": "SE", "switzerland": "CH", "turkey": "TR", "ukraine": "UA",
    "united kingdom": "GB", "bangladesh": "BD", "china": "CN", "guam / micronesia": "GU",
    "hong kong": "HK", "india": "IN", "indonesia": "ID", "iran": "IR", "iraq": "IQ",
    "israel and palestine": "IL", "japan": "JP", "korea": "KR", "kuwait": "KW",
    "lebanon": "LB", "malaysia": "MY", "pakistan": "PK", "philippines": "PH",
    "singapore": "SG", "taiwan": "TW", "thailand": "TH", "united arab emirates": "AE",
    "vietnam": "VN", "australia": "AU", "new zealand": "NZ", "argentina": "AR",
    "bolivia": "BO", "brazil": "BR", "chile": "CL", "colombia": "CO",
    "costa rica": "CR", "dominican republic": "DO", "ecuador": "EC",
    "el salvador": "SV", "guatemala": "GT", "mexico": "MX", "nicaragua": "NI",
    "panama": "PA", "peru": "PE", "puerto rico": "PR", "uruguay": "UY",
    "venezuela": "VE", "virgin islands, u.s.": "VI", "egypt": "EG", "ethiopia": "ET",
    "ghana": "GH", "kenya": "KE", "morocco": "MA", "south africa": "ZA",
    "tunisia": "TN",
}

PUBLIC_POSTINGS_QUERY = """
    SELECT p.id, p.external_id AS craigslist_id, p.title, p.price_text,
           p.price AS price_amount, COALESCE(sr.name, r.name) AS location,
           p.source_url AS listing_url, c.name AS category, p.search_query,
           p.posted_at, p.created_at AS scraped_at, m.url AS image_url,
           p.body AS description,
           CASE
               WHEN p.status = 'deleted' THEN 'hidden'
               WHEN p.status = 'draft' THEN 'unpublished'
               WHEN p.review_status IS NOT NULL THEN p.review_status
               ELSE 'published'
           END AS status
    FROM postings p
    JOIN regions r ON r.id = p.region_id
    LEFT JOIN subregions sr ON sr.id = p.subregion_id
    JOIN categories c ON c.id = p.category_id
    LEFT JOIN media m ON m.posting_id = p.id AND m.is_primary = TRUE
    WHERE p.source = 'craigslist' AND p.status = 'active'
"""


def category_section(code):
    if code in COMMUNITY_CODES:
        return "ccc"
    if code in AUTO_CODES:
        return "aut"
    if code in SECTION_NAMES and code != "sss":
        return code
    return "sss"


def seed_taxonomy(db):
    from .scraper import CATEGORY_LABELS, normalize_category

    for route_prefix, name in SECTION_NAMES.items():
        db.execute(
            """INSERT INTO sections (name, route_prefix) VALUES (?, ?)
               ON CONFLICT (route_prefix) DO UPDATE SET name=EXCLUDED.name""",
            (name, route_prefix),
        )

    categories = {}
    for raw_code, label in CATEGORY_LABELS.items():
        code = normalize_category(raw_code)
        categories.setdefault(code, label)

    for code, label in categories.items():
        section_prefix = category_section(code)
        section = db.execute(
            "SELECT id FROM sections WHERE route_prefix = ?", (section_prefix,)
        ).fetchone()
        db.execute(
            """INSERT INTO categories (section_id, name, short_code)
               VALUES (?, ?, ?)
               ON CONFLICT (section_id, short_code) DO UPDATE SET name=EXCLUDED.name""",
            (section["id"], label, code),
        )


def _region_subdomain(region_url):
    parsed = urlparse(region_url or "")
    hostname = (parsed.hostname or "").lower()
    if hostname in {"www.craigslist.org", "craigslist.org"}:
        match = re.search(r"/search/area/([^/]+)", parsed.path)
        return match.group(1).lower() if match else "legacy"
    if hostname.endswith(".craigslist.org"):
        return hostname[: -len(".craigslist.org")]
    return "legacy"


def _region_directory_entry(subdomain):
    from .scraper import _craigslist_sites

    try:
        sites = _craigslist_sites()
    except Exception:
        return None
    for site in sites:
        if _region_subdomain(site["url"]) == subdomain:
            return site
    return None


def _subregion_code(name):
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    if len(slug) > 20:
        suffix = hashlib.sha1(name.encode("utf-8")).hexdigest()[:5]
        slug = slug[:14].rstrip("-") + "-" + suffix
    return slug or "unknown"


def ensure_region(db, region_url, location=None):
    subdomain = _region_subdomain(region_url)
    directory_entry = _region_directory_entry(subdomain) if subdomain != "legacy" else None
    region_name = directory_entry["name"] if directory_entry else subdomain.replace("-", " ").title()
    country_name = directory_entry.get("country", "") if directory_entry else ""
    country_code = COUNTRY_CODES.get(country_name.lower(), "ZZ")
    db.execute(
        """INSERT INTO regions (name, subdomain, country_code, timezone)
           VALUES (?, ?, ?, 'UTC') ON CONFLICT (subdomain) DO NOTHING""",
        (region_name[:100], subdomain[:63], country_code),
    )
    region = db.execute(
        "SELECT id FROM regions WHERE subdomain = ?", (subdomain[:63],)
    ).fetchone()
    subregion_id = None
    if location and str(location).strip():
        name = str(location).strip()[:100]
        code = _subregion_code(name)
        db.execute(
            """INSERT INTO subregions (region_id, name, code) VALUES (?, ?, ?)
               ON CONFLICT (region_id, code) DO NOTHING""",
            (region["id"], name, code),
        )
        subregion = db.execute(
            "SELECT id FROM subregions WHERE region_id = ? AND code = ?",
            (region["id"], code),
        ).fetchone()
        subregion_id = subregion["id"]
    return region["id"], subregion_id


def ensure_category(db, category_code):
    from .scraper import CATEGORY_LABELS, normalize_category

    code = normalize_category(category_code)
    label = next(
        (label for raw_code, label in CATEGORY_LABELS.items()
         if normalize_category(raw_code) == code),
        code,
    )
    section_prefix = category_section(code)
    section = db.execute(
        "SELECT id FROM sections WHERE route_prefix = ?", (section_prefix,)
    ).fetchone()
    if section is None:
        db.execute(
            "INSERT INTO sections (name, route_prefix) VALUES (?, ?) "
            "ON CONFLICT (route_prefix) DO NOTHING",
            (SECTION_NAMES[section_prefix], section_prefix),
        )
        section = db.execute(
            "SELECT id FROM sections WHERE route_prefix = ?", (section_prefix,)
        ).fetchone()
    db.execute(
        """INSERT INTO categories (section_id, name, short_code)
           VALUES (?, ?, ?)
           ON CONFLICT (section_id, short_code) DO UPDATE SET name=EXCLUDED.name""",
        (section["id"], label, code),
    )
    category = db.execute(
        "SELECT id FROM categories WHERE section_id = ? AND short_code = ?",
        (section["id"], code),
    ).fetchone()
    return category["id"]


def store_posting_image(db, posting_id, image_url):
    if not image_url:
        return
    db.execute(
        "UPDATE media SET is_primary = FALSE WHERE posting_id = ? AND is_primary = TRUE AND url != ?",
        (posting_id, image_url),
    )
    db.execute(
        """INSERT INTO media (posting_id, url, display_order, is_primary)
           VALUES (?, ?, 0, TRUE)
           ON CONFLICT (posting_id, url) DO UPDATE SET is_primary=TRUE""",
        (posting_id, image_url),
    )


def store_posting(db, listing, region_url=None, post_to_blog=True, status=None, review_status=None):
    from .scraper import normalize_category

    category_code = normalize_category(listing.get("category_code") or listing.get("category"))
    category_id = ensure_category(db, category_code)
    region_id, subregion_id = ensure_region(db, region_url, listing.get("location"))
    posting_status = status or ("active" if post_to_blog else "draft")
    body = listing.get("description") or listing["title"]
    attributes = json.dumps(listing.get("attributes") or {})
    attributes_expression = "CAST(? AS JSONB)" if getattr(db, "postgres", False) else "?"
    created_at_expression = (
        "COALESCE(CAST(? AS TIMESTAMPTZ), CURRENT_TIMESTAMP)"
        if getattr(db, "postgres", False)
        else "COALESCE(?, CURRENT_TIMESTAMP)"
    )
    cursor = db.execute(
        f"""INSERT INTO postings
            (uuid, region_id, subregion_id, category_id, title, body, price,
             status, attributes, source, external_id, source_url, search_query,
             price_text, posted_at, review_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, {attributes_expression}, 'craigslist', ?, ?, ?, ?, ?, ?,
                    {created_at_expression})
            ON CONFLICT (source, external_id) DO NOTHING""",
        (
            str(uuid.uuid4()), region_id, subregion_id, category_id,
            str(listing["title"])[:255], body, listing.get("price_amount"),
            posting_status, attributes, str(listing["craigslist_id"]),
            listing["listing_url"], listing.get("search_query"), listing.get("price_text"),
            listing.get("posted_at"), review_status, listing.get("scraped_at"),
        ),
    )
    inserted = cursor.rowcount == 1
    posting = db.execute(
        "SELECT id, status FROM postings WHERE source = 'craigslist' AND external_id = ?",
        (str(listing["craigslist_id"]),),
    ).fetchone()
    if not inserted and status is None and post_to_blog and posting["status"] == "draft":
        db.execute("UPDATE postings SET status = 'active' WHERE id = ?", (posting["id"],))
    store_posting_image(db, posting["id"], listing.get("image_url"))
    return inserted


def has_legacy_postings_table(db):
    if getattr(db, "postgres", False):
        row = db.execute("SELECT to_regclass('craigslist_postings') AS table_name").fetchone()
        return row["table_name"] is not None
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='craigslist_postings'"
    ).fetchone() is not None


def migrate_legacy_postings(db):
    if not has_legacy_postings_table(db):
        return 0

    rows = db.execute("SELECT * FROM craigslist_postings ORDER BY id").fetchall()
    migrated = 0
    for row in rows:
        old_status = row["status"] if "status" in row.keys() else "published"
        posting_status = {
            "hidden": "deleted",
            "unpublished": "draft",
        }.get(old_status, "active")
        review_status = old_status if old_status in {"pending", "completed"} else None
        listing = {
            "craigslist_id": row["craigslist_id"],
            "title": row["title"],
            "description": row["description"] if "description" in row.keys() else None,
            "price_amount": row["price_amount"] if "price_amount" in row.keys() else None,
            "price_text": row["price_text"] if "price_text" in row.keys() else None,
            "location": row["location"] if "location" in row.keys() else None,
            "category": row["category"] if "category" in row.keys() else "sss",
            "search_query": row["search_query"] if "search_query" in row.keys() else None,
            "posted_at": row["posted_at"] if "posted_at" in row.keys() else None,
            "scraped_at": row["scraped_at"] if "scraped_at" in row.keys() else None,
            "image_url": row["image_url"] if "image_url" in row.keys() else None,
            "listing_url": row["listing_url"],
        }
        migrated += store_posting(
            db, listing, status=posting_status, review_status=review_status
        )

    db.execute("DROP TABLE craigslist_postings")
    return migrated
