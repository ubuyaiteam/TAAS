import unittest  # test tools

from taas import htmlutil, inputs, terms  # the code being tested
from taas.errors import ValidationError  # our error types


# Tests for the input checks
class InputTests(unittest.TestCase):
    def test_urls_ok(self):
        self.assertEqual(inputs.validate_urls([" https://a.com/x ", "http://b.com", ""]), ["https://a.com/x", "http://b.com"])

    def test_url_count_and_format(self):
        for bad in (["https://a.com"], ["https://a.com"] * 1 + ["a.com"], ["ftp://a.com", "https://b.com"],
                    ["https://a.com", "https://b.com", "https://c.com", "https://d.com"]):
            with self.assertRaises(ValidationError):
                inputs.validate_urls(bad)

    def test_same_url_twice(self):
        with self.assertRaises(ValidationError):
            inputs.validate_urls(["https://a.com/x", "https://A.com/x/"])

    def test_keywords_ok_and_spaces_cleaned(self):
        out = inputs.validate_keywords(["great   deals", " a b", "c", "d", "e"])
        self.assertEqual(out[0], "great deals")

    def test_keyword_count_and_repeat(self):
        with self.assertRaises(ValidationError):
            inputs.validate_keywords(["a", "b", "c", "d"])
        with self.assertRaises(ValidationError):
            inputs.validate_keywords([str(i) for i in range(11)])
        with self.assertRaises(ValidationError):
            inputs.validate_keywords(["a", "A", "c", "d", "e"])


# Tests for brand and domain terms
class TermTests(unittest.TestCase):
    def test_domain_terms(self):
        self.assertEqual(terms.domain_terms("https://www.shop.example.com/x"), {"shop.example.com", "example"})
        self.assertIn("second-site", terms.domain_terms("https://www.second-site.co.uk/a"))

    def test_short_domain_names_are_skipped(self):
        self.assertNotIn("t", terms.domain_terms("https://t.co/abc"))

    def test_forbidden_terms_join_brands_and_domains(self):
        got = terms.forbidden_terms(["Acme", "", "X"], ["https://acme-shop.com"])
        self.assertIn("Acme", got)
        self.assertIn("acme-shop.com", got)
        self.assertNotIn("X", got)  # too short to block

    def test_whole_word_match(self):
        self.assertTrue(terms.find_term("I like ACME tools", "acme"))
        self.assertFalse(terms.find_term("acmeville", "acme"))

    def test_redact(self):
        self.assertEqual(terms.redact("Buy at Acme now", ["acme"]), "Buy at the store now")


# Tests for the HTML helpers
class HtmlTests(unittest.TestCase):
    def test_sanitize_removes_links_scripts_and_attributes(self):
        raw = '<p class="x">Hi <a href="http://e.com">there</a><script>bad()</script></p><div><h2 id="a">T</h2></div>'
        out = htmlutil.sanitize_html(raw)
        self.assertNotIn("<a", out)
        self.assertNotIn("script", out)
        self.assertNotIn("class", out)
        self.assertNotIn("<div", out)
        self.assertIn("there", out)
        self.assertIn("<h2>T</h2>", out)

    def test_sanitize_keeps_markers(self):
        self.assertIn("[[L1]]deal[[/L1]]", htmlutil.sanitize_html("<p>a [[L1]]deal[[/L1]]</p>"))

    def test_word_count_and_visible_text(self):
        self.assertEqual(htmlutil.visible_text("<p>One  <b>two</b></p><p>three</p>"), "One two three")
        self.assertEqual(htmlutil.count_words("It's a well-known fact, 100%."), 5)


if __name__ == "__main__":
    unittest.main()
