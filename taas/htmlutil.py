"""Small helpers to clean HTML and count words."""

import re  # find patterns in text

from bs4 import BeautifulSoup  # read HTML

ALLOWED_TAGS = {"p", "h2", "ul", "ol", "li", "strong", "em"}  # the only tags kept in articles


# Keep only safe tags and remove all their attributes
def sanitize_html(raw):
    soup = BeautifulSoup(raw, "html.parser")
    # scripts and styles are removed completely
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    for tag in soup.find_all(True):
        if tag.name in ALLOWED_TAGS:
            tag.attrs = {}
        else:
            tag.unwrap()  # drop the tag, keep its text (links are removed here too)
    return str(soup).strip()


# The text a reader sees, without tags
def visible_text(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


# Count words (a word may have ' or - inside)
def count_words(text):
    return len(re.findall(r"[A-Za-z0-9]+(?:['\u2019-][A-Za-z0-9]+)*", text))
