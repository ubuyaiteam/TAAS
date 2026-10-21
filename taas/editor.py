"""Phase 4: turn the article into plain text the user can edit, and back into HTML.

In the editable text:
  ## Heading      = a subheading
  - item          = a list item
  [keyword]       = a link (square brackets mark the link text)
  {image: https://address | description}  = a picture (its own line)
  blank line      = new paragraph
"""

import html  # make text safe inside HTML
import re  # find patterns in text

from bs4 import BeautifulSoup  # read HTML

from .article import assemble  # turns link markers into real links
from .errors import ValidationError  # our error types
from .inputs import normalize_url  # check a web address

IMAGE_LINE = re.compile(r"^\{image:\s*(.*?)\s*\}$", re.DOTALL)  # one picture line
IMAGE_LINE_ANYWHERE = re.compile(r"(?m)^[ \t]*(\{image:[^\n]*\})[ \t]*$")  # picture lines inside a longer text


# Text inside one tag; a link <a> becomes [text]
def _inline(tag):
    parts = []
    for child in tag.children:
        name = getattr(child, "name", None)
        if name == "a":
            parts.append(f"[{child.get_text()}]")
        elif name is None:
            parts.append(str(child))  # plain text
        else:
            parts.append(_inline(child))
    return re.sub(r"\s+", " ", "".join(parts)).strip()


# Article HTML -> editable text
def html_to_text(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    blocks = []
    for el in soup.children:
        name = getattr(el, "name", None)
        if name is None:
            continue
        if name == "h2":
            blocks.append("## " + _inline(el))
        elif el.find("img") and not el.get_text(strip=True):  # a block that holds only pictures
            blocks.extend(f"{{image: {i.get('src', '')} | {i.get('alt', '')}}}" for i in el.find_all("img"))
        elif name in ("ul", "ol"):
            blocks.append("\n".join("- " + _inline(li) for li in el.find_all("li")))
        else:
            blocks.append(_inline(el))
    return "\n\n".join(b for b in blocks if b.strip("# -"))


# Editable text -> (article HTML, notes for the user)
def text_to_html(text, links):
    by_anchor = {l.anchor.lower(): i for i, l in enumerate(links, 1)}
    used, notes = set(), []

    # one piece of text: [anchor] becomes a link marker the first time only
    def inline(raw):
        safe = html.escape(raw, quote=False)

        def replace(match):
            inner = match.group(1)
            number = by_anchor.get(inner.strip().lower())
            if number and number not in used:
                used.add(number)
                return f"[[L{number}]]{inner}[[/L{number}]]"
            notes.append(f"'[{inner}]' is not a link here, so the brackets were removed.")
            return inner

        return re.sub(r"\[([^\[\]]+)\]", replace, safe)

    parts, pictures = [], 0
    text = IMAGE_LINE_ANYWHERE.sub(r"\n\n\1\n\n", text.strip())  # a picture line is always its own block
    for block in [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        picture = IMAGE_LINE.match(block)
        if picture:
            pictures += 1
            tag, note = _image_html(picture, pictures)
            if note:
                notes.append(note)
            if tag:
                parts.append(tag)
        elif block.startswith("## "):
            parts.append("<h2>" + inline(" ".join(lines)[3:].strip()) + "</h2>")
        elif all(l.startswith("- ") for l in lines):
            parts.append("<ul>" + "".join(f"<li>{inline(l[2:].strip())}</li>" for l in lines) + "</ul>")
        else:
            parts.append("<p>" + inline(" ".join(lines)) + "</p>")

    final_html, _ = assemble("".join(parts), links)
    for number, link in enumerate(links, 1):
        if number not in used:
            notes.append(
                f"The link text '[{link.anchor}]' is missing. Put the keyword in [square brackets] "
                f"where it should link to {link.url}."
            )
    return final_html, notes


# Make a different keyword the link text (the old link becomes plain text)
def swap_anchor(text, old, new):
    # 1. remove the brackets around the old link text
    text = re.sub(r"\[" + re.escape(old) + r"\]", lambda m: m.group(0)[1:-1], text, count=1, flags=re.IGNORECASE)
    # 2. put brackets around the first plain use of the new keyword
    pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(new) + r"(?![A-Za-z0-9])", re.IGNORECASE)
    for match in pattern.finditer(text):
        before = text[:match.start()]
        if before.count("[") == before.count("]"):  # not already inside brackets
            return text[:match.start()] + "[" + match.group(0) + "]" + text[match.end():]
    raise ValidationError(
        f"The keyword '{new}' is not in the text, so it cannot become a link. Add it to the text first."
    )


# The one line that stands for a picture; raises ValidationError when the address is not usable
def make_image_line(url, alt=""):
    address = normalize_url(url)  # must be http or https
    if any(c in address for c in "{}|"):
        raise ValidationError("The image address cannot contain the characters { } or |.")
    description = re.sub(r"[{}|\r\n]+", " ", alt or "")
    description = re.sub(r"\s+", " ", description).strip()
    return f"{{image: {address} | {description}}}"


# One picture line -> (HTML, note); the HTML is empty when the line is not usable
def _image_html(match, number):
    inner = match.group(1)
    address, _, alt = inner.partition("|")
    address, alt = address.strip(), alt.strip()
    try:
        address = normalize_url(address)
    except ValidationError:
        return "", f"Picture {number} was left out: its web address must start with https://."
    tag = (
        f'<p style="text-align: center;"><img src="{html.escape(address, quote=True)}" '
        f'alt="{html.escape(alt, quote=True)}" style="max-width: 100%; height: auto;" /></p>'
    )
    note = "" if alt else f"Picture {number} has no description. A short description helps readers and search engines."
    return tag, note
