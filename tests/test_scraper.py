import unittest
from bs4 import BeautifulSoup
from unittest.mock import Mock, patch

from cl.scraper import (
    _craigslist_sites,
    _listing_id,
    _listing_image,
    base_location_search_url,
    craigslist_locations,
    normalize_category,
)


class CategoryNormalizationTests(unittest.TestCase):
    def test_accepts_category_slugs(self):
        self.assertEqual(normalize_category("zip"), "zip")

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
            "https://austin.craigslist.org/search/boa?query=boat",
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


if __name__ == "__main__":
    unittest.main()
