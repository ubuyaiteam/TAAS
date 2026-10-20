"""Phase 1 live check. Run on your own PC (needs internet).

    python phase1_check.py                    # sign in, create a DRAFT test post
    python phase1_check.py --live             # publish the test post
    python phase1_check.py --switch-account   # use another Google account
    python phase1_check.py --link "great deals=https://example.com/a" --link "buy now=https://example.com/b"
                                              # test post with 1-3 links (anchor text=web address)
"""

import argparse  # read command options
import html  # make text safe inside HTML
import sys  # exit code

from taas import config  # the code being used or tested
from taas.auth import GoogleAuth, TokenStore, load_client_config, sign_in  # the code being used or tested
from taas.blogger import BloggerClient  # the code being used or tested
from taas.errors import TaasError, ValidationError  # our error types


# Read "anchor text=web address" options into (anchor, url) pairs
def parse_links(raw_links):
    if not 1 <= len(raw_links) <= 3:
        raise ValidationError("Use 1 to 3 --link options.")
    links = []
    for raw in raw_links:
        # split at the FIRST "=", because web addresses can contain "=" too
        anchor, sep, url = raw.partition("=")
        anchor, url = anchor.strip(), url.strip()
        if not sep or not anchor:
            raise ValidationError(f"Use the form \"anchor text=web address\": {raw}")
        if not url.startswith(("http://", "https://")):
            raise ValidationError(f"The web address must start with http:// or https://: {url}")
        links.append((anchor, url))
    return links


# Build the test post: one short sentence per link
def build_test_html(links):
    parts = ["<p>This is a link test created by the TAAS Phase 1 check. You can delete it.</p>"]
    for anchor, url in links:
        # html.escape stops special characters from breaking the HTML
        safe_url = html.escape(url, quote=True)
        safe_anchor = html.escape(anchor)
        parts.append(f'<p>This sentence has the link <a href="{safe_url}">{safe_anchor}</a> in it.</p>')
    return "".join(parts)


# For each link, is its web address in the saved post?
def links_found(content, links):
    return [html.escape(url, quote=True) in content for _, url in links]


# Make printing safe for any letters (the Windows console can fail on some)
def make_console_safe():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


# Run the live check
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="publish instead of saving a draft")
    parser.add_argument(
        "--switch-account", action="store_true",
        help="forget the saved sign-in and sign in with a different Google account",
    )
    parser.add_argument(
        "--link", action="append", metavar="ANCHOR=URL",
        help="add a link to the test post (use 1 to 3 times)",
    )
    args = parser.parse_args()

    make_console_safe()
    try:
        # check the links first, so a typo does not waste a sign-in
        links = parse_links(args.link) if args.link else []
        # read the settings
        settings = config.load_settings()
        # read the Google client file
        client = load_client_config(settings.client_secret_path())
        # where the sign-in is saved
        store = TokenStore(config.token_path())

        # --switch-account: forget the old account first
        if args.switch_account:
            store.clear()
            print("0. Saved sign-in removed. The saved blog is cleared too.")
            config.save_setting(config.KEY_BLOG_ID, "")

        if store.is_signed_in():
            print("1. Already signed in (saved token found).")
        else:
            print("1. Opening your browser for Google sign-in...")
            sign_in(client, store)
            print("   Signed in.")

        # the client asks for a fresh token each time it needs one
        blogger = BloggerClient(GoogleAuth(client, store).access_token)

        blogs = blogger.list_blogs()
        if not blogs:
            print("2. No blogs found on this Google account. Create one on Blogger first.")
            return 1
        print("2. Your blogs:")
        for i, blog in enumerate(blogs, 1):
            print(f"   {i}. {blog.name}  ({blog.url})  id={blog.id}")

        # use the saved blog if it is still on this account
        blog = next((b for b in blogs if b.id == settings.blog_id), None)
        if blog is None:
            choice = input("   Number of the TEST blog to post to: ").strip()
            blog = blogs[int(choice) - 1]
            # remember the blog for next time
            config.save_setting(config.KEY_BLOG_ID, blog.id)
            print(f"   Saved blog id {blog.id} to the .env file.")

        mode = "LIVE" if args.live else "DRAFT"
        print(f"3. Creating a {mode} test post on '{blog.name}'...")
        # with --link the post has links, otherwise it is plain text
        body = build_test_html(links) if links else (
            "<p>This is a test post created by the TAAS Phase 1 check. "
            "You can delete it.</p>"
        )
        post = blogger.create_post(blog.id, "TAAS test post", body, draft=not args.live)
        print(f"   Done. Status: {post.status or 'unknown'}")
        print(f"   Post URL: {post.url or '(Blogger returned no URL for this post)'}")
        if links:
            print("4. Links in the saved post:")
            if not post.content:
                print("   Blogger did not send the content back. Open the post and click each link.")
            else:
                for (anchor, url), found in zip(links, links_found(post.content, links)):
                    print(f"   [{'OK' if found else 'MISSING'}] {anchor} -> {url}")
        print("\nPhase 1 live check passed. Open Blogger and confirm the post is there.")
        return 0
    # show friendly errors only
    except TaasError as error:
        print(f"\nCHECK FAILED: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
