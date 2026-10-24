"""The look of TAAS: Ubuy colors in a light and a dark version.

Colors come in pairs (light mode, dark mode), which is how the screen toolkit wants them.
The Ubuy colors were read from the Ubuy website:
  amber   #FFB100  main buttons, highlights
  ink     #151515  text on amber, dark backgrounds
  green   #198754  good news          red  #E00F0F  problems
This file has no screen code, so it can be tested without a window.
"""

# ---- brand colors ---------------------------------------------------------------------------
AMBER = "#FFB100"
AMBER_HOVER = "#E09B00"  # amber when the mouse is over a button
INK = "#151515"

# ---- (light, dark) pairs ---------------------------------------------------------------------
WINDOW = ("#F7F7F9", "#121214")  # the window background
CARD = ("#FFFFFF", "#1E1E21")  # panels, the top bar, the scrolling page
CARD_TOP = ("#F0F0F3", "#27272B")  # slightly different panel color (headers)
LINE = ("#DEDEE4", "#38383E")  # thin borders around panels
FIELD = ("#FFFFFF", "#2A2A2F")  # the inside of input boxes
FIELD_LINE = ("#B9B9C2", "#4D4D55")  # border of input boxes
TEXT = ("#151515", "#F2F2F4")  # normal text
TEXT_SOFT = ("#5E5E69", "#A4A4AE")  # hints and placeholders
GREEN = ("#157347", "#4CC38A")  # good news (text)
RED = ("#C70D0D", "#FF7A7A")  # problems (text)
NOTICE = ("#FFF1CC", "#3B2F0E")  # the "new version" bar
BUTTON_TEXT = (INK, INK)  # text on amber buttons
BUTTON_TEXT_OFF = ("#7A5C0B", "#7A5C0B")  # text on a button that cannot be clicked (looks faded)
CHOICE_OFF = ("#E3E3E8", "#CFCFD6")  # unselected part of a choice bar (dark text stays readable)
SCROLL = ("#C4C4CC", "#4D4D55")
SCROLL_HOVER = ("#A2A2AD", "#6C6C77")


# ---- contrast (so the colors can be checked in tests) -----------------------------------------
def _channel(value):
    value /= 255
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


# How bright a color is (0 = black, 1 = white)
def luminance(color):
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


# How well text of one color can be read on another (WCAG: 4.5 or more is good for normal text)
def contrast(color_a, color_b):
    high, low = sorted((luminance(color_a), luminance(color_b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


# ---- what to change in the toolkit's built-in theme ------------------------------------------
def overrides():
    """{widget name: {setting: value}} - only settings the toolkit knows are used (see apply)."""
    amber = [AMBER, AMBER]
    hover = [AMBER_HOVER, AMBER_HOVER]
    return {
        "CTk": {"fg_color": list(WINDOW)},
        "CTkToplevel": {"fg_color": list(WINDOW)},
        "CTkFrame": {"corner_radius": 8, "fg_color": list(CARD), "top_fg_color": list(CARD_TOP), "border_color": list(LINE)},
        "CTkButton": {
            "corner_radius": 6, "fg_color": amber, "hover_color": hover, "border_color": list(BUTTON_TEXT),
            "text_color": list(BUTTON_TEXT), "text_color_disabled": list(BUTTON_TEXT_OFF),
        },
        "CTkLabel": {"text_color": list(TEXT)},
        "CTkEntry": {
            "corner_radius": 6, "border_width": 1, "fg_color": list(FIELD), "border_color": list(FIELD_LINE),
            "text_color": list(TEXT), "placeholder_text_color": list(TEXT_SOFT),
        },
        "CTkTextbox": {
            "corner_radius": 6, "border_width": 1, "fg_color": list(FIELD), "border_color": list(FIELD_LINE),
            "text_color": list(TEXT), "scrollbar_button_color": list(SCROLL), "scrollbar_button_hover_color": list(SCROLL_HOVER),
        },
        "CTkScrollbar": {"button_color": list(SCROLL), "button_hover_color": list(SCROLL_HOVER)},
        "CTkScrollableFrame": {"label_fg_color": list(CARD_TOP)},
        "CTkCheckBox": {
            "fg_color": amber, "hover_color": hover, "border_color": list(FIELD_LINE),
            "checkmark_color": list(BUTTON_TEXT), "text_color": list(TEXT),
        },
        "CTkRadioButton": {"fg_color": amber, "hover_color": hover, "border_color": list(FIELD_LINE), "text_color": list(TEXT)},
        "CTkSwitch": {"progress_color": amber, "button_color": list(CARD), "button_hover_color": list(CARD_TOP), "text_color": list(TEXT)},
        "CTkProgressBar": {"progress_color": amber, "fg_color": list(LINE)},
        "CTkSlider": {"progress_color": amber, "button_color": amber, "button_hover_color": hover},
        "CTkOptionMenu": {
            "fg_color": list(FIELD), "button_color": amber, "button_hover_color": hover, "text_color": list(TEXT),
        },
        "CTkComboBox": {
            "fg_color": list(FIELD), "border_color": list(FIELD_LINE), "button_color": amber,
            "button_hover_color": hover, "text_color": list(TEXT),
        },
        "CTkSegmentedButton": {
            "fg_color": list(CHOICE_OFF), "selected_color": amber, "selected_hover_color": hover,
            "unselected_color": list(CHOICE_OFF), "unselected_hover_color": ["#D3D3DA", "#BDBDC6"],
            "text_color": list(BUTTON_TEXT), "text_color_disabled": list(BUTTON_TEXT_OFF),
        },
        "DropdownMenu": {"fg_color": list(FIELD), "hover_color": list(CARD_TOP), "text_color": list(TEXT)},
    }


# Merge our colors into the toolkit's theme. Call this once, before the window is made.
# Anything the installed toolkit version does not know is skipped, so a version change cannot crash the app.
def apply(ctk):
    manager = getattr(ctk, "ThemeManager", None)
    if manager is None:
        return
    for widget, settings in overrides().items():
        current = manager.theme.get(widget)
        if current is None:
            continue
        for key, value in settings.items():
            if key in current:
                current[key] = value
