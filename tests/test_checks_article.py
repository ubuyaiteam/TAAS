import random  # fixed random numbers for tests
import unittest  # test tools

from taas import article, checks  # the code being tested
from taas.errors import ConfigError, GeminiError, ValidationError  # our error types

from tests.helpers import FakeGemini, KEYWORDS, URLS, make_body, reply, sample_links  # test helpers


# Build the final HTML (markers turned into links)
def final_html(body=None, links=None):
    html_text, problems = article.assemble(body if body is not None else make_body(), links or sample_links())
    assert not problems, problems
    return html_text


def run(html_text, title="A helpful guide", keywords=KEYWORDS, forbidden=("Acme", "shop-one.example.com"), lo=300, hi=400):
    return checks.run_checks(html_text, title, keywords, sample_links(), list(forbidden), lo, hi)


# Tests for the automatic checks
class CheckTests(unittest.TestCase):
    def test_a_good_article_passes(self):
        report = run(final_html())
        self.assertEqual(report.problems, [])
        self.assertTrue(report.passed)
        self.assertTrue(300 <= report.words <= 400)

    def assert_problem(self, report, text):
        self.assertFalse(report.passed)
        self.assertTrue(any(text in p for p in report.problems), report.problems)

    def test_length(self):
        self.assert_problem(run(final_html(make_body(target=200))), "words")
        self.assert_problem(run(final_html(make_body(target=480))), "words")

    def test_missing_keyword(self):
        self.assert_problem(run(final_html(), keywords=KEYWORDS + ["extra word"]), "'extra word' is missing")

    def test_keyword_used_too_often(self):
        body = make_body().replace("</p><h2>First", " home office home office home office home office</p><h2>First", 1)
        self.assert_problem(run(final_html(body)), "'home office' is used")

    def test_extra_or_missing_links(self):
        extra = final_html().replace("</p><h2>First", ' <a href="https://x.com">x</a></p><h2>First', 1)
        self.assert_problem(run(extra), "exactly 2")
        body = make_body().replace("[[L2]]buying guide[[/L2]]", "buying guide")
        html_text, problems = article.assemble(body, sample_links())
        self.assertTrue(problems)  # the missing marker is reported when assembling

    def test_wrong_link_text(self):
        html_text = final_html().replace(">great deals</a>", ">click here</a>")
        self.assert_problem(run(html_text), "must use the text 'great deals'")

    def test_web_address_in_text(self):
        body = make_body().replace("</p><h2>First", " Visit https://x.com today</p><h2>First", 1)
        self.assert_problem(run(final_html(body)), "web address")

    def test_brand_or_domain_name(self):
        body = make_body().replace("</p><h2>First", " Acme is nice</p><h2>First", 1)
        self.assert_problem(run(final_html(body)), "'Acme'")
        self.assert_problem(run(final_html(), title="Acme guide"), "'Acme'")

    def test_link_addresses_may_contain_the_domain(self):
        self.assertTrue(run(final_html()).passed)  # shop-one.example.com is in a link but is not shown text

    def test_headings(self):
        self.assert_problem(run(final_html().replace("<h2>Second part</h2>", "")), "subheadings")

    def test_title(self):
        self.assert_problem(run(final_html(), title="  "), "no title")

    def test_repeated_phrase(self):
        body = make_body().replace("</p><h2>First", " blue green yellow red. blue green yellow red. blue green yellow red.</p><h2>First", 1)
        self.assert_problem(run(final_html(body), lo=1, hi=1000), "repeated")

    def test_stock_phrase(self):
        body = make_body().replace("</p><h2>First", " Let us delve into it.</p><h2>First", 1)
        self.assert_problem(run(final_html(body), lo=1, hi=1000), "stock phrase")


# Tests for putting links in
class AssembleTests(unittest.TestCase):
    def test_markers_become_links(self):
        out, problems = article.assemble("<p>a [[L1]]great deals[[/L1]] b [[L2]]buying guide[[/L2]]</p>", sample_links())
        self.assertEqual(problems, [])
        self.assertIn(f'<a href="{URLS[0]}">great deals</a>', out)
        self.assertIn(f'<a href="{URLS[1]}">buying guide</a>', out)

    def test_marker_twice_or_leftover(self):
        _, problems = article.assemble("<p>[[L1]]a[[/L1]] [[L1]]b[[/L1]] [[L2]]c[[/L2]]</p>", sample_links())
        self.assertTrue(any("marker 1" in p for p in problems))
        out, problems = article.assemble("<p>[[L1]]a[[/L1]] [[L2]]c[[/L2]] [[L7]]x</p>", sample_links())
        self.assertTrue(problems)
        self.assertNotIn("[[", out)

    def test_special_characters_in_address(self):
        links = [article.Link('https://a.com/?x=1&y="2"\\1', "great deals"), article.Link("https://b.com", "buying guide")]
        out, _ = article.assemble("<p>[[L1]]great deals[[/L1]] [[L2]]buying guide[[/L2]]</p>", links)
        self.assertIn("&amp;", out)
        self.assertNotIn('"2"', out)


def request(**kw):
    base = dict(keywords=list(KEYWORDS), links=sample_links(), category="office furniture", country="India",
                page_notes=["Acme sells desks at acme.com"], forbidden=["Acme", "shop-one.example.com"])
    base.update(kw)
    return article.ArticleRequest(**base)


# Tests for the request checks
class RequestTests(unittest.TestCase):
    def test_valid_request_is_cleaned(self):
        req = request(links=[article.Link(URLS[0], "GREAT DEALS"), article.Link(URLS[1], "buying guide")])
        article.validate_request(req)
        self.assertEqual(req.links[0].anchor, "great deals")  # the keyword exactly as typed

    def test_bad_requests(self):
        cases = [
            request(links=sample_links()[:1]),
            request(links=[article.Link(URLS[0], "not a keyword"), article.Link(URLS[1], "buying guide")]),
            request(links=[article.Link(URLS[0], "great deals"), article.Link(URLS[1], "Great Deals")]),
            request(links=[article.Link("nope", "great deals"), article.Link(URLS[1], "buying guide")]),
            request(keywords=KEYWORDS[:3]),
            request(min_words=500, max_words=400),
        ]
        for req in cases:
            with self.assertRaises(ValidationError):
                article.validate_request(req)


# Tests for the writing steps
class PipelineTests(unittest.TestCase):
    def go(self, gem, **kw):
        return article.generate_article(request(), gem, rng=random.Random(3), **kw)

    def test_first_try_passes_and_humanized_version_is_used(self):
        gem = FakeGemini(reply(), reply("A kinder title"))
        result = self.go(gem)
        self.assertTrue(result.report.passed)
        self.assertEqual((result.attempts, result.humanized, result.title), (1, True, "A kinder title"))
        self.assertEqual(len(gem.calls), 2)
        self.assertEqual(result.html.count("<a "), 2)

    def test_humanize_that_breaks_the_links_is_ignored(self):
        broken = make_body().replace("[[L1]]", "").replace("[[/L1]]", "")
        result = self.go(FakeGemini(reply(), reply(body=broken)))
        self.assertTrue(result.report.passed)
        self.assertFalse(result.humanized)

    def test_humanize_error_keeps_the_first_version(self):
        result = self.go(FakeGemini(reply(), GeminiError("busy")))
        self.assertTrue(result.report.passed)
        self.assertFalse(result.humanized)

    def test_humanize_can_be_turned_off(self):
        gem = FakeGemini(reply())
        self.go(gem, humanize=False)
        self.assertEqual(len(gem.calls), 1)

    def test_failed_check_leads_to_a_retry_with_the_problems(self):
        short = reply(body=make_body(target=200))
        gem = FakeGemini(short, short, reply(), reply())
        result = self.go(gem)
        self.assertTrue(result.report.passed)
        self.assertEqual(result.attempts, 2)
        self.assertIn("Your last try had these problems", gem.calls[2]["prompt"])
        self.assertIn("words", gem.calls[2]["prompt"])

    def test_all_tries_fail_gives_the_best_version_with_problems(self):
        short = reply(body=make_body(target=200))
        result = self.go(FakeGemini(*([short] * 6)))
        self.assertFalse(result.report.passed)
        self.assertEqual(result.attempts, 3)
        self.assertTrue(result.report.problems)

    def test_gemini_errors_in_all_tries_are_raised(self):
        with self.assertRaises(GeminiError):
            self.go(FakeGemini(GeminiError("a"), GeminiError("b"), GeminiError("c")))

    def test_one_error_then_success(self):
        result = self.go(FakeGemini(GeminiError("a"), reply(), reply()))
        self.assertTrue(result.report.passed)
        self.assertEqual(result.attempts, 2)

    def test_wrong_key_stops_at_once(self):
        with self.assertRaises(ConfigError):
            self.go(FakeGemini(ConfigError("key")))

    def test_incomplete_answer_counts_as_a_failed_try(self):
        with self.assertRaises(GeminiError):
            self.go(FakeGemini('{"title": ""}', '{"body_html": "x"}', "nonsense"))

    def test_links_added_by_gemini_are_removed(self):
        body = make_body().replace("</p><h2>First", ' <a href="https://spam.com">spam</a></p><h2>First', 1)
        result = self.go(FakeGemini(reply(body=body), reply(body=body)))
        self.assertNotIn("spam.com", result.html)
        self.assertTrue(result.report.passed)

    def test_prompt_content(self):
        gem = FakeGemini(reply(), reply())
        self.go(gem)
        prompt = gem.calls[0]["prompt"]
        self.assertNotIn("Acme", prompt)  # brand hidden in the notes
        self.assertNotIn("http", prompt)
        for text in ("[[L1]]great deals[[/L1]]", "[[L2]]buying guide[[/L2]]", "between 300 and 400", "India", "office furniture"):
            self.assertIn(text, prompt)
        self.assertIn("Never mention any brand", gem.calls[0]["system"])
        self.assertTrue(gem.calls[0]["json_mode"])

    def test_articles_vary_between_runs(self):
        seen = set()
        for seed in range(12):
            gem = FakeGemini(reply(), reply())
            article.generate_article(request(), gem, rng=random.Random(seed))
            seen.add([l for l in gem.calls[0]["prompt"].split("\n") if l.startswith("Angle:")][0])
        self.assertGreater(len(seen), 1)

    def test_word_range_is_a_setting(self):
        gem = FakeGemini(reply(body=make_body(target=150)), reply(body=make_body(target=150)))
        result = article.generate_article(request(min_words=100, max_words=200), gem, rng=random.Random(1))
        self.assertTrue(result.report.passed)
        self.assertIn("between 100 and 200", gem.calls[0]["prompt"])


if __name__ == "__main__":
    unittest.main()
