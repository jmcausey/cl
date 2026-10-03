import unittest

from cl.scraper import _listing_id, normalize_category


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


if __name__ == "__main__":
    unittest.main()
