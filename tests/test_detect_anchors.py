import json  # write JSON answers
import unittest  # test tools

from taas import anchors, detect  # the code being tested
from taas.errors import ConfigError, GeminiError, PageReadError  # our error types
from taas.pagereader import PageInfo  # a read page

from tests.helpers import FakeGemini  # fake Gemini


# A page with enough text
def page(url="https://acme.in/desks", title="Standing desks", description="Desks for homes", text="Good desks. " * 30):
    return PageInfo(url=url, host="acme.in", title=title, description=description, text=text, lang="en")


# A fake page reader: returns pages or errors by address
def reader_for(mapping):
    def read(url, http):
        item = mapping[url]
        if isinstance(item, Exception):
            raise item
        return item
    return read


def answer(brand="Acme", category="office furniture", country="India"):
    return json.dumps({"brand": brand, "category": category, "country": country})


# Tests for detecting brand, category and country
class DetectTests(unittest.TestCase):
    def test_detects_values_and_sends_hints(self):
        gem = FakeGemini(answer())
        result = detect.analyze_url("u1", gem, reader=reader_for({"u1": page()}))
        d = result.detection
        self.assertEqual((d.brand, d.category, d.country, d.error), ("Acme", "office furniture", "India", ""))
        prompt = gem.calls[0]["prompt"]
        self.assertIn("Domain ending: in", prompt)
        self.assertIn("Never guess", gem.calls[0]["system"])
        self.assertTrue(gem.calls[0]["json_mode"])

    def test_unreadable_page_gives_manual_entry_message(self):
        gem = FakeGemini()
        result = detect.analyze_url("u1", gem, reader=reader_for({"u1": PageReadError("u1 was not found (HTTP 404).")}))
        self.assertIsNone(result.page)
        self.assertIn("Type the details by hand", result.detection.error)
        self.assertEqual(gem.calls, [])  # Gemini was not asked

    def test_empty_page_is_not_guessed(self):
        gem = FakeGemini()
        empty = PageInfo(url="u1", thin=True)
        result = detect.analyze_url("u1", gem, reader=reader_for({"u1": empty}))
        self.assertIn("JavaScript", result.detection.error)
        self.assertEqual(gem.calls, [])

    def test_bad_gemini_answer_is_saved_as_error(self):
        result = detect.analyze_url("u1", FakeGemini("not json"), reader=reader_for({"u1": page()}))
        self.assertIn("by hand", result.detection.error)
        self.assertEqual(result.detection.brand, "")

    def test_wrong_key_stops_everything(self):
        with self.assertRaises(ConfigError):
            detect.analyze_url("u1", FakeGemini(ConfigError("bad key")), reader=reader_for({"u1": page()}))

    def test_one_failure_does_not_stop_the_others(self):
        gem = FakeGemini(answer())
        results = detect.analyze_urls(["u1", "u2"], gem, reader=reader_for({"u1": PageReadError("down"), "u2": page()}))
        self.assertTrue(results[0].detection.error)
        self.assertEqual(results[1].detection.brand, "Acme")

    def test_non_text_values_become_empty(self):
        bad = json.dumps({"brand": 5, "category": None, "country": ["x"]})
        d = detect.analyze_url("u1", FakeGemini(bad), reader=reader_for({"u1": page()})).detection
        self.assertEqual((d.brand, d.category, d.country), ("", "", ""))

    def test_summarize_picks_most_common(self):
        make = lambda b, c, k: detect.UrlAnalysis("u", None, detect.Detection("u", b, c, k))
        analyses = [make("A", "Desks", "India"), make("B", "desks", ""), make("", "Chairs", "India")]
        category, country, brands = detect.summarize(analyses)
        self.assertEqual((category.lower(), country, brands), ("desks", "India", ["A", "B"]))
        self.assertEqual(detect.summarize([make("", "", "")]), ("", "", []))


KEYWORDS = ["great deals", "home office", "desk setup", "budget tips", "buying guide"]


# Tests for choosing the link keywords
class AnchorTests(unittest.TestCase):
    def test_gemini_choice_is_used(self):
        gem = FakeGemini(json.dumps({"anchors": ["Buying Guide", "great deals"]}))
        got = anchors.choose_anchors(KEYWORDS, ["https://a.com/guide", "https://b.com"], [None, None], gem)
        self.assertEqual(got, ["buying guide", "great deals"])  # keywords exactly as typed

    def test_bad_answers_fall_back_to_overlap(self):
        urls = ["https://a.com/budget-tips", "https://b.com/home-office"]
        for bad in ("not json", json.dumps({"anchors": ["x", "y"]}), json.dumps({"anchors": ["great deals", "great deals"]}),
                    json.dumps({"anchors": ["great deals"]}), GeminiError("down")):
            got = anchors.choose_anchors(KEYWORDS, urls, [None, None], FakeGemini(bad))
            self.assertEqual(got, ["budget tips", "home office"])

    def test_overlap_without_gemini(self):
        p1 = page(title="Great deals on desks", description="")
        p2 = page(title="Plan your home office", description="")
        got = anchors.choose_anchors(KEYWORDS, ["https://a.com", "https://b.com"], [p1, p2])
        self.assertEqual(got, ["great deals", "home office"])

    def test_keywords_are_never_used_twice(self):
        got = anchors.choose_anchors(KEYWORDS, ["https://a.com", "https://b.com", "https://c.com"], [None] * 3)
        self.assertEqual(len(set(got)), 3)

    def test_wrong_key_stops_everything(self):
        with self.assertRaises(ConfigError):
            anchors.choose_anchors(KEYWORDS, ["https://a.com", "https://b.com"], [None, None], FakeGemini(ConfigError("key")))


if __name__ == "__main__":
    unittest.main()
