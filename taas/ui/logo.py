"""The TAAS logo, drawn with code (so there is no picture file to ship or lose).

An article page with a "send" arrow: a near-black badge with an amber ring, a white page with a folded corner,
and an amber circle with an up arrow (the article goes out). It is an original drawing and
does not copy the Ubuy logo. Small sizes leave out the fine details so they stay clear.
"""

from PIL import Image, ImageDraw  # drawing

AMBER, INK = "#FFB100", "#151515"
PAGE, FOLD, LINES = "#FFFFFF", "#D4D4DB", "#B6B6BF"
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)  # sizes stored in the .ico file
SCALE = 4  # draw 4 times bigger, then shrink: smooth edges


# One logo as a picture (RGBA, transparent corners)
def draw_logo(size=256):
    big = size * SCALE
    unit = big / 100  # the drawing is planned on a 100 x 100 grid
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)

    def box(x1, y1, x2, y2):
        return [x1 * unit, y1 * unit, x2 * unit, y2 * unit]

    def points(*pairs):
        return [(x * unit, y * unit) for x, y in pairs]

    detailed = size >= 40
    # badge with an amber ring all around it, so it also shows on dark backgrounds (taskbar, dark mode).
    # The ring is thicker at small sizes so that it stays visible.
    ring = 4 if detailed else 9
    d.rounded_rectangle(box(1, 1, 99, 99), radius=23 * unit, fill=AMBER)
    d.rounded_rectangle(box(1 + ring, 1 + ring, 99 - ring, 99 - ring), radius=(23 - ring) * unit, fill=INK)
    # the article page with a folded corner
    d.polygon(points((22, 16), (50, 16), (66, 32), (66, 80), (22, 80)), fill=PAGE)
    d.polygon(points((50, 16), (50, 32), (66, 32)), fill=FOLD)
    if detailed:  # lines of text
        for top, right in ((42, 56), (51, 56), (60, 44)):
            d.rounded_rectangle(box(31, top, right, top + 4.5), radius=2.2 * unit, fill=LINES)
    # the send badge: amber circle with a dark ring (cuts it free from the page) and an up arrow
    cx, cy = 68, 69
    d.ellipse(box(cx - 24, cy - 24, cx + 24, cy + 24), fill=INK)
    d.ellipse(box(cx - 20, cy - 20, cx + 20, cy + 20), fill=AMBER)
    d.polygon(points((cx, cy - 13), (cx - 11, cy - 1), (cx + 11, cy - 1)), fill=INK)  # arrow head
    d.rectangle(box(cx - 4.2, cy - 2, cx + 4.2, cy + 13), fill=INK)  # arrow shaft
    return image.resize((size, size), Image.LANCZOS)


# Save a Windows icon file with several sizes inside
def write_ico(path, sizes=ICON_SIZES):
    ordered = sorted(sizes, reverse=True)
    biggest = draw_logo(ordered[0])
    biggest.save(path, format="ICO", sizes=[(s, s) for s in ordered],
                 append_images=[draw_logo(s) for s in ordered[1:]])
