import unittest
import sqlite3
from bs4 import BeautifulSoup
from unittest.mock import Mock, patch

from cl.scraper import (
    CATEGORY_ALIASES,
    CATEGORY_LABELS,
    _craigslist_sites,
    _listing_id,
    _listing_image,
    base_location_search_url,
    craigslist_locations,
    normalize_category,
    store_listing,
)


class CategoryNormalizationTests(unittest.TestCase):
    def test_accepts_category_slugs(self):
        self.assertEqual(normalize_category("zip"), "zip")

    def test_maps_legacy_car_category_to_craigslist_code(self):
        self.assertEqual(normalize_category("car"), "cta")

    def test_category_options_and_legacy_values_build_canonical_urls(self):
        categories = {
            **CATEGORY_ALIASES,
            **{
                code: CATEGORY_ALIASES.get(code, code)
                for code in CATEGORY_LABELS
            },
            "community": "ccc",
        }
        site_url = "https://dallas.craigslist.org"
        for category, canonical in categories.items():
            with self.subTest(category=category):
                self.assertEqual(normalize_category(category), canonical)
                self.assertEqual(
                    base_location_search_url(site_url, category=category),
                    f"{site_url}/search/{canonical}",
                )
        for code, label in CATEGORY_LABELS.items():
            canonical = CATEGORY_ALIASES.get(code, code)
            with self.subTest(label=label):
                self.assertEqual(normalize_category(code), canonical)
                self.assertEqual(normalize_category(label), canonical)

    def test_accepts_free_label(self):
        self.assertEqual(normalize_category("free"), "zip")

    def test_accepts_free_label_with_mixed_case(self):
        self.assertEqual(normalize_category("Free"), "zip")

    def test_extracts_static_result_id_from_hash_style_url(self):
        url = "https://www.craigslist.org/view/d/dallas-old-kenmore-dryer/vvR8cDYSv344rAhPc9eUGo"
        self.assertEqual(_listing_id({}, url), "vvR8cDYSv344rAhPc9eUGo")

    def test_extracts_image_from_data_img_src(self):
        row = BeautifulSoup(
            '<li><img data-img-src="//images.craigslist.org/photo_300x300.jpg"></li>',
            "html.parser",
        )
        self.assertEqual(
            _listing_image(row, "https://example.craigslist.org/search/sss"),
            "https://images.craigslist.org/photo_300x300.jpg",
        )

    def test_location_directory_groups_countries_states_and_sites(self):
        response = Mock()
        response.text = """
            <h2>US</h2><h4>Texas</h4>
            <a href="/area/austin">Austin</a>
            <h2>Europe</h2><h4>France</h4>
            <a href="/area/paris">Paris</a>
            <a href="/about/help">Help</a>
        """
        _craigslist_sites.cache_clear()
        try:
            with patch("cl.scraper.requests.get", return_value=response):
                locations = craigslist_locations()
        finally:
            _craigslist_sites.cache_clear()

        countries = {country["name"]: country for country in locations}
        texas = countries["United States"]["states"][0]
        france = countries["France"]["states"][0]
        self.assertEqual(texas["name"], "Texas")
        self.assertEqual(texas["cities"][0], {
            "name": "Austin",
            "url": "https://austin.craigslist.org",
        })
        self.assertEqual(france["name"], "")
        self.assertEqual(france["cities"][0]["name"], "Paris")

    def test_selected_site_builds_search_url_on_canonical_regional_host(self):
        self.assertEqual(
            base_location_search_url(
                "https://austin.craigslist.org", category="boa", query="boat"
            ),
            "https://austin.craigslist.org/search/boo?query=boat",
        )

    def test_community_category_uses_valid_category_search_route(self):
        self.assertEqual(
            base_location_search_url(
                "https://easttexas.craigslist.org",
                category="pet",
                query="husky",
                radius=120,
            ),
            "https://easttexas.craigslist.org/search/pet?query=husky&search_distance=120",
        )

    def test_cars_and_trucks_search_uses_craigslist_category_code(self):
        self.assertEqual(
            base_location_search_url(
                "https://dallas.craigslist.org",
                category="car",
                query="ford ranger",
                radius=100,
            ),
            "https://dallas.craigslist.org/search/cta?query=ford+ranger&search_distance=100",
        )

    def test_unpublished_listing_can_be_published_by_later_job(self):
        db = sqlite3.connect(":memory:")
        db.execute(
            """CREATE TABLE craigslist_postings (
                   id INTEGER PRIMARY KEY,
                   craigslist_id TEXT NOT NULL UNIQUE,
                   title TEXT NOT NULL,
                   price_text TEXT,
                   price_amount REAL,
                   location TEXT,
                   listing_url TEXT NOT NULL,
                   category TEXT,
                   search_query TEXT,
                   posted_at TEXT,
                   image_url TEXT,
                   description TEXT,
                   status TEXT NOT NULL DEFAULT 'published'
               )"""
        )
        listing = {
            "craigslist_id": "listing-1",
            "title": "Test listing",
            "listing_url": "https://example.craigslist.org/listing-1",
        }

        self.assertTrue(store_listing(listing, db, post_to_blog=False))
        status = db.execute(
            "SELECT status FROM craigslist_postings WHERE craigslist_id=?",
            (listing["craigslist_id"],),
        ).fetchone()[0]
        self.assertEqual(status, "unpublished")

        self.assertFalse(store_listing(listing, db, post_to_blog=True))
        status = db.execute(
            "SELECT status FROM craigslist_postings WHERE craigslist_id=?",
            (listing["craigslist_id"],),
        ).fetchone()[0]
        self.assertEqual(status, "published")

        store_listing(listing, db, post_to_blog=False)
        status = db.execute(
            "SELECT status FROM craigslist_postings WHERE craigslist_id=?",
            (listing["craigslist_id"],),
        ).fetchone()[0]
        self.assertEqual(status, "published")


if __name__ == "__main__":
    unittest.main()
