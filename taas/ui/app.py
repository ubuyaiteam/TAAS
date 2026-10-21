"""The screens of TAAS (CustomTkinter).

Screens: Setup -> Input -> Check details -> Article -> Result.
Slow jobs run in a background thread, so the window never freezes.
"""

import queue  # hands results from the background job to the window
import threading  # run slow jobs in the background
import webbrowser  # open web pages

import customtkinter as ctk  # the screen toolkit

from ..errors import TaasError  # our error types
from ..workflow import Workflow  # all the steps behind the screens

APP_TITLE = "TAAS - Tool for Automatic Article Submission"
RED, GREEN = "#c0392b", "#1e8449"  # colors for errors and good news
NEUTRAL = ("gray10", "gray90")  # normal text color (light mode, dark mode); None is not allowed by the toolkit
WRAP = 820  # where long text wraps (pixels)
POLL_MS = 150  # how often the window checks for a finished job
DRAFT_CHOICE, LIVE_CHOICE = "Save as Blogger draft", "Publish live"


class App(ctk.CTk):
    """The window. It keeps the current data and switches screens."""

    def __init__(self, workflow=None, auto_check=False):
        super().__init__()
        self.workflow = workflow or Workflow()
        self.title(f"{APP_TITLE}  (v{self.workflow.version})")
        self.geometry("980x780")
        self.minsize(860, 640)

        # data shared by the screens
        self.last_input = None  # what the user typed on the Input screen
        self.analysis = None  # result of reading the pages
        self.draft = None  # the article being reviewed
        self.result = None  # ("ok", PostResult) or ("error", text)
        self.busy = False

        # top bar: screen name and Setup button
        top = self.top_bar = ctk.CTkFrame(self)
        top.pack(fill="x", padx=12, pady=(12, 0))
        self.step_label = ctk.CTkLabel(top, text="", font=ctk.CTkFont(size=16, weight="bold"))
        self.step_label.pack(side="left", padx=10, pady=8)
        ctk.CTkButton(top, text="Setup", width=90, command=self.open_setup).pack(side="right", padx=10, pady=8)
        ctk.CTkButton(top, text="Check for updates", width=140, command=self.on_check_updates).pack(side="right", pady=8)
        ctk.CTkLabel(top, text=f"v{self.workflow.version}").pack(side="right", padx=10, pady=8)

        # a notice that appears only when a newer version was released
        self.update_bar = ctk.CTkFrame(self)
        self.update_label = ctk.CTkLabel(self.update_bar, text="", anchor="w")
        self.update_label.pack(side="left", padx=10, pady=6)
        self.update_info = None
        self.update_button = ctk.CTkButton(self.update_bar, text="Open download page", width=160,
                                           command=self.on_open_download)
        self.update_button.pack(side="right", padx=10, pady=6)

        # one line that says "Working..." while a job runs
        self.status = ctk.CTkLabel(self, text="", anchor="w")
        self.status.pack(fill="x", padx=22, pady=(6, 0))

        # the area where screens appear
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=12, pady=12)
        self.screen = None
        self.show(SetupScreen if self.workflow.missing_setup() else InputScreen)

        # look for a new version quietly when the app starts (only when it is set up)
        if auto_check and self.workflow.update_check_ready():
            self.run_task(self.workflow.check_for_update, self.after_quiet_check, "", background=True)

    # Show a screen (the old one is removed)
    def show(self, screen_class):
        if self.screen is not None:
            self.screen.destroy()
        self.screen = screen_class(self.body, self)
        self.screen.pack(fill="both", expand=True)
        self.step_label.configure(text=screen_class.TITLE)

    # Open Setup (ignored while a job runs)
    def open_setup(self):
        if not self.busy:
            self.show(SetupScreen)

    # Show or clear the "Working..." line
    def set_busy(self, text):
        self.busy = bool(text)
        self.status.configure(text=text)

    # Run a slow job in the background, then call on_done(kind, value)
    # kind is "ok" (value = the job's result) or "error" (value = text to show)
    # background=True: a quiet job that does not block the buttons or show "Working..."
    def run_task(self, work, on_done, message, background=False):
        if self.busy and not background:
            return
        if not background:
            self.set_busy(message)
        results = queue.Queue()

        def job():
            try:
                results.put(("ok", work()))
            except TaasError as error:
                results.put(("error", str(error)))  # our own errors are already plain language
            except Exception as error:  # anything unexpected
                results.put(("error", f"Something unexpected went wrong: {error}"))

        threading.Thread(target=job, daemon=True).start()

        # the window checks for the answer every fraction of a second
        def poll():
            try:
                kind, value = results.get_nowait()
            except queue.Empty:
                self.after(POLL_MS, poll)
                return
            if not background:
                self.set_busy("")
            on_done(kind, value)

        self.after(POLL_MS, poll)

    # The user pressed "Check for updates"
    def on_check_updates(self):
        self.run_task(self.workflow.check_for_update, self.after_manual_check, "Looking for a new version...")

    def after_manual_check(self, kind, value):
        if kind == "error":
            self.show_info("Check for updates", value)
            return
        self.apply_update_info(value)
        text = value.message()
        if value.newer and value.notes:
            text += "\n\nWhat is new:\n" + value.notes
        self.show_info("Check for updates", text)

    # The quiet check at start-up: speak up only when there is news
    def after_quiet_check(self, kind, value):
        if kind == "ok":
            self.apply_update_info(value)

    # Show or hide the "new version" notice
    def apply_update_info(self, info):
        self.update_info = info
        if info.newer:
            self.update_label.configure(text=f"New version {info.latest} is available (you have {info.current}).")
            self.update_bar.pack(fill="x", padx=12, pady=(6, 0), after=self.top_bar)
        else:
            self.update_bar.pack_forget()

    def on_open_download(self):
        if self.update_info:
            self.workflow.open_download_page(self.update_info)

    # Tell the user something in a pop-up
    def show_info(self, title, message):
        from tkinter import messagebox  # imported here so the file loads without a display
        messagebox.showinfo(title, message)

    # Ask a yes/no question in a pop-up
    def ask_yes_no(self, title, message):
        from tkinter import messagebox  # imported here so the file loads without a display
        return messagebox.askyesno(title, message)


class Screen(ctk.CTkFrame):
    """Base for all screens: a scrolling page plus a message line."""

    TITLE = ""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.workflow = app.workflow
        self.page = ctk.CTkScrollableFrame(self)
        self.page.pack(fill="both", expand=True)
        self.message = None
        self.build()

    def build(self):
        raise NotImplementedError

    # A big title
    def heading(self, text):
        ctk.CTkLabel(self.page, text=text, font=ctk.CTkFont(size=20, weight="bold"), anchor="w").pack(
            fill="x", padx=10, pady=(10, 4))

    # A section title
    def section(self, text):
        ctk.CTkLabel(self.page, text=text, font=ctk.CTkFont(size=15, weight="bold"), anchor="w").pack(
            fill="x", padx=10, pady=(16, 2))

    # A normal line of text
    def text(self, text, color=None):
        label = ctk.CTkLabel(self.page, text=text, anchor="w", justify="left", wraplength=WRAP)
        if color:
            label.configure(text_color=color)
        label.pack(fill="x", padx=10, pady=2)
        return label

    # A label with a one-line entry box under it; returns the entry
    def field(self, label, value="", show=None, width=420, placeholder=""):
        ctk.CTkLabel(self.page, text=label, anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        options = {"width": width}
        if show:
            options["show"] = show
        if placeholder:
            options["placeholder_text"] = placeholder
        entry = ctk.CTkEntry(self.page, **options)
        if value:
            entry.insert(0, value)
        entry.pack(anchor="w", padx=10, pady=2)
        return entry

    # A button
    def button(self, text, command, width=170):
        button = ctk.CTkButton(self.page, text=text, command=command, width=width)
        button.pack(anchor="w", padx=10, pady=6)
        return button

    # The line where errors and good news appear (create it once, at the place you want it)
    def make_message(self):
        self.message = ctk.CTkLabel(self.page, text="", anchor="w", justify="left", wraplength=WRAP)
        self.message.pack(fill="x", padx=10, pady=6)

    # Show a message (red = problem, green = good news)
    def say(self, text, ok=False):
        self.message.configure(text=text, text_color=GREEN if ok else RED)


# ------------------------------------------------------------------ Setup

class SetupScreen(Screen):
    TITLE = "Setup"

    def build(self):
        s = self.workflow.settings
        self.heading("Setup")

        # --- Gemini and article settings ---
        self.section("1. Gemini and article settings")
        self.key = self.field("Gemini API key", s.gemini_api_key, show="*")
        self.model = self.field("Gemini model", s.gemini_model)
        self.min_words = self.field("Shortest article (words)", str(s.min_words), width=120)
        self.max_words = self.field("Longest article (words)", str(s.max_words), width=120)
        self.limit = self.field("Posting limit per day (leave empty for no limit)",
                                "" if s.post_limit_per_day is None else str(s.post_limit_per_day), width=120)
        self.button("Save settings", self.on_save)

        # --- Google account ---
        self.section("2. Google account")
        self.google_status = self.text("")
        self.button("Sign in with Google", self.on_sign_in)
        self.button("Use another Google account", self.on_switch)
        self.refresh_google()

        # --- blog ---
        self.section("3. Your blog")
        self.blogs = {}  # menu text -> blog id
        self.blog_menu = ctk.CTkOptionMenu(self.page, values=["(sign in, then load your blogs)"],
                                           command=self.on_blog_chosen, width=420)
        self.blog_menu.pack(anchor="w", padx=10, pady=4)
        if s.blog_id:
            self.blog_menu.set(f"Saved blog (id {s.blog_id})")
        self.button("Load my blogs", self.on_load_blogs)

        self.make_message()
        self.button("Continue", self.on_continue)

    # Save the settings; returns True when saved
    def on_save(self):
        try:
            self.workflow.save_settings(self.key.get(), self.model.get(), self.min_words.get(),
                                        self.max_words.get(), self.limit.get())
        except TaasError as error:
            self.say(str(error))
            return False
        self.say("Settings saved.", ok=True)
        return True

    # Update the Google status text
    def refresh_google(self):
        ok, note = self.workflow.client_file_status()
        signed = "Signed in." if self.workflow.is_signed_in() else "Not signed in."
        if ok:
            self.google_status.configure(text=f"{note} {signed}", text_color=GREEN if signed == "Signed in." else NEUTRAL)
        else:
            path = self.workflow.settings.client_secret_path()
            self.google_status.configure(text=f"{note}\nPlace client_secret.json here: {path}", text_color=RED)

    # Sign in, then load the blogs
    def on_sign_in(self):
        self.app.run_task(self.workflow.sign_in, self.after_sign_in, "Waiting for you to sign in in the browser...")

    # Forget the account and sign in again
    def on_switch(self):
        def work():
            self.workflow.sign_out()
            self.workflow.sign_in()
        self.app.run_task(work, self.after_sign_in, "Waiting for you to sign in in the browser...")

    def after_sign_in(self, kind, value):
        self.refresh_google()
        if kind == "error":
            self.say(value)
            return
        self.say("Signed in.", ok=True)
        self.on_load_blogs()

    # Ask Blogger for the user's blogs
    def on_load_blogs(self):
        self.app.run_task(self.workflow.list_blogs, self.after_blogs, "Loading your blogs...")

    def after_blogs(self, kind, value):
        if kind == "error":
            self.say(value)
            return
        if not value:
            self.say("No blogs were found on this Google account. Create one on Blogger first.")
            return
        self.blogs = {f"{b.name} ({b.url})": b.id for b in value}
        labels = list(self.blogs)
        self.blog_menu.configure(values=labels)
        current = [l for l, i in self.blogs.items() if i == self.workflow.settings.blog_id]
        if current:
            self.blog_menu.set(current[0])
        elif len(labels) == 1:
            self.blog_menu.set(labels[0])
            self.on_blog_chosen(labels[0])
        else:
            self.blog_menu.set("(choose your blog)")
        self.say(f"Found {len(labels)} blog(s).", ok=True)

    # The user picked a blog
    def on_blog_chosen(self, label):
        blog_id = self.blogs.get(label)
        if blog_id:
            self.workflow.select_blog(blog_id)
            self.say("Blog saved.", ok=True)

    # Go on when everything is ready
    def on_continue(self):
        if not self.on_save():
            return
        missing = self.workflow.missing_setup()
        if missing:
            self.say("Not ready yet:\n- " + "\n- ".join(missing))
            return
        self.app.show(InputScreen)


# ------------------------------------------------------------------ Input

class InputScreen(Screen):
    TITLE = "Step 1 of 4: Addresses and keywords"

    def build(self):
        saved_urls, saved_keywords = self.app.last_input or (["", "", ""], "")
        self.heading("Step 1: Your web addresses and keywords")
        self.text("Enter 2 or 3 web addresses. Each one becomes one link in the article.")
        self.urls = [
            self.field(f"Web address {n}" + (" (optional)" if n == 3 else ""),
                       saved_urls[n - 1] if n <= len(saved_urls) else "", width=640, placeholder="https://")
            for n in (1, 2, 3)
        ]
        ctk.CTkLabel(self.page, text="Keywords: 5 to 10, one per line or separated by commas", anchor="w").pack(
            fill="x", padx=10, pady=(14, 0))
        self.keywords = ctk.CTkTextbox(self.page, height=140, width=640, wrap="word")
        self.keywords.pack(anchor="w", padx=10, pady=2)
        if saved_keywords:
            self.keywords.insert("1.0", saved_keywords)
        self.make_message()
        self.button("Read the pages", self.on_read)

    def on_read(self):
        urls = [e.get() for e in self.urls]
        keywords = self.keywords.get("1.0", "end")
        self.app.last_input = (urls, keywords.strip())
        self.say("")
        self.app.run_task(lambda: self.workflow.analyze(urls, keywords), self.after_read,
                          "Reading the pages and detecting details. This can take a minute...")

    def after_read(self, kind, value):
        if kind == "error":
            self.say(value)
            return
        self.app.analysis = value
        self.app.show(DetailsScreen)


# ---------------------------------------------------------------- Details

class DetailsScreen(Screen):
    TITLE = "Step 2 of 4: Check the details"

    def build(self):
        analysis = self.app.analysis
        self.heading("Step 2: Check what was found")
        self.text("Correct anything that is wrong. Brand names are only used to keep them out of the article.")
        self.brands, self.notes = [], []
        for item in analysis.analyses:
            self.text(item.url)
            d = item.detection
            if d.error:
                self.text(d.error, RED)
            else:
                self.text("Page read." + (" It had very little text, so check the values." if d.thin else ""), GREEN)
            self.brands.append(self.field("Brand name on this page", d.brand, width=420))
            self.notes.append(self.field("About this page (optional: helps when the page cannot be read)", d.note, width=720))
        self.section("For the whole article")
        self.category = self.field("Category", analysis.category, width=420)
        self.country = self.field("Country", analysis.country, width=420)
        self.make_message()
        row = ctk.CTkFrame(self.page, fg_color="transparent")
        row.pack(anchor="w", padx=10, pady=6)
        ctk.CTkButton(row, text="Back", width=100, command=self.on_back).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Write the article", width=170, command=self.on_write).pack(side="left")

    # Keep what the user typed, so coming back to this screen shows it again
    def keep_edits(self):
        analysis = self.app.analysis
        for item, entry, note in zip(analysis.analyses, self.brands, self.notes):
            item.detection.brand = entry.get().strip()
            item.detection.note = note.get().strip()
        analysis.category = self.category.get().strip()
        analysis.country = self.country.get().strip()

    def on_back(self):
        self.keep_edits()
        self.app.show(InputScreen)

    def on_write(self):
        self.keep_edits()
        brands = [e.get() for e in self.brands]
        category, country = self.category.get(), self.country.get()
        self.say("")
        self.app.run_task(lambda: self.workflow.generate(self.app.analysis, category, country, brands),
                          self.after_write, "Writing the article. This can take a minute or two...")

    def after_write(self, kind, value):
        if kind == "error":
            self.say(value)
            return
        self.app.draft = value
        self.app.show(ArticleScreen)


# ---------------------------------------------------------------- Article

class ArticleScreen(Screen):
    TITLE = "Step 3 of 4: Read, edit and post"

    def build(self):
        draft = self.app.draft
        self.heading("Step 3: Read and edit the article")
        self.info = self.text("")
        self.title_entry = self.field("Title", draft.title, width=720)
        ctk.CTkLabel(self.page, text="Article text", anchor="w").pack(fill="x", padx=10, pady=(10, 0))
        self.body = ctk.CTkTextbox(self.page, height=380, width=720, wrap="word")
        self.body.pack(anchor="w", padx=10, pady=2)
        self.text("Square brackets [like this] mark a link. Start a line with ## for a subheading "
                  "and with - for a list item. Leave an empty line between paragraphs.")

        # --- pictures ---
        self.section("Images")
        self.text("Blogger cannot take files from this app, so a picture must already be on the internet. "
                  "Paste its web address and a short description. Click in the article where it should go, "
                  "then press Add image. It is placed after the paragraph you clicked in. "
                  "A picture shows in the text as a line like {image: https://... | description}; "
                  "delete that line to remove the picture.")
        self.image_url = self.field("Image web address", width=640, placeholder="https://")
        self.image_alt = self.field("Image description (what the picture shows)", width=640)
        row = ctk.CTkFrame(self.page, fg_color="transparent")
        row.pack(anchor="w", padx=10, pady=6)
        ctk.CTkButton(row, text="Add image", width=130, command=self.on_add_image).pack(side="left", padx=(0, 8))
        # not ready yet: shown so the team can see what is coming, but it cannot be clicked
        self.generate_images_button = ctk.CTkButton(row, text="Generate images automatically (coming soon)",
                                                    width=300, state="disabled")
        self.generate_images_button.pack(side="left")
        self.image_note = ctk.CTkLabel(self.page, text="", anchor="w", justify="left", wraplength=WRAP)
        self.image_note.pack(fill="x", padx=10, pady=2)

        # --- which keyword is the link text for each address ---
        self.section("Links")
        self.menus = []
        for i, link in enumerate(draft.links):
            self.text(f"Link {i + 1}: {link.url}")
            menu = ctk.CTkOptionMenu(self.page, values=list(draft.keywords), width=320,
                                     command=lambda value, i=i: self.on_anchor(i, value))
            menu.pack(anchor="w", padx=10, pady=2)
            self.menus.append(menu)

        # --- checks ---
        self.section("Checks")
        self.checks = self.text("")
        row = ctk.CTkFrame(self.page, fg_color="transparent")
        row.pack(anchor="w", padx=10, pady=6)
        ctk.CTkButton(row, text="Check again", width=130, command=self.on_check).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Write it again", width=130, command=self.on_rewrite).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Back", width=100, command=self.on_back).pack(side="left")

        # --- post ---
        self.section("Post to Blogger")
        self.mode = ctk.CTkSegmentedButton(self.page, values=[DRAFT_CHOICE, LIVE_CHOICE])
        self.mode.set(DRAFT_CHOICE)
        self.mode.pack(anchor="w", padx=10, pady=4)
        self.confirm = ctk.CTkCheckBox(self.page, text="I have read the article and the links, and it can be posted.",
                                       command=self.on_confirm_changed)
        self.confirm.pack(anchor="w", padx=10, pady=4)
        self.make_message()
        self.post_button = ctk.CTkButton(self.page, text="Post to Blogger", width=170, command=self.on_post, state="disabled")
        self.post_button.pack(anchor="w", padx=10, pady=6)

        self.fill(draft)

    # Put the draft into the boxes
    def fill(self, draft):
        self.title_entry.delete(0, "end")
        self.title_entry.insert(0, draft.title)
        self.body.delete("1.0", "end")
        self.body.insert("1.0", draft.text)
        for menu, link in zip(self.menus, draft.links):
            menu.set(link.anchor)
        self.show_report(draft.report)

    # Show the check result
    def show_report(self, report):
        draft = self.app.draft
        tries = f" | written in {draft.attempts} {'try' if draft.attempts == 1 else 'tries'}" if draft.attempts else ""
        self.info.configure(text=f"{report.words} words (allowed {draft.min_words} to {draft.max_words}){tries}")
        if report.passed:
            self.checks.configure(text="All checks passed.", text_color=GREEN)
        else:
            self.checks.configure(
                text="Please look at these:\n" + "\n".join(f"- {p}" for p in report.problems), text_color=RED)

    def current(self):
        return self.title_entry.get().strip(), self.body.get("1.0", "end").strip()

    # Put a picture line into the article text, after the paragraph the cursor is in
    def on_add_image(self):
        try:
            line = self.workflow.image_line(self.image_url.get(), self.image_alt.get())
        except TaasError as error:
            self.image_note.configure(text=str(error), text_color=RED)
            return
        self.body.insert("insert lineend", "\n\n" + line + "\n\n")
        self.image_url.delete(0, "end")
        self.image_alt.delete(0, "end")
        self.image_note.configure(text="Image added to the article text.", text_color=GREEN)
        self.on_check()

    # Go back to the details (the article text on screen is kept in the draft)
    def on_back(self):
        title, text = self.current()
        self.workflow.recheck(self.app.draft, title, text)
        self.app.show(DetailsScreen)

    # Run the checks on what is on screen
    def on_check(self):
        title, text = self.current()
        _, report = self.workflow.recheck(self.app.draft, title, text)
        self.show_report(report)

    # The user chose another keyword for a link
    def on_anchor(self, index, value):
        draft = self.app.draft
        title, text = self.current()
        try:
            new_text = self.workflow.change_anchor(draft, text, index, value)
        except TaasError as error:
            self.menus[index].set(draft.links[index].anchor)  # put the old choice back
            self.say(str(error))
            return
        self.body.delete("1.0", "end")
        self.body.insert("1.0", new_text)
        self.say("")
        self.on_check()

    # Write a new article (replaces the text on screen)
    def on_rewrite(self):
        if not self.app.ask_yes_no("Write it again", "This replaces the text on screen with a new article. Continue?"):
            return
        self.say("")
        self.app.run_task(lambda: self.workflow.regenerate(self.app.draft), self.after_rewrite,
                          "Writing the article again. This can take a minute or two...")

    def after_rewrite(self, kind, value):
        if kind == "error":
            self.say(value)
            return
        self.fill(value)

    # The post button works only while the box is ticked
    def on_confirm_changed(self):
        self.post_button.configure(state="normal" if self.confirm.get() else "disabled")

    def on_post(self):
        if not self.confirm.get():
            self.say("Tick the box to confirm you have read the article.")
            return
        title, text = self.current()
        live = self.mode.get() == LIVE_CHOICE
        draft = self.app.draft
        self.say("")
        warnings = self.workflow.warnings_before_post(draft, title, text)
        self.show_report(draft.report)
        if warnings and not self.app.ask_yes_no("Before posting", "\n\n".join(warnings) + "\n\nPost anyway?"):
            return
        if live and not self.app.ask_yes_no("Publish live", "This publishes the article on your blog now. Continue?"):
            return
        self.app.run_task(lambda: self.workflow.post(draft, title, text, live, True), self.after_post,
                          "Posting to Blogger...")

    def after_post(self, kind, value):
        self.app.result = (kind, value)
        self.app.show(ResultScreen)


# ----------------------------------------------------------------- Result

class ResultScreen(Screen):
    TITLE = "Step 4 of 4: Result"

    def build(self):
        kind, value = self.app.result
        if kind == "error":
            self.heading("The article was not posted")
            self.text(value, RED)
            self.button("Back to the article", lambda: self.app.show(ArticleScreen))
            return

        self.heading("Done")
        self.text("Saved as a Blogger draft." if not value.live else "Published on your blog.", GREEN)
        if value.url:
            self.link = self.field("Link to the post", value.url, width=640)
            row = ctk.CTkFrame(self.page, fg_color="transparent")
            row.pack(anchor="w", padx=10, pady=6)
            ctk.CTkButton(row, text="Copy link", width=120, command=self.on_copy).pack(side="left", padx=(0, 8))
            ctk.CTkButton(row, text="Open in browser", width=150, command=lambda: webbrowser.open(value.url)).pack(side="left")
        else:
            self.text("Open Blogger to see your post.")
        self.button("Write another article", self.on_again)

    def on_copy(self):
        self.app.clipboard_clear()
        self.app.clipboard_append(self.link.get())

    # Start again with empty boxes
    def on_again(self):
        self.app.last_input = self.app.analysis = self.app.draft = self.app.result = None
        self.app.show(InputScreen)


# Start the app
def run():
    ctk.set_appearance_mode("system")  # follow the Windows light or dark mode
    ctk.set_default_color_theme("blue")
    App(auto_check=True).mainloop()
