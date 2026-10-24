import unittest  # test tools

import phase1_check as check  # the live-check script
from taas.errors import ValidationError  # our error types


# Tests for the link options of the live check
class LinkOptionTests(unittest.TestCase):
    def test_parses_anchor_and_url(self):
        links = check.parse_links(["great deals=https://a.com/x", "buy now=http://b.com"])
        self.assertEqual(links, [("great deals", "https://a.com/x"), ("buy now", "http://b.com")])

    def test_url_may_contain_equals_sign(self):
        links = check.parse_links(["deals=https://a.com/?id=5&x=1"])
        self.assertEqual(links[0][1], "https://a.com/?id=5&x=1")

    def test_bad_options_are_rejected(self):
        for bad in (["no equals sign"], ["=https://a.com"], ["x=ftp://a.com"], ["x=a.com"]):
            with self.assertRaises(ValidationError):
                check.parse_links(bad)

    def test_link_count_must_be_1_to_3(self):
        with self.assertRaises(ValidationError):
            check.parse_links([])
        with self.assertRaises(ValidationError):
            check.parse_links(["a=https://a.com"] * 4)


# Tests for the test-post HTML
class TestHtmlTests(unittest.TestCase):
    def test_one_anchor_tag_per_link(self):
        links = [("great deals", "https://a.com/x"), ("buy now", "https://b.com")]
        html_text = check.build_test_html(links)
        self.assertEqual(html_text.count("<a "), 2)
        self.assertIn('<a href="https://a.com/x">great deals</a>', html_text)

    def test_special_characters_are_escaped(self):
        html_text = check.build_test_html([("a <b> & c", 'https://a.com/?x=1&y="2"')])
        self.assertNotIn("<b>", html_text)
        self.assertIn("&amp;", html_text)
        self.assertNotIn('"2"', html_text)  # the quote cannot break out of href

    def test_links_found_reports_each_link(self):
        links = [("a", "https://a.com/?x=1&y=2"), ("b", "https://b.com")]
        content = check.build_test_html(links[:1])
        self.assertEqual(check.links_found(content, links), [True, False])


if __name__ == "__main__":
    unittest.main()
