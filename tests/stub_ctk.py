"""A stand-in for customtkinter, used only by the UI smoke test.

It remembers what the code does with each widget (text, values, entry contents), so a test can
click buttons and read screens. It does NOT draw anything, so it cannot show how the windows look.
Like the real library, pack/grid return None.
"""


class _Font:
    def __init__(self, **kwargs):
        self.kw = kwargs


class Widget:
    def __init__(self, master=None, *args, **kwargs):
        self.master = master
        self.kw = dict(kwargs)
        self.children = []
        self.destroyed = False
        if isinstance(master, Widget):
            master.children.append(self)

    def pack(self, *a, **k):  # the real pack returns None
        return None

    def pack_forget(self):
        return None

    def grid(self, *a, **k):
        return None

    def place(self, *a, **k):
        return None

    def configure(self, **kwargs):
        # the real toolkit raises an error when a color is None
        for key in ("text_color", "fg_color", "border_color"):
            if key in kwargs and kwargs[key] is None:
                raise ValueError(f"color is None for {key}, use 'transparent' for no color")
        self.kw.update(kwargs)

    def cget(self, key):
        return self.kw.get(key)

    def destroy(self):
        self.destroyed = True
        for child in list(self.children):
            child.destroy()

    def root(self):
        node = self
        while isinstance(node.master, Widget):
            node = node.master
        return node

    def after(self, ms, func=None, *args):
        self.root().afters.append(func)

    def descendants(self):
        for child in self.children:
            if not child.destroyed:
                yield child
                yield from child.descendants()


class CTk(Widget):
    def __init__(self, *a, **k):
        super().__init__(None)
        self.afters, self.titles, self.clipboard = [], [], ""

    def title(self, text):
        self.titles.append(text)

    def geometry(self, *a):
        pass

    def minsize(self, *a):
        pass

    def mainloop(self):
        pass

    def clipboard_clear(self):
        self.clipboard = ""

    def clipboard_append(self, text):
        self.clipboard += text


class CTkFrame(Widget):
    pass


class CTkScrollableFrame(Widget):
    pass


class CTkLabel(Widget):
    pass


class CTkButton(Widget):
    def invoke(self):  # what a click does
        if self.kw.get("state") != "disabled" and self.kw.get("command"):
            self.kw["command"]()


class CTkEntry(Widget):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._text = ""

    def insert(self, index, text):
        self._text += text

    def delete(self, first, last=None):
        self._text = ""

    def get(self):
        return self._text


class CTkTextbox(Widget):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._text = ""

    def insert(self, index, text):
        self._text += text

    def delete(self, first, last=None):
        self._text = ""

    def get(self, first, last=None):
        return self._text + "\n"  # the real one adds a final newline


class CTkOptionMenu(Widget):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        values = self.kw.get("values") or [""]
        self._value = values[0]

    def set(self, value):
        self._value = value

    def get(self):
        return self._value

    def choose(self, value):  # what picking an item does
        self._value = value
        if self.kw.get("command"):
            self.kw["command"](value)


class CTkCheckBox(Widget):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._on = 0

    def get(self):
        return self._on

    def click(self):
        self._on = 0 if self._on else 1
        if self.kw.get("command"):
            self.kw["command"]()


class CTkSegmentedButton(Widget):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._value = ""

    def set(self, value):
        self._value = value

    def get(self):
        return self._value


def CTkFont(**kwargs):
    return _Font(**kwargs)


def set_appearance_mode(mode):
    pass


def set_default_color_theme(theme):
    pass
