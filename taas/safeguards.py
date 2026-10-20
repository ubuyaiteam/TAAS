"""Phase 4: posting limit and repeat warning.

A tiny local log keeps only the time, blog id, web addresses and draft/live flag of each post.
It never keeps article text. Delete post_log.json to clear it.
"""

import json  # read and write JSON files
import time  # clock and dates
from pathlib import Path  # file paths

from .errors import ValidationError  # our error types

DAY = 86400  # seconds in a day
REPEAT_WINDOW_DAYS = 7  # same web addresses within this many days = warning
LOG_KEEP_DAYS = 30  # older entries are deleted


# Same set of addresses in any order and letter case = same key
def _url_key(urls):
    return sorted(u.strip().lower().rstrip("/") for u in urls)


class PostLog:
    """Remembers recent posts."""

    def __init__(self, path):
        self.path = Path(path)

    # Read the saved entries (a broken file counts as empty)
    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError, UnicodeDecodeError):
            return []
        return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []

    # Add one post and drop old entries
    def record(self, blog_id, urls, live, now):
        entries = [e for e in self._load() if now - e.get("time", 0) < LOG_KEEP_DAYS * DAY]
        entries.append({"time": now, "blog_id": blog_id, "urls": list(urls), "live": bool(live)})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(entries), encoding="utf-8")

    # How many live posts went to this blog in the last 24 hours
    def live_posts_last_day(self, blog_id, now):
        return sum(
            1 for e in self._load()
            if e.get("live") and e.get("blog_id") == blog_id and now - e.get("time", 0) < DAY
        )

    # Stop when the daily limit is used up (no limit = never stops)
    def check_limit(self, limit, blog_id, now):
        if limit is None:
            return
        count = self.live_posts_last_day(blog_id, now)
        if count >= limit:
            raise ValidationError(
                f"Posting limit reached: {count} live post(s) in the last 24 hours (limit {limit}). "
                "Change the limit in Setup, or save this one as a draft."
            )

    # Message if the same web addresses were used recently (else None)
    def repeat_warning(self, urls, now):
        key = _url_key(urls)
        for e in self._load():
            if now - e.get("time", 0) < REPEAT_WINDOW_DAYS * DAY and _url_key(e.get("urls", [])) == key:
                when = time.strftime("%d %b %Y", time.localtime(e["time"]))
                return (
                    f"These web addresses were already used in a post on {when}. "
                    "Posting them again so soon can look like spam."
                )
        return None
