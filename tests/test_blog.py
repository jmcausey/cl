import unittest

from cl.routes import normalize_blog_status


class BlogStatusTests(unittest.TestCase):
    def test_pending_is_normalized(self):
        self.assertEqual(normalize_blog_status("pending"), "pending")

    def test_completed_is_normalized(self):
        self.assertEqual(normalize_blog_status("completed"), "completed")

    def test_invalid_defaults_to_pending(self):
        self.assertEqual(normalize_blog_status("unknown"), "pending")


if __name__ == "__main__":
    unittest.main()
