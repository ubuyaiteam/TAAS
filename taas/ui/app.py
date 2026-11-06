"""The screens of TAAS (CustomTkinter).

Layout: a sidebar on the left (the four steps, plus Dark mode, Check for updates and Settings) and the
current screen on the right: a title, a white card with the form, and a bottom line with a message and the
buttons that move you on.

Screens: Setup -> Input -> Check details -> Article -> Result.
Slow jobs run in a background thread, so the window never freezes.
"""

import queue  # hands results from the background job to the window
import re  # a quick look at whether a typed address looks like a web address
import sys  # locate bundled icon resources
import threading  # run slow jobs in the background
import webbrowser  # open web pages
from pathlib import Path  # resolve the logo icon

import customtkinter as ctk  # the screen toolkit
from PIL import Image  # load the sidebar icon variants

from ..errors import TaasError  # our error types
from ..inputs import MAX_KEYWORDS, MAX_URLS, MIN_KEYWORDS, MIN_URLS  # allowed input counts
from ..workflow import Workflow, split_keywords  # all the steps behind the screens

APP_TITLE = "TAAS - Tool for Automatic Article Submission"

# Colors are (light mode, dark mode) pairs, so the Dark mode switch can change them all at once.
PAGE_BG = ("#FFFDF7", "#12131F")  # the page behind everything
SIDEBAR_BG = ("#FFFFFF", "#181A28")
CARD_BG = ("#FFFFFF", "#1C1E2E")  # the white card with the form
FIELD_BG = ("#F5F1E5", "#262940")  # menus, the switch, quiet fills
LINE = ("#E9E3D2", "#33364F")  # thin lines around cards
INPUT_LINE = ("#D9D5CA", "#3F4366")  # the border of entry boxes
INK = ("#20243A", "#F1F2FA")  # main text
MUTED = ("#656879", "#A3A8C4")  # helper text and field labels
PLACEHOLDER = ("#6B7089", "#8A8FB0")
ACCENT = ("#FFB900", "#5B54E8")  # main buttons and the current step
ACCENT_HOVER = ("#E6A700", "#6A63F0")
ACCENT_TEXT = ("#805800", "#B9C5FF")  # readable accent text on light backgrounds
ACCENT_SOFT = ("#F5F1E5", "#2A2C4D")  # the current step's pill, button hover
SELECTED = ("#F5E7B3", "#3E4180")  # the chosen side of the Draft/Live switch
STEP_FILL = ("#F5F1E5", "#2B2E48")  # a step that is still to come
AMBER = "#FFB900"  # the Ubuy yellow
RED = ("#B3261E", "#FF8A80")  # a problem
GREEN = ("#0B7A5E", "#4ADE9F")  # good news
GREEN_SOFT = ("#DDF5EC", "#1C3A31")
WARN = ("#8A5A00", "#FFC857")  # a gentle heads-up (a page that could not be read)
NEUTRAL = INK  # normal text color; None is not allowed by the toolkit

FONT = "Segoe UI"  # a clean Windows font
SIDEBAR_W = 250
WRAP = 580  # where long text wraps (pixels)
POLL_MS = 150  # how often the window checks for a finished job
DRAFT_CHOICE, LIVE_CHOICE = "Save as Blogger draft", "Publish live"
STEPS = ["Add pages", "Check details", "Review article", "Publish"]
MARKET_COUNTRIES = (
    "Netherlands", "Germany", "Italy", "Spain", "France", "Belgium",
    "Saudi Arabia", "Qatar", "United Kingdom", "Ireland", "Kuwait", "Bahrain",
    "Philippines", "Malaysia", "Norway", "Sweden", "Denmark", "Finland",
    "Nigeria", "Kenya", "South Africa", "Canada", "Iceland", "Croatia",
    "Hong Kong", "Singapore", "Australia", "New Zealand", "UAE", "India",
    "Greece", "Brazil",
)


def font(size=13, weight="normal"):
    return ctk.CTkFont(family=FONT, size=size, weight=weight)


# How the buttons look: main = solid indigo, quiet = soft fill, flat = for the sidebar
def main_button(**more):
    return dict(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=(INK[0], "#FFFFFF"),
                text_color_disabled=("#82734D", "#C7C9DD"),
                corner_radius=22, height=42, font=font(14, "bold"), **more)


def quiet_button(**more):
    return dict(fg_color=ACCENT_SOFT, hover_color=SELECTED, text_color=INK, text_color_disabled=MUTED,
                corner_radius=22, height=42, font=font(14, "bold"), **more)


def flat_button(**more):
    return dict(fg_color="transparent", hover_color=FIELD_BG, text_color=INK, anchor="w", corner_radius=12,
                height=38, font=font(14), **more)


# Does what was typed look like a web address? (only a quick, friendly hint)
def looks_like_address(text):
    return bool(re.match(r"^https?://\S+\.\S+$", text.strip()))


class App(ctk.CTk):
    """The window. It keeps the current data and switches screens."""

    def __init__(self, workflow=None, auto_check=False):
        super().__init__()
        self.workflow = workflow or Workflow()
        self.title(f"{APP_TITLE}  (v{self.workflow.version})")
        self.geometry("1100x760")
        self.minsize(980, 660)
        self.configure(fg_color=PAGE_BG)
        self.set_window_icon()

        # data shared by the screens
        self.last_input = None  # what the user typed on the Input screen
        self.last_keyword_seed = ""
        self.analysis = None  # result of reading the pages
        self.draft = None  # the article being reviewed
        self.result = None  # ("ok", PostResult) or ("error", text)
        self.busy = False
        self.dark = False

        self.sidebar_icon_refs = {}
        self.build_sidebar()

        # the right side: a notice, the "Working..." line, and the screen
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(side="left", fill="both", expand=True)

        # a notice that appears only when a newer version was released
        self.update_bar = ctk.CTkFrame(main, fg_color=ACCENT_SOFT, corner_radius=12)
        self.update_label = ctk.CTkLabel(self.update_bar, text="", anchor="w", text_color=INK, font=font(13))
        self.update_label.pack(side="left", padx=14, pady=8)
        self.update_info = None
        self.update_button = ctk.CTkButton(self.update_bar, text="Download installer", width=210,
                                           command=self.on_install_update, **main_button())
        self.update_button.configure(height=34)
        self.update_button.pack(side="right", padx=10, pady=6)

        # one line that says "Working..." while a job runs
        self.status = ctk.CTkLabel(main, text="", anchor="w", text_color=ACCENT_TEXT, font=font(13, "bold"))
        self.status.pack(fill="x", padx=40, pady=(14, 0))

        # the area where screens appear
        self.body = ctk.CTkFrame(main, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=40, pady=(10, 26))
        self.screen = None
        self.show(SetupScreen if self.workflow.missing_setup() else InputScreen)

        # look for a new version quietly when the app starts (only when it is set up)
        if auto_check and self.workflow.update_check_ready():
            self.run_task(self.workflow.check_for_update, self.after_quiet_check, "", background=True)

    def set_window_icon(self):
        if sys.platform != "win32":
            return
        bundle_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
        icon_path = bundle_dir / "assets" / "taas-logo.ico"
        if icon_path.is_file():
            self.iconbitmap(default=str(icon_path))

    # The sidebar: logo, the four steps, and the small buttons at the bottom
    def build_sidebar(self):
        bar = self.sidebar = ctk.CTkFrame(self, width=SIDEBAR_W, fg_color=SIDEBAR_BG, corner_radius=0,
                                          border_width=0)
        bar.pack(side="left", fill="y")
        bar.pack_propagate(False)

        logo = ctk.CTkFrame(bar, fg_color="transparent")
        logo.pack(fill="x", padx=24, pady=(30, 26))
        ctk.CTkLabel(logo, text="✓", fg_color=AMBER, text_color=INK, corner_radius=12, width=40, height=40,
                     font=font(20, "bold")).pack(side="left")
        ctk.CTkLabel(logo, text="TAAS", text_color=INK, font=font(22, "bold")).pack(side="left", padx=12)

        # the four steps
        self.step_rows = []
        for number, name in enumerate(STEPS, start=1):
            row = ctk.CTkFrame(bar, fg_color="transparent", corner_radius=14)
            row.pack(fill="x", padx=14, pady=2)
            circle = ctk.CTkLabel(row, text=str(number), width=28, height=28, corner_radius=14, fg_color=STEP_FILL,
                                  text_color=MUTED, font=font(13, "bold"))
            circle.pack(side="left", padx=(10, 12), pady=10)
            label = ctk.CTkLabel(row, text=name, anchor="w", text_color=MUTED, font=font(15))
            label.pack(side="left", fill="x", expand=True)
            self.step_rows.append((row, circle, label))
            for widget in (row, circle, label):
                widget.bind("<Button-1>", lambda event, step=number: self.on_step_click(event, step))
                widget.configure(cursor="hand2")
            for widget in (row, circle, label):
                widget.bind("<Enter>", lambda event, step=number: self.on_step_hover(step, True))
                widget.bind("<Leave>", lambda event, step=number: self.on_step_hover(step, False))

        self.markets_button = ctk.CTkButton(
            bar, text="Markets", command=self.open_markets, **flat_button()
        )
        self.markets_button.pack(fill="x", padx=14, pady=(12, 0))

        # the small buttons at the bottom
        ctk.CTkFrame(bar, fg_color="transparent").pack(fill="both", expand=True)
        ctk.CTkFrame(bar, height=1, fg_color=LINE, corner_radius=0).pack(fill="x", padx=20)
        self.theme_icon, self.theme_button = self.sidebar_option("moon", "Dark mode", self.on_toggle_theme,
                                                                pady=(12, 0))
        self.sidebar_option("update", "Check for updates", self.on_check_updates)
        self.sidebar_option("settings", "Settings", self.open_setup)
        ctk.CTkLabel(bar, text=f"Version {self.workflow.version}", anchor="w", text_color=MUTED,
                     font=font(12)).pack(fill="x", padx=28, pady=(8, 22))

    def sidebar_option(self, icon, text, command, pady=0):
        row = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=pady)
        icon_label = ctk.CTkLabel(
            row, text="", image=self.sidebar_icon_image(icon), width=28, height=38, text_color=INK
        )
        icon_label.pack(side="left", padx=(8, 2))
        button = ctk.CTkButton(row, text=text, command=command, **flat_button())
        button.pack(side="left", fill="x", expand=True)
        return icon_label, button

    def sidebar_icon_image(self, name):
        image = self.sidebar_icon_refs.get(name)
        if image is None:
            bundle_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
            light_path = bundle_dir / "assets" / f"sidebar_{name}_light.png"
            dark_path = bundle_dir / "assets" / f"sidebar_{name}_dark.png"
            with Image.open(light_path) as light:
                light_image = light.copy()
            with Image.open(dark_path) as dark:
                dark_image = dark.copy()
            image = ctk.CTkImage(light_image=light_image, dark_image=dark_image, size=(24, 24))
            self.sidebar_icon_refs[name] = image
        return image

    # Mark which step the user is on: earlier steps get a tick, later ones stay grey (step 0 = none)
    def set_step(self, current):
        self.current_step = current
        for number, (row, circle, label) in enumerate(self.step_rows, start=1):
            if number < current:  # done
                row.configure(fg_color="transparent")
                circle.configure(text="✓", fg_color=GREEN_SOFT, text_color=GREEN)
                label.configure(text_color=INK, font=font(15))
            elif number == current:  # here
                row.configure(fg_color=ACCENT_SOFT)
                circle.configure(text=str(number), fg_color=ACCENT, text_color=(INK[0], "#FFFFFF"))
                label.configure(text_color=INK, font=font(15, "bold"))
            else:  # still to come
                row.configure(fg_color="transparent")
                circle.configure(text=str(number), fg_color=STEP_FILL, text_color=MUTED)
                label.configure(text_color=MUTED, font=font(15))

    def on_step_hover(self, step, hovered):
        row = self.step_rows[step - 1][0]
        if hovered:
            row.configure(fg_color=ACCENT_SOFT if step == self.current_step else FIELD_BG)
        else:
            self.set_step(self.current_step)

    def on_step_click(self, event, step):
        self.navigate_step(step)
        return "break"

    # Switch between the light and the dark look
    def on_toggle_theme(self):
        self.dark = not self.dark
        ctk.set_appearance_mode("dark" if self.dark else "light")
        self.theme_button.configure(text="Light mode" if self.dark else "Dark mode")
        icon_name = "sun" if self.dark else "moon"
        self.theme_icon.configure(image=self.sidebar_icon_image(icon_name))

    # Show a screen (the old one is removed)
    def show(self, screen_class):
        if self.screen is not None:
            self.screen.destroy()
        self.screen = screen_class(self.body, self)
        self.screen.pack(fill="both", expand=True)
        self.set_step(self.screen.STEP)

    def navigate_step(self, step):
        if self.busy or self.screen is None:
            return

        destinations = {
            1: InputScreen if not self.workflow.missing_setup() else None,
            2: DetailsScreen if self.analysis is not None else None,
            3: ArticleScreen if self.draft is not None else None,
            4: ResultScreen if self.result and self.result[0] == "ok" else None,
        }
        destination = destinations.get(step)
        if destination is None or isinstance(self.screen, destination):
            return

        save = getattr(self.screen, "save_for_navigation", None)
        if save:
            save()
        self.show(destination)

    # Open Setup (ignored while a job runs)
    def open_setup(self):
        if not self.busy:
            self.show(SetupScreen)

    def open_markets(self):
        if not self.busy:
            self.show(MarketsScreen)

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
        if value.newer:
            self.confirm_update(value, text)
        else:
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
            self.update_button.configure(text="Download installer" if info.installer_url else "Open release page")
            self.update_bar.pack(fill="x", padx=40, pady=(22, 0), before=self.status)
        else:
            self.update_bar.pack_forget()

    def on_install_update(self):
        if self.update_info:
            self.confirm_update(self.update_info)

    def confirm_update(self, info, details=""):
        message = details or info.message()
        if info.installer_url:
            message += (
                f"\n\nOpen the download for TAAS_Setup_{info.latest}.exe? "
                "After it downloads, close TAAS and run the installer. Your settings will be kept."
            )
            if self.ask_yes_no("Download TAAS installer", message):
                self.workflow.open_browser(info.installer_url)
            return
        message += (
            f"\n\nThis release does not include TAAS_Setup_{info.latest}.exe. "
            "Open the release page to check for an installer?"
        )
        if self.ask_yes_no("Open TAAS release page", message):
            self.workflow.open_download_page(info)
        return

    def after_update(self, info, kind, value):
        if kind == "error":
            self.show_info("Update failed", str(value))
            if self.ask_yes_no("Manual update", "Open the release page to download TAAS manually?"):
                self.workflow.open_download_page(info)
            return
        self.destroy()

    # Tell the user something in a pop-up
    def show_info(self, title, message):
        from tkinter import messagebox  # imported here so the file loads without a display
        messagebox.showinfo(title, message)

    # Ask a yes/no question in a pop-up
    def ask_yes_no(self, title, message):
        from tkinter import messagebox  # imported here so the file loads without a display
        return messagebox.askyesno(title, message)

    # Let the user pick a picture file; returns its path, or "" if the window was closed
    def choose_picture(self):
        from tkinter import filedialog  # imported here so the file loads without a display
        return filedialog.askopenfilename(
            title="Choose a picture to upload",
            filetypes=[("Pictures", "*.jpg *.jpeg *.png *.gif *.webp"), ("All files", "*.*")])


class Screen(ctk.CTkFrame):
    """Base for all screens: a title, a white scrolling card, and a bottom line with a message and buttons."""

    TITLE = ""
    STEP = 0  # which sidebar step is current (0 = none)
    HINT = ""  # a quiet line at the bottom left until a message replaces it

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.workflow = app.workflow
        self.head = ctk.CTkFrame(self, fg_color="transparent")
        self.head.pack(fill="x")
        # the bottom line is packed before the card so it always keeps its place
        self.footer = ctk.CTkFrame(self, fg_color="transparent")
        self.footer.pack(side="bottom", fill="x", pady=(16, 0))
        # the buttons are packed first, so a long message wraps instead of pushing them out of the window
        self.actions = ctk.CTkFrame(self.footer, fg_color="transparent")
        self.actions.pack(side="right")
        self.message = ctk.CTkLabel(self.footer, text=self.HINT, anchor="w", justify="left", wraplength=400,
                                    text_color=MUTED, font=font(13))
        self.message.pack(side="left", fill="x", expand=True)
        # a white card on the light page
        self.page = ctk.CTkScrollableFrame(self, fg_color=CARD_BG, corner_radius=20, border_width=1,
                                           border_color=LINE, scrollbar_button_color=LINE,
                                           scrollbar_button_hover_color=INPUT_LINE)
        self.page.pack(fill="both", expand=True)
        self.build()

    def build(self):
        raise NotImplementedError

    # The big title (and a quiet line under it), above the card
    def heading(self, text, subtitle=""):
        ctk.CTkLabel(self.head, text=text, text_color=INK, font=font(30, "bold"), anchor="w").pack(
            fill="x", pady=(8, 0))
        if subtitle:
            ctk.CTkLabel(self.head, text=subtitle, text_color=MUTED, font=font(15), anchor="w", justify="left",
                         wraplength=WRAP + 120).pack(fill="x", pady=(6, 18))
        else:
            ctk.CTkFrame(self.head, height=14, fg_color="transparent").pack()

    # A section title inside the card
    def section(self, text):
        ctk.CTkLabel(self.page, text=text, text_color=INK, font=font(16, "bold"), anchor="w").pack(
            fill="x", padx=22, pady=(22, 2))
        ctk.CTkFrame(self.page, height=3, width=40, fg_color=AMBER, corner_radius=2).pack(anchor="w", padx=22,
                                                                                         pady=(0, 4))

    # A normal line of text
    def text(self, text, color=None):
        label = ctk.CTkLabel(self.page, text=text, anchor="w", justify="left", wraplength=WRAP,
                             text_color=color or INK, font=font(14))
        label.pack(fill="x", padx=22, pady=3)
        return label

    # A label with a one-line entry box under it; returns the entry
    def field(self, label, value="", show=None, width=420, placeholder="", parent=None, return_label=False):
        parent = parent or self.page
        label_widget = ctk.CTkLabel(parent, text=label, anchor="w", text_color=INK, font=font(14, "bold"))
        label_widget.pack(
            fill="x", padx=22, pady=(14, 0))
        options = self.entry_look(width)
        if show:
            options["show"] = show
        if placeholder:
            options["placeholder_text"] = placeholder
        entry = ctk.CTkEntry(parent, **options)
        if value:
            entry.insert(0, value)
        if width >= 400:  # wide boxes fill the card (whatever its width), short ones keep their size
            entry.configure(width=200)
            entry.pack(fill="x", padx=22, pady=4)
        else:
            entry.pack(anchor="w", padx=22, pady=4)
        return (label_widget, entry) if return_label else entry

    # The look of a one-line entry box: rounded, thin border, same color as the card
    def entry_look(self, width):
        return dict(width=width, height=46, corner_radius=14, border_width=2, border_color=INPUT_LINE,
                    fg_color=CARD_BG, text_color=INK, placeholder_text_color=PLACEHOLDER, font=font(14))

    # The look of a big text box
    def textbox_look(self, height):
        return dict(height=height, wrap="word", corner_radius=14, border_width=2, border_color=INPUT_LINE,
                    fg_color=CARD_BG, text_color=INK, font=font(14))

    # The look of a drop-down menu
    def menu_look(self, width):
        return dict(width=width, height=38, corner_radius=14, fg_color=FIELD_BG, text_color=INK, button_color=ACCENT,
                    button_hover_color=ACCENT_HOVER, dropdown_fg_color=CARD_BG, dropdown_text_color=INK,
                    dropdown_hover_color=ACCENT_SOFT, font=font(14), dropdown_font=font(14))

    # A button inside the card (for things that are not "go on")
    def button(self, text, command, width=190, quiet=False):
        look = quiet_button() if quiet else main_button()
        look["height"] = 38
        button = ctk.CTkButton(self.page, text=text, command=command, width=width, **look)
        button.pack(anchor="w", padx=22, pady=6)
        return button

    # The main "go on" button at the bottom right
    def primary(self, text, command, width=190, state="normal"):
        button = ctk.CTkButton(self.actions, text=text, command=command, width=width, state=state, **main_button())
        button.pack(side="left", padx=(10, 0))
        return button

    # The quiet "Back" button next to it (it comes first, on the left)
    def back_button(self, command):
        button = ctk.CTkButton(self.actions, text="Back", command=command, width=100, **quiet_button())
        button.pack(side="left")
        return button

    # Show a message at the bottom left (red = problem, green = good news; empty text clears it)
    def say(self, text, ok=False):
        self.message.configure(text=text, text_color=GREEN if ok else RED)


# ------------------------------------------------------------------ Setup

class MarketsScreen(Screen):
    TITLE = "Markets"
    STEP = 0

    def build(self):
        self.heading(
            "Markets",
            "Choose a country to see its two planned publishing website options.",
        )
        self.section("Country")
        self.country_menu = MarketsCountryMenu(
            self.page,
            values=list(MARKET_COUNTRIES),
            command=self.on_country_changed,
            **self.menu_look(280),
        )
        self.country_menu.pack(anchor="w", padx=22, pady=8)
        self.country_menu.set(MARKET_COUNTRIES[0])

        self.section("Website options")
        self.country_label = self.text(MARKET_COUNTRIES[0], ACCENT_TEXT)
        row = ctk.CTkFrame(self.page, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=8)
        placeholder_style = quiet_button(state="disabled", width=240)
        self.website_one = ctk.CTkButton(
            row, text="Website 1 (coming soon)", **placeholder_style
        )
        self.website_one.pack(side="left", padx=(0, 10))
        self.website_two = ctk.CTkButton(
            row, text="Website 2 (coming soon)", **placeholder_style
        )
        self.website_two.pack(side="left")
        self.text(
            "These are placeholders only. Country-specific publishing will be available "
            "after the websites and their publishing integrations are configured.",
            MUTED,
        )

    def on_country_changed(self, country):
        self.country_label.configure(text=country)


class MarketsCountryMenu(ctk.CTkOptionMenu):
    VISIBLE_ITEMS = 10
    ITEM_HEIGHT = 34

    def _open_dropdown_menu(self):
        if hasattr(self, "country_popup") and self.country_popup.winfo_exists():
            self.country_popup.destroy()
            return

        root = self.winfo_toplevel()
        screen_height = self.winfo_screenheight()
        row_height = int(round(self._apply_widget_scaling(self.ITEM_HEIGHT)))
        popup_height = int(round(self._apply_widget_scaling(
            self.VISIBLE_ITEMS * self.ITEM_HEIGHT
        )))
        popup_height = min(popup_height, screen_height - 20)
        x = self.winfo_rootx()
        below = self.winfo_rooty() + self.winfo_height()
        above = self.winfo_rooty() - popup_height
        y = above if below + popup_height > screen_height and above >= 0 else below

        popup = self.country_popup = ctk.CTkToplevel(root, fg_color=CARD_BG)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.transient(root)
        popup.geometry(
            f"{self.winfo_width()}x{popup_height}+{x}+{y}"
        )
        frame = ctk.CTkScrollableFrame(
            popup,
            width=self.winfo_width(),
            height=popup_height,
            fg_color=CARD_BG,
            corner_radius=12,
            border_width=1,
            border_color=LINE,
            scrollbar_button_color=LINE,
            scrollbar_button_hover_color=INPUT_LINE,
        )
        frame.pack(fill="both", expand=True)
        item_style = flat_button()
        item_style["height"] = row_height
        for country in self._values:
            button = ctk.CTkButton(
                frame,
                text=country,
                command=lambda selected=country: self._select_country(selected),
                **item_style,
            )
            button.pack(fill="x", padx=4, pady=1)

        popup.bind("<Escape>", lambda event: popup.destroy())
        popup.deiconify()
        popup.focus_force()

    def _select_country(self, country):
        self.set(country)
        self._command(country)
        self.country_popup.destroy()


# ------------------------------------------------------------------ Setup

class SetupScreen(Screen):
    TITLE = "Setup"
    STEP = 0

    def build(self):
        s = self.workflow.settings
        self.heading("Setup", "Connect an AI provider and your Google account. You only need to do this once.")

        # --- AI provider and article settings ---
        self.section("1. AI provider and article settings")
        self.provider_selector = ctk.CTkFrame(self.page, fg_color=FIELD_BG, corner_radius=14)
        self.provider_selector.pack(anchor="w", padx=22, pady=6)
        self.gemini_provider_button = ctk.CTkButton(
            self.provider_selector, text="Gemini", command=lambda: self.on_provider_changed("Gemini"),
            width=120, height=38, corner_radius=12, font=font(14, "bold"),
        )
        self.openai_provider_button = ctk.CTkButton(
            self.provider_selector, text="OpenAI", command=lambda: self.on_provider_changed("OpenAI"),
            width=120, height=38, corner_radius=12, font=font(14, "bold"),
        )
        self.gemini_provider_button.pack(side="left", padx=3, pady=3)
        self.openai_provider_button.pack(side="left", padx=3, pady=3)
        self.gemini_fields = ctk.CTkFrame(self.page, fg_color="transparent")
        self.openai_fields = ctk.CTkFrame(self.page, fg_color="transparent")
        self.gemini_key = self.field("Gemini API key", s.gemini_api_key, show="*", parent=self.gemini_fields)
        self.gemini_model = self.field("Gemini model", s.gemini_model, parent=self.gemini_fields)
        self.openai_key = self.field("OpenAI API key", s.openai_api_key, show="*", parent=self.openai_fields)
        self.openai_model = self.field("OpenAI model", s.openai_model, parent=self.openai_fields)
        self.key, self.model = self.gemini_key, self.gemini_model
        self.on_provider_changed("OpenAI" if s.ai_provider == "openai" else "Gemini")
        self.min_words_label, self.min_words = self.field(
            "Shortest article (words)", str(s.min_words), width=120, return_label=True
        )
        self.max_words = self.field("Longest article (words)", str(s.max_words), width=120)
        self.limit = self.field("Posting limit per day (leave empty for no limit)",
                                "" if s.post_limit_per_day is None else str(s.post_limit_per_day), width=120)
        self.button("Save settings", self.on_save, quiet=True)

        # --- Google account ---
        self.section("2. Google account")
        self.google_status = self.text("")
        self.button("Sign in with Google", self.on_sign_in)
        self.button("Use another Google account", self.on_switch, quiet=True)
        self.refresh_google()

        # --- blog ---
        self.section("3. Your blog")
        self.blogs = {}  # menu text -> Blogger blog
        self.selected_blog_url = ""
        blog_row = ctk.CTkFrame(self.page, fg_color="transparent")
        blog_row.pack(fill="x", padx=22, pady=6)
        self.blog_menu = ctk.CTkOptionMenu(blog_row, values=["(sign in, then load your blogs)"],
                                           command=self.on_blog_chosen, **self.menu_look(420))
        self.blog_menu.pack(side="left", padx=(0, 8), fill="x", expand=True)
        self.open_blog_button = ctk.CTkButton(
            blog_row, text="Open blog", command=self.open_blog, width=130, state="disabled", **quiet_button()
        )
        self.open_blog_button.pack(side="left")
        if s.blog_id:
            self.blog_menu.set(f"Saved blog (id {s.blog_id})")
        self.button("Load my blogs", self.on_load_blogs, quiet=True)
        ctk.CTkFrame(self.page, height=10, fg_color="transparent").pack()

        self.primary("Continue", self.on_continue)

    # Save the settings; returns True when saved
    def on_save(self):
        try:
            provider = "openai" if self.selected_provider == "OpenAI" else "gemini"
            self.workflow.save_settings(
                self.gemini_key.get(), self.gemini_model.get(), self.min_words.get(),
                self.max_words.get(), self.limit.get(), provider=provider,
                openai_key=self.openai_key.get(), openai_model=self.openai_model.get(),
            )
        except TaasError as error:
            self.say(str(error))
            return False
        self.say("Settings saved.", ok=True)
        return True

    def on_provider_changed(self, provider):
        self.selected_provider = provider
        for name, button in (("Gemini", self.gemini_provider_button), ("OpenAI", self.openai_provider_button)):
            selected = name == provider
            button.configure(
                fg_color=ACCENT if selected else FIELD_BG,
                hover_color=ACCENT_HOVER if selected else ACCENT_SOFT,
                text_color=(INK[0], "#FFFFFF"),
            )
        if provider == "OpenAI":
            self.gemini_fields.pack_forget()
            if hasattr(self, "min_words"):
                self.openai_fields.pack(fill="x", before=self.min_words_label)
            else:
                self.openai_fields.pack(fill="x")
        else:
            self.openai_fields.pack_forget()
            if hasattr(self, "min_words"):
                self.gemini_fields.pack(fill="x", before=self.min_words_label)
            else:
                self.gemini_fields.pack(fill="x")

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
            if self.app.ask_yes_no(
                "Login failed",
                f"{value}\n\nWould you like to try signing in again?",
            ):
                self.on_sign_in()
            return
        self.say("Signed in.", ok=True)
        self.on_load_blogs()

    # Ask Blogger for the user's blogs
    def on_load_blogs(self):
        self.selected_blog_url = ""
        self.open_blog_button.configure(state="disabled")
        self.app.run_task(self.workflow.list_blogs, self.after_blogs, "Loading your blogs...")

    def after_blogs(self, kind, value):
        if kind == "error":
            self.say(value)
            return
        if not value:
            self.blogs = {}
            self.blog_menu.configure(values=["(no blogs found)"])
            self.blog_menu.set("(no blogs found)")
            self.say("No blogs were found on this Google account. Create one on Blogger first.")
            return
        self.blogs = {f"{b.name} ({b.url})": b for b in value}
        labels = list(self.blogs)
        self.blog_menu.configure(values=labels)
        current = [l for l, blog in self.blogs.items() if blog.id == self.workflow.settings.blog_id]
        if current:
            self.blog_menu.set(current[0])
            self.on_blog_chosen(current[0])
        elif len(labels) == 1:
            self.blog_menu.set(labels[0])
            self.on_blog_chosen(labels[0])
        else:
            self.blog_menu.set("(choose your blog)")
        self.say(f"Found {len(labels)} blog(s).", ok=True)

    # The user picked a blog
    def on_blog_chosen(self, label):
        blog = self.blogs.get(label)
        if blog:
            self.workflow.select_blog(blog.id)
            self.selected_blog_url = blog.url
            self.open_blog_button.configure(state="normal" if blog.url else "disabled")
            self.say("Blog saved.", ok=True)

    def open_blog(self):
        if self.selected_blog_url:
            webbrowser.open(self.selected_blog_url)

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
    TITLE = "Add pages"
    STEP = 1
    HINT = "Takes about a minute."

    def build(self):
        saved_urls, saved_keywords = self.app.last_input or ([""], "")
        saved_urls = saved_urls[:MAX_URLS] or [""]
        self.app.last_keyword_seed = getattr(self.app, "last_keyword_seed", "")
        self.selected_keywords = split_keywords(saved_keywords)
        self.heading("Let's write your article",
                     f"Add at least {MIN_URLS} product page (up to {MAX_URLS}).")
        self.url_fields = ctk.CTkFrame(self.page, fg_color="transparent")
        self.url_fields.pack(fill="x")
        self.urls, self.ticks = [], []
        for value in saved_urls:
            self.add_url_field(value)
        self.add_url_button = ctk.CTkButton(
            self.page, text="+ Add another URL", command=self.on_add_url, width=200, **quiet_button()
        )
        self.add_url_button.configure(height=38)
        self.add_url_button.pack(anchor="w", padx=22, pady=6)
        self.update_add_url_button()
        self.refresh_ticks()
        ctk.CTkLabel(self.page, text="Keyword ideas", anchor="w", text_color=INK,
                     font=font(14, "bold")).pack(fill="x", padx=22, pady=(14, 0))
        seed_row = ctk.CTkFrame(self.page, fg_color="transparent")
        seed_row.pack(fill="x", padx=22, pady=4)
        self.keyword_seed = ctk.CTkEntry(
            seed_row, placeholder_text='Enter one seed phrase, e.g. "Diwali sale"', **self.entry_look(420)
        )
        self.keyword_seed.pack(side="left", fill="x", expand=True, padx=(0, 8))
        if self.app.last_keyword_seed:
            self.keyword_seed.insert(0, self.app.last_keyword_seed)
        self.generate_keywords_button = ctk.CTkButton(
            seed_row, text="Generate keywords", command=self.on_generate_keywords, state="disabled",
            width=170, **quiet_button()
        )
        self.generate_keywords_button.pack(side="left")
        self.keyword_seed.bind("<KeyRelease>", lambda event: self.update_keyword_controls())

        ctk.CTkLabel(self.page, text="Keywords for the article", anchor="w", text_color=INK,
                     font=font(14, "bold")).pack(fill="x", padx=22, pady=(12, 0))
        self.keyword_chip_area = ctk.CTkFrame(self.page, fg_color="transparent")
        self.keyword_chip_area.pack(fill="x", padx=22, pady=(4, 2))
        self.keyword_chip_rows = []
        self.render_keyword_chips()

        add_row = ctk.CTkFrame(self.page, fg_color="transparent")
        add_row.pack(fill="x", padx=22, pady=4)
        self.manual_keywords = ctk.CTkEntry(
            add_row, placeholder_text="Add keywords separated by commas", **self.entry_look(420)
        )
        self.manual_keywords.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.manual_keywords.bind("<Return>", self.on_add_keywords)
        self.add_keywords_button = ctk.CTkButton(
            add_row, text="Add", command=self.on_add_keywords, width=80, **quiet_button()
        )
        self.add_keywords_button.pack(side="left")
        self.keyword_count = self.text("", MUTED)
        ctk.CTkFrame(self.page, height=10, fg_color="transparent").pack()
        self.read_button = self.primary("Read my pages", self.on_read, state="disabled")
        self.update_keyword_controls()

    def render_keyword_chips(self):
        for row in self.keyword_chip_rows:
            row.destroy()
        self.keyword_chip_rows = []
        for start in range(0, len(self.selected_keywords), 2):
            row = ctk.CTkFrame(self.keyword_chip_area, fg_color="transparent")
            row.pack(fill="x", pady=2)
            self.keyword_chip_rows.append(row)
            for index in range(start, min(start + 2, len(self.selected_keywords))):
                keyword = self.selected_keywords[index]
                chip = ctk.CTkFrame(row, fg_color=ACCENT_SOFT, corner_radius=16)
                chip.pack(side="left", padx=(0, 8), pady=2)
                ctk.CTkLabel(
                    chip, text=keyword, text_color=INK, font=font(13), width=min(220, max(60, len(keyword) * 8))
                ).pack(side="left", padx=(10, 4), pady=6)
                remove_look = quiet_button()
                remove_look.update(width=26, height=26, corner_radius=13)
                ctk.CTkButton(
                    chip, text="×", command=lambda word=keyword: self.remove_keyword(word),
                    **remove_look
                ).pack(side="left", padx=(0, 4), pady=3)

    def update_keyword_controls(self):
        seed = self.keyword_seed.get().strip()
        self.generate_keywords_button.configure(state="normal" if seed else "disabled")
        count = len(self.selected_keywords)
        self.keyword_count.configure(
            text=f"{count} of {MAX_KEYWORDS} keywords selected. Add at least {MIN_KEYWORDS} to continue."
            if count < MIN_KEYWORDS else f"{count} of {MAX_KEYWORDS} keywords selected."
        )
        self.read_button.configure(state="normal" if count >= MIN_KEYWORDS else "disabled")

    def add_keyword_values(self, raw):
        additions = raw if isinstance(raw, (list, tuple)) else split_keywords(raw)
        new_values = list(self.selected_keywords)
        seen = {word.casefold() for word in new_values}
        for keyword in additions:
            normalized = " ".join(keyword.split())
            if normalized.casefold() not in seen:
                new_values.append(normalized)
                seen.add(normalized.casefold())
        if len(new_values) > MAX_KEYWORDS:
            self.say(f"Choose no more than {MAX_KEYWORDS} keywords.")
            return False
        self.selected_keywords = new_values
        self.render_keyword_chips()
        self.update_keyword_controls()
        return True

    def remove_keyword(self, keyword):
        self.selected_keywords = [item for item in self.selected_keywords if item != keyword]
        self.render_keyword_chips()
        self.update_keyword_controls()

    def on_add_keywords(self, event=None):
        if self.add_keyword_values(self.manual_keywords.get()):
            self.manual_keywords.delete(0, "end")
            self.say("")
        return "break"

    def on_generate_keywords(self):
        seed = self.keyword_seed.get().strip()
        self.app.last_keyword_seed = seed
        self.generate_keywords_button.configure(state="disabled")
        self.say("")
        self.app.run_task(
            lambda: self.workflow.suggest_keywords(seed),
            lambda kind, value: self.after_generate_keywords(seed, kind, value),
            "Getting keyword suggestions...",
        )

    def after_generate_keywords(self, seed, kind, value):
        self.generate_keywords_button.configure(state="normal" if self.keyword_seed.get().strip() else "disabled")
        if kind == "error":
            self.say(value)
            return
        if self.keyword_seed.get().strip() != seed:
            return
        if self.add_keyword_values(value):
            self.say(f"Added {len(value)} keyword suggestion(s).", ok=True)

    def add_url_field(self, value=""):
        number = len(self.urls) + 1
        entry = self.field(
            f"Page {number}" + (" (optional)" if number > MIN_URLS else ""),
            value, width=640, placeholder="https://", parent=self.url_fields,
        )
        tick = ctk.CTkLabel(self.url_fields, text="", anchor="w", text_color=GREEN, font=font(13, "bold"))
        tick.pack(fill="x", padx=24)
        entry.bind("<KeyRelease>", lambda event: self.refresh_ticks())
        self.urls.append(entry)
        self.ticks.append(tick)

    def on_add_url(self):
        if len(self.urls) >= MAX_URLS:
            return
        self.add_url_field()
        self.refresh_ticks()
        self.update_add_url_button()

    def update_add_url_button(self):
        if len(self.urls) >= MAX_URLS:
            self.add_url_button.configure(state="disabled", text=f"Maximum of {MAX_URLS} URLs added")
        else:
            self.add_url_button.configure(state="normal", text="+ Add another URL")

    # A friendly "Looks good" under each address that looks right
    def refresh_ticks(self):
        for entry, tick in zip(self.urls, self.ticks):
            tick.configure(text="✓  Looks good" if looks_like_address(entry.get()) else "")

    def save_for_navigation(self):
        self.app.last_keyword_seed = self.keyword_seed.get().strip()
        self.app.last_input = ([entry.get() for entry in self.urls], ", ".join(self.selected_keywords))

    def on_read(self):
        urls = [e.get() for e in self.urls]
        self.app.last_keyword_seed = self.keyword_seed.get().strip()
        keywords = ", ".join(self.selected_keywords)
        self.app.last_input = (urls, keywords)
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
    TITLE = "Check details"
    STEP = 2

    def build(self):
        analysis = self.app.analysis
        self.heading("Check what we found",
                     "Correct anything that is wrong. Brand names are only used to keep them out of the article.")
        self.brands, self.notes = [], []
        for item in analysis.analyses:
            ctk.CTkLabel(self.page, text=item.url, anchor="w", text_color=ACCENT_TEXT, font=font(14, "bold")).pack(
                fill="x", padx=22, pady=(18, 2))
            d = item.detection
            if d.error:
                self.text(d.error, WARN)  # a gentle heads-up, not an alarm
            else:
                self.text("Page read." + (" It had very little text, so check the values." if d.thin else ""), GREEN)
            self.brands.append(self.field("Brand name on this page", d.brand, width=420))
            self.notes.append(self.field("About this page (optional: helps when the page cannot be read)", d.note,
                                         width=720))
        self.section("For the whole article")
        self.category = self.field("Category", analysis.category, width=420)
        self.country = self.field("Country", analysis.country, width=420)
        ctk.CTkFrame(self.page, height=10, fg_color="transparent").pack()
        self.back_button(self.on_back)
        self.primary("Write the article", self.on_write)

    # Keep what the user typed, so coming back to this screen shows it again
    def keep_edits(self):
        analysis = self.app.analysis
        for item, entry, note in zip(analysis.analyses, self.brands, self.notes):
            item.detection.brand = entry.get().strip()
            item.detection.note = note.get().strip()
        analysis.category = self.category.get().strip()
        analysis.country = self.country.get().strip()

    def save_for_navigation(self):
        self.keep_edits()

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
    TITLE = "Review article"
    STEP = 3

    def build(self):
        draft = self.app.draft
        self.heading("Review your article", "Read it, change anything you like, then post it to Blogger.")
        self.info = self.text("", MUTED)
        self.title_entry = self.field("Title", draft.title, width=720)
        ctk.CTkLabel(self.page, text="Article text", anchor="w", text_color=INK, font=font(14, "bold")).pack(
            fill="x", padx=22, pady=(14, 0))
        self.body = ctk.CTkTextbox(self.page, **self.textbox_look(380))
        self.body.pack(fill="x", padx=22, pady=4)
        self.text("Square brackets [like this] mark a link. Start a line with ## for a subheading "
                  "and with - for a list item. Leave an empty line between paragraphs.", MUTED)

        # --- pictures ---
        self.section("Images")
        self.text("Blogger cannot take files from this app, so a picture must already be on the internet. "
                  "Paste its web address and a short description. Click in the article where it should go, "
                  "then press Add image. It is placed after the paragraph you clicked in. "
                  "A picture shows in the text as a line like {image: https://... | description}; "
                  "delete that line to remove the picture.", MUTED)
        self.image_url = self.field("Image web address", width=640, placeholder="https://")
        self.image_alt = self.field("Image description (what the picture shows)", width=640)
        row = ctk.CTkFrame(self.page, fg_color="transparent")
        row.pack(anchor="w", padx=22, pady=8)
        ctk.CTkButton(row, text="Add image", width=130, command=self.on_add_image, **main_button()).pack(
            side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Upload image to cloud", width=190, command=self.on_upload_image,
                      **main_button()).pack(side="left", padx=(0, 8))
        # not ready yet: shown so the team can see what is coming, but it cannot be clicked
        self.generate_images_button = ctk.CTkButton(row, text="Generate images automatically (coming soon)",
                                                    width=300, state="disabled", **quiet_button())
        self.generate_images_button.pack(side="left")
        self.image_note = ctk.CTkLabel(self.page, text="", anchor="w", justify="left", wraplength=WRAP,
                                       text_color=INK, font=font(13))
        self.image_note.pack(fill="x", padx=22, pady=2)
        # the web address of the uploaded picture: it can be selected and copied, but not changed
        ctk.CTkLabel(self.page, text="Uploaded image web address (copy it from here)", anchor="w", text_color=INK,
                     font=font(14, "bold")).pack(fill="x", padx=22, pady=(10, 0))
        self.uploaded_url = ctk.CTkEntry(self.page, **self.entry_look(640))
        self.uploaded_url.configure(width=200)
        self.uploaded_url.pack(fill="x", padx=22, pady=4)
        self.uploaded_url.configure(state="readonly")

        # --- which keyword is the link text for each address ---
        self.section("Links")
        self.menus = []
        for i, link in enumerate(draft.links):
            self.text(f"Link {i + 1}: {link.url}")
            menu = ctk.CTkOptionMenu(self.page, values=list(draft.keywords),
                                     command=lambda value, i=i: self.on_anchor(i, value), **self.menu_look(320))
            menu.pack(anchor="w", padx=22, pady=4)
            self.menus.append(menu)

        # --- checks ---
        self.section("Checks")
        self.checks = self.text("")
        row = ctk.CTkFrame(self.page, fg_color="transparent")
        row.pack(anchor="w", padx=22, pady=8)
        ctk.CTkButton(row, text="Check again", width=130, command=self.on_check, **quiet_button()).pack(
            side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Write it again", width=140, command=self.on_rewrite, **quiet_button()).pack(
            side="left")

        # --- post ---
        self.section("Post to Blogger")
        self.mode = ctk.CTkSegmentedButton(self.page, values=[DRAFT_CHOICE, LIVE_CHOICE], fg_color=FIELD_BG,
                                           selected_color=SELECTED, selected_hover_color=SELECTED,
                                           unselected_color=FIELD_BG, unselected_hover_color=ACCENT_SOFT,
                                           text_color=INK, corner_radius=14, font=font(14, "bold"))
        self.mode.set(DRAFT_CHOICE)
        self.mode.pack(anchor="w", padx=22, pady=6)
        self.confirm = ctk.CTkCheckBox(self.page, text="I have read the article and the links, and it can be posted.",
                                       command=self.on_confirm_changed, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                       border_color=INPUT_LINE, checkmark_color="#FFFFFF", text_color=INK,
                                       corner_radius=6, font=font(14))
        self.confirm.pack(anchor="w", padx=22, pady=(6, 18))

        self.back_button(self.on_back)
        self.post_button = self.primary("Post to Blogger", self.on_post, state="disabled")

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
                text="Please look at these:\n" + "\n".join(f"- {p}" for p in report.problems), text_color=WARN)

    def current(self):
        return self.title_entry.get().strip(), self.body.get("1.0", "end").strip()

    def save_for_navigation(self):
        title, text = self.current()
        self.workflow.recheck(self.app.draft, title, text)

    # Put a picture line into the article text, after the paragraph the cursor is in
    def on_add_image(self):
        try:
            line = self.workflow.image_line(self.image_url.get(), self.image_alt.get())
        except TaasError as error:
            self.image_note.configure(text=str(error), text_color=WARN)
            return
        self.body.insert("insert lineend", "\n\n" + line + "\n\n")
        self.image_url.delete(0, "end")
        self.image_alt.delete(0, "end")
        self.image_note.configure(text="Image added to the article text.", text_color=GREEN)
        self.on_check()

    # Let the user pick a picture, upload it to Cloudinary, then show and fill in its web address
    def on_upload_image(self):
        path = self.app.choose_picture()
        if not path:  # the user closed the window
            return
        self.image_note.configure(text="", text_color=INK)
        self.app.run_task(lambda: self.workflow.upload_image(path), self.after_upload_image,
                          "Uploading the picture to the cloud...")

    # The upload finished
    def after_upload_image(self, kind, value):
        if kind == "error":
            self.image_note.configure(text=value, text_color=RED)
            return
        self.uploaded_url.configure(state="normal")
        self.uploaded_url.delete(0, "end")
        self.uploaded_url.insert(0, value)
        self.uploaded_url.configure(state="readonly")
        self.image_url.delete(0, "end")
        self.image_url.insert(0, value)
        self.image_note.configure(text="Picture uploaded. Its web address is filled in above; add a description "
                                       "and press Add image.", text_color=GREEN)

    # Go back to the details (the article text on screen is kept in the draft)
    def on_back(self):
        self.save_for_navigation()
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
    TITLE = "Publish"
    STEP = 4

    def build(self):
        kind, value = self.app.result
        if kind == "error":
            self.STEP = 3  # the article is still waiting, so stay on "Review article"
            self.heading("The article was not posted", "Nothing was lost. Your article is still there.")
            self.text(value, WARN if "HTTP" not in value else RED)
            self.primary("Back to the article", lambda: self.app.show(ArticleScreen), width=210)
            return

        self.STEP = 5  # all four steps are done
        self.heading("Done")
        ctk.CTkLabel(self.page, text="✓", width=72, height=72, corner_radius=36, fg_color=GREEN_SOFT, text_color=GREEN,
                     font=font(34, "bold")).pack(anchor="w", padx=22, pady=(22, 8))
        self.text("Saved as a Blogger draft." if not value.live else "Published on your blog.", GREEN)
        if value.url:
            self.link = self.field("Link to the post", value.url, width=640)
            row = ctk.CTkFrame(self.page, fg_color="transparent")
            row.pack(anchor="w", padx=22, pady=8)
            ctk.CTkButton(row, text="Copy link", width=120, command=self.on_copy, **quiet_button()).pack(
                side="left", padx=(0, 8))
            ctk.CTkButton(row, text="Open in browser", width=160, command=lambda: webbrowser.open(value.url),
                          **main_button()).pack(side="left")
        else:
            self.text("Open Blogger to see your post.")
        self.primary("Write another article", self.on_again, width=220)

    def on_copy(self):
        self.app.clipboard_clear()
        self.app.clipboard_append(self.link.get())

    # Start again with empty boxes
    def on_again(self):
        self.app.last_input = self.app.analysis = self.app.draft = self.app.result = None
        self.app.last_keyword_seed = ""
        self.app.show(InputScreen)


# Start the app
def run():
    ctk.set_appearance_mode("light")  # starts light; the Dark mode button in the sidebar switches it
    ctk.set_default_color_theme("blue")
    App(auto_check=True).mainloop()
