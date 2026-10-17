"""TileSlicer - pixel-art GUI built from the graphics in  Assets/Interface
with the  monogram.ttf  pixel font, shown on fixed 384x512 canvases.

Main window (top to bottom):
  Batch / About buttons, Import / Slice buttons
  32 x 32 banner : selection box (gold + blue when active)
  16 x 16 banner : selection box
  custom banner  : a  W x H  tile size can be typed here (e.g. 24x24)
  bottom         : prefix parchment area (appears when Slice asks for a prefix)

About window (opened from the About button, same 384x512 decoration):
  the app name, what it does, and the credits: Hypnobius for the
  interface design tilesets, datagoblin for the monogram.ttf pixel font.

Batch window (opened from the Batch button, same 384x512 decoration):
  Slice button, 32/16 size checkboxes
  scrollable list of the chosen images (scrollbar when they don't all fit)
  pressing Slice slices every listed image; it only asks for a prefix for
  files whose names would collide (identical stems), otherwise the file
  name itself is used as the prefix.

Interactions
  Import  : pick one image file
  Batch   : pick several image files, all load into the batch window
  About   : show the credits (Esc or the red x closes it)
  rows    : choose the tile size (32, 16, or the typed custom size)
  Slice   : asks for an export prefix, then writes Prefix_Row#_Column#_WxH.png
  red x   : quit / close the window

All windows are undecorated (overrideredirect) so no OS title bar spoils the
art; drag them by the border or any empty patch to move them, and they keep a
taskbar button on Windows so they can still be found when covered.
"""

import os
import re
import sys
import tkinter as tk
from collections import defaultdict
from tkinter import filedialog

from PIL import Image, ImageDraw, ImageFont, ImageTk

if getattr(sys, "frozen", False):    # PyInstaller exe: assets are bundled read-only
    ROOT_DIR = os.path.dirname(sys.executable)              # writes go next to the exe
    RES_DIR = getattr(sys, "_MEIPASS", ROOT_DIR)
else:
    ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
    RES_DIR = ROOT_DIR
ASSET_DIR = os.path.join(RES_DIR, "Assets")
INTERFACE_DIR = os.path.join(ASSET_DIR, "Interface")
FONT_PATH = os.path.join(ASSET_DIR, "monogram.ttf")
EXPORT_DIR = os.path.join(ROOT_DIR, "Export")

WIDTH, HEIGHT = 384, 512
FONT_SIZE = 32                       # monogram renders crisp at multiples of 16
SMALL_FONT = 32                      # parchment box labels

FILL = (46, 50, 42, 255)             # background / interior colour
TEXT_GRAY = (165, 165, 165, 255)     # placeholder dims text
TEXT_WHITE = (241, 241, 241, 255)    # Batch / Import / Slice / banner labels
TEXT_DARK = (46, 50, 42, 255)        # parchment text
TEXT_GOLD = (251, 214, 147, 255)     # toast / batch size labels
TEXT_RED = (255, 113, 91, 255)       # toast / error
TEXT_BLUE = (64, 108, 145, 255)      # highlight

# ---------------------------------------------------------------- assets ----

_asset_cache = {}


def load(name):
    """Return an Interface asset as RGBA (cached)."""
    if name not in _asset_cache:
        _asset_cache[name] = Image.open(os.path.join(INTERFACE_DIR, name)).convert("RGBA")
    return _asset_cache[name]


def scale2(img):
    return img.resize((img.width * 2, img.height * 2), Image.NEAREST)


_font_cache = {}


def font(size):
    if size not in _font_cache:
        _font_cache[size] = ImageFont.truetype(FONT_PATH, size)
    return _font_cache[size]


_text_cache = {}


def text_image(text, size, color, max_width=None):
    """Render text with the monogram pixel font, cropped to its pixels."""
    key = (text, size, color, max_width)
    if key in _text_cache:
        return _text_cache[key]
    box = (max(1, len(text)) * size, size * 3)
    img = Image.new("RGBA", box, (0, 0, 0, 0))
    ImageDraw.Draw(img).text((size, size), text, font=font(size), fill=color)
    bbox = img.getbbox()
    img = img.crop(bbox) if bbox else Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    if max_width and img.width > max_width:          # keep the head visible
        img = img.crop((0, 0, max_width, img.height))
    if size % 16:                                    # in-between sizes: hard pixel edges
        img.putalpha(img.getchannel("A").point(lambda a: 255 if a > 110 else 0))
    _text_cache[key] = img
    return img


def paste_centered(dest, element, cx, cy):
    dest.alpha_composite(element, (round(cx - element.width / 2),
                                   round(cy - element.height / 2)))


# ------------------------------------------------------------ assemblers ----

def build_button(left_name, right_name, squish=False, text=None,
                 text_pos=(0, 0), text_color=TEXT_WHITE):
    """One 128x64 button: left+right halves at 2x, optional 1px squish,
    optional label baked on top."""
    asm = Image.new("RGBA", (128, 64), (0, 0, 0, 0))
    asm.alpha_composite(scale2(load(left_name)), (0, 0))
    asm.alpha_composite(scale2(load(right_name)), (64, 0))
    if squish:                     # the mock's Slice button is one row shorter
        sq = Image.new("RGBA", (128, 64), FILL)
        sq.paste(asm.crop((0, 0, 128, 33)), (0, 0))
        sq.paste(asm.crop((0, 34, 128, 64)), (0, 33))
        asm = sq
    if text:
        asm.alpha_composite(text_image(text, FONT_SIZE, text_color), text_pos)
    return asm


def build_window_panel(cols, rows):
    """The stitched parchment window, stretched to  cols x rows  tiles."""
    panel = Image.new("RGBA", (32 * cols, 32 * rows), (0, 0, 0, 0))
    for r in range(rows):
        pattern = 1 if r == 0 else (3 if r == rows - 1 else 2)
        for i in range(cols):
            c = 4 if i == 0 else (6 if i == cols - 1 else 5)
            panel.alpha_composite(load(f"Interface_Row{pattern}_Column{c}_32x32.png"),
                                  (i * 32, r * 32))
    return panel


SCROLL_TRACK = {
    "inactive": ("Scrollbar-UP-DOWN-Top-Edge-Inactive.png",
                 "Scrollbar-MiddleFill-Inactive.png",
                 "Scrollbar-UP-DOWN-Bottom-Edge-Inactive.png"),
    "hover": ("Scrollbar-UP-DOWN-Top-Edge-Hover.png",
              "Scrollbar-MiddleFill-Hover.png",
              "Scrollbar-UP-DOWN-Bottom-Edge-Hover.png"),
    "active": ("Scrollbar-UP-DOWN-Top-Edge-Active.png",
               "Scrollbar-MiddleFill-Active.png",
               "Scrollbar-UP-DOWN-Bottom-Edge-active.png"),
}


def build_scrollbar(state, height=320):
    """Vertical scrollbar track: top arrow + fill + bottom arrow."""
    top, fill, bottom = SCROLL_TRACK[state]
    strip = Image.new("RGBA", (32, height), (0, 0, 0, 0))
    strip.alpha_composite(load(top), (0, 0))
    for y in range(32, height - 32, 32):
        strip.alpha_composite(load(fill), (0, y))
    strip.alpha_composite(load(bottom), (0, height - 32))
    return strip


def build_static_scene(close_at=(321, 33)):
    """Everything that never changes: fill, ornate border, close x."""
    scene = Image.new("RGBA", (WIDTH, HEIGHT), FILL)
    scene.alpha_composite(load("Border-Top-left-Corner.png"), (0, 0))
    scene.alpha_composite(load("Border-Top-right-Corner.png"), (WIDTH - 32, 0))
    scene.alpha_composite(load("Border-Bottom-Left-Corner.png"), (0, HEIGHT - 32))
    scene.alpha_composite(load("Border-Bottom-Right-Corner.png"), (WIDTH - 32, HEIGHT - 32))
    for x in range(32, WIDTH - 32, 32):
        scene.alpha_composite(load("Border-Top.png"), (x, 0))
        scene.alpha_composite(load("Border-Bottom.png"), (x, HEIGHT - 32))
    for y in range(32, HEIGHT - 32, 32):
        scene.alpha_composite(load("Border-Left.png"), (0, y))
        scene.alpha_composite(load("Border-Right.png"), (WIDTH - 32, y))
    scene.alpha_composite(load("x.png"), close_at)
    return scene


# ------------------------------------------------------------- geometry -----

BATCH_ORIGIN = (33, 32)              # Batch button sits exactly 16 px above Import
ABOUT_ORIGIN = (224, 32)             # About button, right above Slice
IMPORT_ORIGIN = (33, 112)
SLICE_ORIGIN = (224, 113)


def build_slice_button(state, squish=True):
    pairs = {
        "idle": ("Button-Inactive-Left.png", "Button-Inactive-Right.png"),
        "hover": ("Button-Hover-Left.png", "Button-Hover-Right.png"),
        "pressed": ("Button-Pressed-Left.png", "Button-Pressed-Right.png"),
    }[state]
    return build_button(pairs[0], pairs[1], squish=squish,
                        text="Slice", text_pos=(35, 28), text_color=TEXT_WHITE)


BANNER_X = 64                        # selection banners, centered: 256 wide
BANNER_W, BANNER_H = 256, 64
BANNER_LABEL_Y = 35                  # label center inside the banner art
ROW_GAP = 16                         # air between the banner rows

ROW1_Y = 176                         # selection banner tops
ROW2_Y = ROW1_Y + BANNER_H + ROW_GAP    # 256
ROW3_Y = ROW2_Y + BANNER_H + ROW_GAP    # 336

BATCH_RECT = (31, 30, 163, 98)
ABOUT_RECT = (222, 30, 354, 98)
IMPORT_RECT = (31, 110, 163, 176)
SLICE_RECT = (222, 111, 354, 176)
BANNER32_RECT = (BANNER_X - 2, ROW1_Y, BANNER_X + BANNER_W + 2, ROW1_Y + BANNER_H + 2)
BANNER16_RECT = (BANNER_X - 2, ROW2_Y, BANNER_X + BANNER_W + 2, ROW2_Y + BANNER_H + 2)
BANNERCUSTOM_RECT = (BANNER_X - 2, ROW3_Y, BANNER_X + BANNER_W + 2, ROW3_Y + BANNER_H + 2)
CLOSE_ART = (321, 33)                # close x in the batch / about windows
CLOSE_RECT = (322, 34, 352, 64)
MAIN_CLOSE_ART = (176, 48)           # main window: between Batch and About
MAIN_CLOSE_RECT = (177, 49, 207, 79)

PROMPT_ORIGIN = (64, 384)            # prefix area, bottom of the window
PROMPT_COLS = 8                      # 256 x 96
PROMPT_CX = 192
PROMPT_TITLE_Y = PROMPT_ORIGIN[1] + 16
PROMPT_VALUE_Y = PROMPT_ORIGIN[1] + 48
PROMPT_VALUE_MAX_W = 192
OK_CENTER = (168, PROMPT_ORIGIN[1] + 80)
NO_CENTER = (216, PROMPT_ORIGIN[1] + 80)
OK_RECT = (OK_CENTER[0] - 20, OK_CENTER[1] - 12, OK_CENTER[0] + 20, OK_CENTER[1] + 12)
NO_RECT = (NO_CENTER[0] - 20, NO_CENTER[1] - 12, NO_CENTER[0] + 20, NO_CENTER[1] + 12)
DIMMAX = 200                         # custom dims text width inside the banner

TOAST_Y = 424

# batch window
B_SLICE_ORIGIN = (224, 65)
B_SLICE_RECT = (222, 64, 354, 129)
B_OPT_CB_X = 48
B_OPT_TEXT_X = 88
B_OPT32_Y = 64
B_OPT16_Y = 112
B_OPT32_RECT = (46, 62, 172, 98)
B_OPT16_RECT = (46, 110, 172, 146)
B_LIST_X, B_LIST_Y = 48, 160
B_LIST_COLS, B_LIST_ROWS = 8, 10     # 256 x 320 panel
B_ENTRY_H = 32
B_VISIBLE = B_LIST_ROWS - 2          # entries per page
B_SCROLL_X = 304
B_SCROLL_H = 32 * B_LIST_ROWS
B_THUMB_H = 27
B_THUMB_TOP = 36                     # thumb travel: 36 .. 36+221
B_THUMB_TRAVEL = B_SCROLL_H - 2 * B_THUMB_TOP - B_THUMB_H
B_TOAST_Y = 152

# about window: centred lines, top to bottom
AB_HEAD_Y = 112                      # "TileSlicer"
AB_DESC1_Y, AB_DESC2_Y = 168, 200    # what the app does
AB_CREDITS_Y = 264                   # "Credits"
AB_NAME_Y = 328                      # "Hypnobius"
AB_ROLE_Y = 364                      # "interface design tilesets"
AB_FONT_NAME_Y = 404                 # "datagoblin"
AB_FONT_ROLE_Y = 440                 # "monogram.ttf pixel font"

SIZE_RE = re.compile(r"\s*(\d{1,4})\s*[xX]\s*(\d{1,4})\s*$")


def in_rect(pos, rect):
    x, y = pos
    x0, y0, x1, y1 = rect
    return x0 <= x < x1 and y0 <= y < y1


def clean_prefix(text, fallback="Tiles"):
    """Strip characters Windows can't use in file names."""
    prefix = "".join(ch for ch in text if ch not in '<>:"/\\|?*').strip()
    return prefix or fallback or "Tiles"


def undecorate(window):
    """Drop the OS title bar (it breaks the pixel-art look) while keeping the
    window in the taskbar / Alt-Tab on Windows."""
    window.overrideredirect(True)
    if os.name != "nt":
        return

    def apply():
        try:
            import ctypes
            user32 = ctypes.windll.user32
            get = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_ = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000
            hwnds = {window.winfo_id(), user32.GetParent(window.winfo_id())}
            for hwnd in hwnds:
                if hwnd:
                    style = get(hwnd, GWL_EXSTYLE)
                    set_(hwnd, GWL_EXSTYLE, (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW)
        except Exception:
            pass

    apply()
    # Tk marks the override-redirect toplevel as a tool window when it is
    # mapped, so the style has to be re-applied once the window is up.
    window.after(200, apply)


BUTTON_PAIRS = {
    "idle": ("Button-Inactive-Left.png", "Button-Inactive-Right.png"),
    "hover": ("Button-Hover-Left.png", "Button-Hover-Right.png"),
    "pressed": ("Button-Pressed-Left.png", "Button-Pressed-Right.png"),
}


# ------------------------------------------------------------- slicing ------

def slice_image(image_path, prefix, tile_w, tile_h=None, export_dir=EXPORT_DIR):
    """Cut image_path into tile_w x tile_h tiles, named
    Prefix_Row#_Column#_WxH.png"""
    if tile_h is None:
        tile_h = tile_w
    img = Image.open(image_path).convert("RGBA")
    width, height = img.size
    rows, cols = height // tile_h, width // tile_w
    os.makedirs(export_dir, exist_ok=True)
    count = 0
    for r in range(rows):
        for c in range(cols):
            tile = img.crop((c * tile_w, r * tile_h, (c + 1) * tile_w, (r + 1) * tile_h))
            name = f"{prefix}_Row{r + 1}_Column{c + 1}_{tile_w}x{tile_h}.png"
            tile.save(os.path.join(export_dir, name))
            count += 1
    return count, rows, cols


# ------------------------------------------------------- shared painting ----

def draw_prompt_panel(img, title, value, caret_on, hover):
    """The bottom parchment prefix area, shared by both windows."""
    img.alpha_composite(build_window_panel(PROMPT_COLS, 3), PROMPT_ORIGIN)
    paste_centered(img, text_image(title, FONT_SIZE, TEXT_DARK, max_width=PROMPT_VALUE_MAX_W + 32),
                   PROMPT_CX, PROMPT_TITLE_Y)
    txt = text_image(value, FONT_SIZE, TEXT_DARK, max_width=PROMPT_VALUE_MAX_W)
    vx = round(PROMPT_CX - txt.width / 2)
    img.alpha_composite(txt, (vx, round(PROMPT_VALUE_Y - txt.height / 2)))
    if caret_on:
        caret_x = vx + txt.width + 2
        img.paste(TEXT_DARK, (caret_x, PROMPT_VALUE_Y - 7, caret_x + 2, PROMPT_VALUE_Y + 7))
    ok_color = TEXT_BLUE if hover == "ok" else TEXT_DARK
    no_color = TEXT_BLUE if hover == "no" else TEXT_DARK
    paste_centered(img, text_image("OK", FONT_SIZE, ok_color), OK_CENTER[0], OK_CENTER[1])
    paste_centered(img, text_image("No", FONT_SIZE, no_color), NO_CENTER[0], NO_CENTER[1])


class CanvasApp:
    """Common canvas plumbing: photo swap, blinking caret, toast."""

    def __init__(self):
        self.hover = None
        self.press = None
        self.toast = None
        self._toast_token = 0
        self.prompt_open = False
        self.prompt_text = ""
        self.prompt_title = "Prefix"
        self.prompt_hover = None
        self.prompt_press = None
        self.caret_on = True
        self._blink_scheduled = False
        self._item = None
        self._drag = None               # window-move drag state
        self._drag_moved = False

    def render(self):
        img = self.compose()
        self._photo = ImageTk.PhotoImage(img)
        if self._item is None:
            self._item = self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        else:
            self.canvas.itemconfig(self._item, image=self._photo)

    def show_toast(self, text, color):
        self._toast_token += 1
        token = self._toast_token
        self.toast = (text, color, token)
        self.render()

        def clear():
            if self.toast and self.toast[2] == token:
                self.toast = None
                self.render()
        self.root.after(1900, clear)

    def _ensure_blink(self):
        if not self._blink_scheduled:
            self._blink_scheduled = True
            self.root.after(530, self._blink)

    def _blink(self):
        self._blink_scheduled = False
        if self.prompt_open or getattr(self, "custom_editing", False):
            self.caret_on = not self.caret_on
            self.render()
            self._ensure_blink()

    def tag_prompt(self):
        self.prompt_open = False
        self.prompt_press = self.prompt_hover = None

    def on_key_prompt(self, event):
        """Shared prompt typing. Returns True when the key was consumed."""
        key = event.keysym
        if key == "Escape":
            self.on_prompt_cancel()
            return True
        if key in ("Return", "KP_Enter"):
            self.on_prompt_confirm()
            return True
        if key == "BackSpace":
            self.prompt_text = self.prompt_text[:-1]
            self.caret_on = True
            self.render()
            return True
        if event.char and event.char.isprintable() and len(self.prompt_text) < 60:
            self.prompt_text += event.char
            self.caret_on = True
            self.render()
            return True
        return False

    def preview_caret_flip(self):
        self.caret_on = not self.caret_on
        img = self.compose()
        self.caret_on = not self.caret_on
        return img


# ------------------------------------------------------------------ app -----

class TileSlicerGUI(CanvasApp):
    def __init__(self):
        # keep 1 screen pixel = 1 art pixel on high-dpi displays
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        self.root = tk.Tk()
        self.root.title("TileSlicer")
        self.root.configure(bg="#2e322a")
        self.root.resizable(False, False)
        undecorate(self.root)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{WIDTH}x{HEIGHT}+{(sw - WIDTH) // 2}+{max(20, (sh - HEIGHT) // 2 - 60)}")
        try:
            self.root.tk.call("tk", "scaling", 1.0)
        except tk.TclError:
            pass

        self.canvas = tk.Canvas(self.root, width=WIDTH, height=HEIGHT,
                                highlightthickness=0, bd=0, bg="#2e322a")
        self.canvas.pack()
        super().__init__()

        try:                                     # the official TileSlicer icon
            icon = Image.open(os.path.join(ASSET_DIR, "TileSlicer.png")).convert("RGBA")
        except OSError:
            icon = load("Checkbox-Hover.png")
        self._icon = ImageTk.PhotoImage(icon.resize((64, 64), Image.NEAREST))
        try:
            self.root.iconphoto(True, self._icon)
        except tk.TclError:
            pass

        # pre-assembled graphics -------------------------------------------
        self.scene = build_static_scene(MAIN_CLOSE_ART)
        self.btn_batch = {
            state: build_button(left, right,
                                text="Batch", text_pos=(39, 27), text_color=TEXT_WHITE)
            for state, (left, right) in BUTTON_PAIRS.items()
        }
        self.btn_about = {
            state: build_button(BUTTON_PAIRS[state][0], BUTTON_PAIRS[state][1],
                                text="About", text_pos=(35, 27), text_color=TEXT_WHITE)
            for state in BUTTON_PAIRS
        }
        self.btn_import = {
            state: build_button(BUTTON_PAIRS[state][0], BUTTON_PAIRS[state][1],
                                text="Import", text_pos=(28, 27), text_color=TEXT_WHITE)
            for state in BUTTON_PAIRS
        }
        self.btn_slice = {s: build_slice_button(s) for s in ("idle", "hover", "pressed")}
        self.banner_active = load("Active selection box.png")
        self.banner_inactive = load("Inactive selection box.png")
        self.banners = {
            32: (self._labeled_banner(self.banner_inactive, "32 x 32"),
                 self._labeled_banner(self.banner_active, "32 x 32")),
            16: (self._labeled_banner(self.banner_inactive, "16 x 16"),
                 self._labeled_banner(self.banner_active, "16 x 16")),
        }

        # interaction state --------------------------------------------------
        self.image_path = None
        self.mode = 16                  # 32 | 16 | "custom"
        self.custom_text = ""           # W x H typed into the custom banner
        self.custom_editing = False
        self.batch_windows = []
        self.about_window = None

        self.render()

        # events --------------------------------------------------------------
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Leave>", self.on_leave)
        self.root.bind("<Key>", self.on_key)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self.root.focus_force()

    def _labeled_banner(self, banner, label):
        """A selection banner (active or inactive art) with its label baked on."""
        banner = banner.copy()
        paste_centered(banner, text_image(label, SMALL_FONT, TEXT_WHITE),
                       BANNER_W / 2, BANNER_LABEL_Y)
        return banner

    # ------------------------------------------------------------ drawing --

    def _button_image(self, name):
        table = {"batch": self.btn_batch, "about": self.btn_about,
                 "import": self.btn_import, "slice": self.btn_slice}[name]
        if self.press == name:
            return table["pressed"]
        if self.hover == name:
            return table["hover"]
        return table["idle"]

    def _custom_banner_image(self):
        banner = (self.banner_active if self.mode == "custom" else self.banner_inactive).copy()
        show_caret = self.custom_editing and self.caret_on
        text = self.custom_text
        if text:
            ti = text_image(text, SMALL_FONT, TEXT_WHITE, max_width=DIMMAX)
        else:
            ti = text_image("??x??", SMALL_FONT, TEXT_GRAY)
        cx = BANNER_W / 2
        paste_centered(banner, ti, cx, BANNER_LABEL_Y)
        if show_caret:
            caret_x = round(cx + ti.width / 2) + 2
            banner.paste(TEXT_WHITE,
                         (caret_x, BANNER_LABEL_Y - 7, caret_x + 2, BANNER_LABEL_Y + 7))
        return banner

    def compose(self):
        """The complete frame for the current UI state, as a PIL image."""
        img = self.scene.copy()
        img.alpha_composite(self._button_image("batch"), BATCH_ORIGIN)
        img.alpha_composite(self._button_image("about"), ABOUT_ORIGIN)
        img.alpha_composite(self._button_image("import"), IMPORT_ORIGIN)
        img.alpha_composite(self._button_image("slice"), SLICE_ORIGIN)
        for wanted, y in ((32, ROW1_Y), (16, ROW2_Y)):
            inactive, active = self.banners[wanted]
            img.alpha_composite(active if self.mode == wanted else inactive, (BANNER_X, y))
        img.alpha_composite(self._custom_banner_image(), (BANNER_X, ROW3_Y))
        if self.toast:
            text, color, _ = self.toast
            paste_centered(img, text_image(text, FONT_SIZE, color, max_width=352),
                           WIDTH / 2, TOAST_Y)
        if self.prompt_open:
            draw_prompt_panel(img, self.prompt_title, self.prompt_text,
                              self.caret_on, self.prompt_hover)
        return img

    # ------------------------------------------------------------ helpers --

    def hit(self, pos):
        for name, rect in (("batch", BATCH_RECT), ("about", ABOUT_RECT),
                           ("import", IMPORT_RECT), ("slice", SLICE_RECT),
                           ("close", MAIN_CLOSE_RECT),
                           ("banner32", BANNER32_RECT), ("banner16", BANNER16_RECT),
                           ("bannercustom", BANNERCUSTOM_RECT)):
            if in_rect(pos, rect):
                return name
        return None

    def current_tile_size(self):
        """(w, h) selected right now, or None if the custom text is invalid."""
        if self.mode != "custom":
            return (self.mode, self.mode)
        m = SIZE_RE.fullmatch(self.custom_text)
        if not m or int(m.group(1)) < 1 or int(m.group(2)) < 1:
            return None
        return (int(m.group(1)), int(m.group(2)))

    def _apply_hover(self, pos):
        if self.prompt_open:
            hover = "ok" if in_rect(pos, OK_RECT) else ("no" if in_rect(pos, NO_RECT) else None)
            if hover != self.prompt_hover:
                self.prompt_hover = hover
                self.render()
            self.canvas.configure(cursor="hand2" if hover else "")
            return
        hover = self.hit(pos)
        if hover == "bannercustom":
            cursor = "xterm"
        elif hover:
            cursor = "hand2"
        else:
            cursor = ""
        self.canvas.configure(cursor=cursor)
        if hover != self.hover:
            self.hover = hover
            self.render()

    # ------------------------------------------------------------- events --

    def on_motion(self, event):
        if self._drag is not None:
            dx, dy, sx, sy = self._drag
            if not self._drag_moved:
                if abs(event.x_root - sx) < 3 and abs(event.y_root - sy) < 3:
                    return
                self._drag_moved = True
            self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")
            return
        self._apply_hover((event.x, event.y))

    def on_press(self, event):
        self.root.focus_force()
        if self.prompt_open:
            self.prompt_press = self.prompt_hover
            return
        self.press = self.hit((event.x, event.y))
        if self.press is None:          # empty space / border: start a window drag
            self._drag = (event.x_root - self.root.winfo_x(),
                          event.y_root - self.root.winfo_y(),
                          event.x_root, event.y_root)
            self._drag_moved = False
        else:
            self.render()

    def on_release(self, event):
        pos = (event.x, event.y)
        if self._drag is not None:
            moved = self._drag_moved
            self._drag = None
            if moved:                   # the window was dragged, not clicked
                return
        if self.prompt_open:
            target = "ok" if in_rect(pos, OK_RECT) else ("no" if in_rect(pos, NO_RECT) else None)
            if target and target == self.prompt_press:
                if target == "ok":
                    self.on_prompt_confirm()
                else:
                    self.on_prompt_cancel()
            self.prompt_press = None
            return
        pressed, self.press = self.press, None
        self.hover = self.hit(pos)
        self.render()
        if pressed and pressed == self.hover:
            self.activate(pressed)
        elif self.custom_editing and not self.hover:
            self.custom_editing = False
            self.render()

    def on_leave(self, event):
        if self.prompt_open:
            if self.prompt_hover:
                self.prompt_hover = None
                self.render()
            return
        if self.hover or self.press:
            self.hover = self.press = None
            self.render()

    def activate(self, name):
        if name != "bannercustom":
            self.custom_editing = False
        if name == "close":
            self.root.destroy()
        elif name == "banner32":
            self.mode = 32
            self.render()
        elif name == "banner16":
            self.mode = 16
            self.render()
        elif name == "bannercustom":
            self.mode = "custom"
            self.custom_editing = True
            self.caret_on = True
            self._ensure_blink()
            self.render()
        elif name == "batch":
            paths = filedialog.askopenfilenames(
                title="Choose images for batch slicing",
                filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                           ("All files", "*.*")])
            if paths:
                self.open_batch(list(paths))
            else:
                self.render()
        elif name == "about":
            self.open_about()
        elif name == "import":
            path = filedialog.askopenfilename(
                title="Choose an image to slice",
                filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("All files", "*.*")])
            if path:
                self.image_path = path
                self.show_toast(f"Loaded {os.path.basename(path)}", TEXT_GOLD)
            else:
                self.render()
        elif name == "slice":
            if not self.image_path:
                self.show_toast("Import an image first", TEXT_RED)
            elif self.current_tile_size() is None:
                self.mode = "custom"
                self.custom_editing = True
                self._ensure_blink()
                self.show_toast("Enter a size like 24x24", TEXT_RED)
            else:
                self.open_prompt()

    def open_batch(self, paths):
        """Open the batch window for  paths  (also used by tests)."""
        self.batch_windows = [w for w in self.batch_windows
                              if getattr(w, "alive", False)]
        win = BatchWindow(self, paths)
        self.batch_windows.append(win)
        return win

    def open_about(self):
        """Open the credits window, or bring it forward if it is already up."""
        win = self.about_window
        if win is not None and win.alive:
            win.root.lift()
            win.root.focus_force()
            return win
        self.about_window = AboutWindow(self)
        return self.about_window

    # ------------------------------------------------------------- prompt --

    def open_prompt(self):
        stem = os.path.splitext(os.path.basename(self.image_path))[0]
        self.prompt_title = "Prefix"
        self.prompt_text = stem[:60]
        self.prompt_open = True
        self.prompt_hover = self.prompt_press = None
        self.caret_on = True
        self._ensure_blink()
        self.render()

    def close_prompt(self):
        self.tag_prompt()
        self.render()

    def on_prompt_cancel(self):
        self.close_prompt()

    def on_prompt_confirm(self):
        prefix = clean_prefix(self.prompt_text,
                              os.path.splitext(os.path.basename(self.image_path))[0] or "Tiles")
        size = self.current_tile_size()
        self.close_prompt()
        if size is None:
            self.show_toast("Enter a size like 24x24", TEXT_RED)
            return
        try:
            count, rows, cols = slice_image(self.image_path, prefix, size[0], size[1])
            if count == 0:
                self.show_toast("No tiles: image smaller than tile", TEXT_RED)
                return
            print(f"Sliced {count} tiles ({rows} rows x {cols} columns) to {EXPORT_DIR}")
            self.show_toast(f"Sliced {count} tiles", TEXT_GOLD)
        except Exception as exc:                       # noqa: BLE001
            print("Slice failed:", exc)
            self.show_toast("Slice failed", TEXT_RED)

    def on_key(self, event):
        if self.prompt_open:
            self.on_key_prompt(event)
        elif self.custom_editing:
            key = event.keysym
            if key in ("Escape", "Return", "KP_Enter"):
                self.custom_editing = False
                self.render()
            elif key == "BackSpace":
                self.custom_text = self.custom_text[:-1]
                self.caret_on = True
                self.render()
            elif event.char and event.char in "0123456789xX " and len(self.custom_text) < 12:
                self.custom_text += event.char
                self.caret_on = True
                self.render()

    # ---------------------------------------------------------------- run --

    def run(self):
        self.root.mainloop()


# ------------------------------------------------------------ batch window --

class BatchWindow(CanvasApp):
    """A 384x512 window listing several images; slices them all at once."""

    def __init__(self, parent, paths):
        self.parent = parent
        self.paths = list(paths)
        self.names = [os.path.basename(p) for p in self.paths]
        self.size = 16
        self.scroll = 0
        self.scroll_hover = False
        self.dragging = False
        self.drag_off = 0
        self.alive = True

        self.root = tk.Toplevel(parent.root)
        self.root.title("TileSlicer - Batch")
        self.root.configure(bg="#2e322a")
        self.root.resizable(False, False)
        undecorate(self.root)
        self.canvas = tk.Canvas(self.root, width=WIDTH, height=HEIGHT,
                                highlightthickness=0, bd=0, bg="#2e322a")
        self.canvas.pack()
        super().__init__()

        try:
            px = parent.root.winfo_rootx() + WIDTH + 24
            py = parent.root.winfo_rooty()
            self.root.geometry(f"{WIDTH}x{HEIGHT}+{px}+{py}")
        except tk.TclError:
            pass

        # pre-assembled graphics -------------------------------------------
        self.scene = build_static_scene()
        self.btn_slice = {s: build_slice_button(s) for s in ("idle", "hover", "pressed")}
        self.cb_idle = load("Checkbox-Inactive.png")
        self.cb_hover = load("Checkbox-Hover.png")
        self.cb_pressed = load("Checkbox-Pressed.png")
        self.cb_checked = load("Checkbox-Hover.png").copy()
        self.cb_checked.alpha_composite(load("x.png"))
        self.list_panel = build_window_panel(B_LIST_COLS, B_LIST_ROWS)
        self.scroll_strips = {s: build_scrollbar(s) for s in ("inactive", "hover", "active")}
        self.thumb = load("Scrollbar-UP-DOWN-Moving-Bar.png")
        self.opt32 = text_image("32 x 32", FONT_SIZE, TEXT_GOLD)
        self.opt16 = text_image("16 x 16", FONT_SIZE, TEXT_GOLD)

        # slicing bookkeeping
        self.prefix_map = {}
        self.used_fold = set()
        self.conflict_q = []
        self.prompt_for = None

        self.render()

        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Leave>", self.on_leave)
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.root.bind("<Key>", self.on_key)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.focus_force()

    # ------------------------------------------------------------ helpers --

    @property
    def max_scroll(self):
        return max(0, len(self.paths) - B_VISIBLE)

    def thumb_y(self):
        """y offset of the thumb inside the scroll strip."""
        if self.max_scroll == 0:
            return B_THUMB_TOP
        frac = self.scroll / self.max_scroll
        return round(B_THUMB_TOP + frac * B_THUMB_TRAVEL)

    def thumb_rect(self):
        return (B_SCROLL_X + 2, B_LIST_Y + self.thumb_y() - 4,
                B_SCROLL_X + 30, B_LIST_Y + self.thumb_y() + B_THUMB_H + 4)

    def scroll_zone(self, pos):
        x, y = pos
        return (B_SCROLL_X <= x < B_SCROLL_X + 32 and
                B_LIST_Y <= y < B_LIST_Y + B_SCROLL_H and len(self.paths) > B_VISIBLE)

    def hit(self, pos):
        for name, rect in (("slice", B_SLICE_RECT), ("close", CLOSE_RECT),
                           ("opt32", B_OPT32_RECT), ("opt16", B_OPT16_RECT)):
            if in_rect(pos, rect):
                return name
        if self.scroll_zone(pos):
            return "scroll"
        return None

    def _checkbox_image(self, value):
        name = f"opt{value}"
        if self.size == value:
            return self.cb_checked
        if self.hover == name and self.press != name:
            return self.cb_hover
        if self.press == name:
            return self.cb_pressed
        return self.cb_idle

    def _button_image(self, name):
        if self.press == name:
            return self.btn_slice["pressed"]
        if self.hover == name:
            return self.btn_slice["hover"]
        return self.btn_slice["idle"]

    # ------------------------------------------------------------ drawing --

    def compose(self):
        img = self.scene.copy()
        img.alpha_composite(self._button_image("slice"), B_SLICE_ORIGIN)
        for value, y in ((32, B_OPT32_Y), (16, B_OPT16_Y)):
            img.alpha_composite(self._checkbox_image(value), (B_OPT_CB_X, y))
            label = self.opt32 if value == 32 else self.opt16
            img.alpha_composite(label, (B_OPT_TEXT_X, round(y + 16 - label.height / 2)))
        img.alpha_composite(self.list_panel, (B_LIST_X, B_LIST_Y))
        for i in range(min(B_VISIBLE, len(self.paths) - self.scroll)):
            name = self.names[self.scroll + i]
            txt = text_image(name, FONT_SIZE, TEXT_DARK, max_width=B_LIST_COLS * 32 - 32)
            img.alpha_composite(txt, (B_LIST_X + 16,
                                      B_LIST_Y + 32 + i * B_ENTRY_H + round(16 - txt.height / 2)))
        if len(self.paths) > B_VISIBLE:
            state = "active" if self.dragging else ("hover" if self.scroll_hover else "inactive")
            img.alpha_composite(self.scroll_strips[state], (B_SCROLL_X, B_LIST_Y))
            img.alpha_composite(self.thumb, (B_SCROLL_X, B_LIST_Y + self.thumb_y()))
        if self.toast:
            text, color, _ = self.toast
            paste_centered(img, text_image(text, FONT_SIZE, color, max_width=352),
                           WIDTH / 2, B_TOAST_Y)
        if self.prompt_open:
            draw_prompt_panel(img, self.prompt_title, self.prompt_text,
                              self.caret_on, self.prompt_hover)
        return img

    # ------------------------------------------------------------- events --

    def _apply_hover(self, pos):
        if self.prompt_open:
            hover = "ok" if in_rect(pos, OK_RECT) else ("no" if in_rect(pos, NO_RECT) else None)
            if hover != self.prompt_hover:
                self.prompt_hover = hover
                self.render()
            self.canvas.configure(cursor="hand2" if hover else "")
            return
        hover = self.hit(pos)
        in_scroll = hover == "scroll"
        if in_scroll != self.scroll_hover:
            self.scroll_hover = in_scroll
            self.render()
        self.canvas.configure(cursor="hand2" if hover else "")
        if hover != self.hover:
            self.hover = hover
            self.render()

    def on_motion(self, event):
        pos = (event.x, event.y)
        if self.dragging:
            y = min(max(pos[1] - self.drag_off, B_LIST_Y + B_THUMB_TOP),
                    B_LIST_Y + B_THUMB_TOP + B_THUMB_TRAVEL)
            frac = (y - B_LIST_Y - B_THUMB_TOP) / B_THUMB_TRAVEL if B_THUMB_TRAVEL else 0
            self.scroll = round(frac * self.max_scroll)
            self.render()
            return
        if self._drag is not None:
            dx, dy, sx, sy = self._drag
            if not self._drag_moved:
                if abs(event.x_root - sx) < 3 and abs(event.y_root - sy) < 3:
                    return
                self._drag_moved = True
            self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")
            return
        self._apply_hover(pos)

    def on_press(self, event):
        self.root.focus_force()
        if self.prompt_open:
            self.prompt_press = self.prompt_hover
            return
        pos = (event.x, event.y)
        if len(self.paths) > B_VISIBLE and in_rect(pos, self.thumb_rect()):
            self.dragging = True
            self.drag_off = pos[1] - (B_LIST_Y + self.thumb_y())
            self.render()
            return
        self.press = self.hit(pos)
        if self.press is None:          # empty space / border: start a window drag
            self._drag = (event.x_root - self.root.winfo_x(),
                          event.y_root - self.root.winfo_y(),
                          event.x_root, event.y_root)
            self._drag_moved = False
        else:
            self.render()

    def on_release(self, event):
        pos = (event.x, event.y)
        if self.dragging:
            self.dragging = False
            self._apply_hover(pos)
            self.render()
            return
        if self._drag is not None:
            moved = self._drag_moved
            self._drag = None
            if moved:                   # the window was dragged, not clicked
                return
        if self.prompt_open:
            target = "ok" if in_rect(pos, OK_RECT) else ("no" if in_rect(pos, NO_RECT) else None)
            if target and target == self.prompt_press:
                if target == "ok":
                    self.on_prompt_confirm()
                else:
                    self.on_prompt_cancel()
            self.prompt_press = None
            return
        pressed, self.press = self.press, None
        self.hover = self.hit(pos)
        self.render()
        if pressed and pressed == self.hover:
            self.activate(pressed)

    def on_leave(self, event):
        if self.prompt_open:
            if self.prompt_hover:
                self.prompt_hover = None
                self.render()
            return
        if self.hover or self.press or self.scroll_hover:
            self.hover = self.press = None
            self.scroll_hover = False
            self.render()

    def on_wheel(self, event):
        if self.prompt_open or self.max_scroll == 0:
            return
        self.scroll = min(max(self.scroll + (-1 if event.delta > 0 else 1), 0),
                          self.max_scroll)
        self.render()

    def activate(self, name):
        if name == "close":
            self.close()
        elif name == "opt32":
            self.size = 32
            self.render()
        elif name == "opt16":
            self.size = 16
            self.render()
        elif name == "slice":
            self.start_slice()

    def close(self):
        self.alive = False
        self.root.destroy()

    # ------------------------------------------------------ batch slicing --

    def start_slice(self):
        def stem(p):
            return os.path.splitext(os.path.basename(p))[0]

        groups = defaultdict(list)
        for p in self.paths:
            groups[clean_prefix(stem(p)).casefold()].append(p)
        conflicts = [p for g in groups.values() if len(g) > 1 for p in g]

        self.prefix_map = {p: clean_prefix(stem(p)) for p in self.paths if p not in conflicts}
        self.used_fold = {v.casefold() for v in self.prefix_map.values()}
        self.conflict_q = list(conflicts)
        self.next_conflict()

    def next_conflict(self):
        if self.conflict_q:
            path = self.conflict_q.pop(0)
            self.prompt_for = path
            self.prompt_title = os.path.basename(path)
            self.prompt_text = os.path.splitext(self.prompt_title)[0][:60]
            self.prompt_open = True
            self.prompt_hover = self.prompt_press = None
            self.caret_on = True
            self._ensure_blink()
            self.render()
        else:
            self.slice_all()

    def on_prompt_confirm(self):
        stem = os.path.splitext(os.path.basename(self.prompt_for))[0]
        cand = clean_prefix(self.prompt_text, stem or "Tiles")
        if cand.casefold() in self.used_fold:
            self.show_toast("Prefix already used", TEXT_RED)
            return
        self.used_fold.add(cand.casefold())
        self.prefix_map[self.prompt_for] = cand
        self.tag_prompt()
        self.render()
        self.next_conflict()

    def on_prompt_cancel(self):
        self.tag_prompt()
        self.conflict_q = []
        self.render()

    def slice_all(self):
        total = skipped = 0
        for path in self.paths:
            prefix = self.prefix_map.get(path)
            if not prefix:
                skipped += 1
                continue
            try:
                count, _, _ = slice_image(path, prefix, self.size, self.size)
                total += count
                if count == 0:
                    skipped += 1
            except Exception as exc:                   # noqa: BLE001
                print("Slice failed:", path, exc)
                skipped += 1
        msg = f"Sliced {total} tiles"
        if skipped:
            msg += f" ({skipped} skipped)"
        print(f"Batch sliced {len(self.paths)} images: {msg} to {EXPORT_DIR}")
        self.show_toast(msg, TEXT_RED if total == 0 else TEXT_GOLD)

    def on_key(self, event):
        if self.prompt_open:
            self.on_key_prompt(event)


class AboutWindow(CanvasApp):
    """The credits window: same decor as the others, no controls besides the x."""

    def __init__(self, parent):
        self.parent = parent
        self.alive = True

        self.root = tk.Toplevel(parent.root)
        self.root.title("TileSlicer - About")
        self.root.configure(bg="#2e322a")
        self.root.resizable(False, False)
        undecorate(self.root)
        self.canvas = tk.Canvas(self.root, width=WIDTH, height=HEIGHT,
                                highlightthickness=0, bd=0, bg="#2e322a")
        self.canvas.pack()
        super().__init__()

        try:
            px = parent.root.winfo_rootx() + WIDTH + 24
            py = parent.root.winfo_rooty()
            self.root.geometry(f"{WIDTH}x{HEIGHT}+{px}+{py}")
        except tk.TclError:
            pass

        # pre-assembled graphics -------------------------------------------
        self.scene = build_static_scene()
        self.heading = text_image("TileSlicer", FONT_SIZE, TEXT_GOLD)
        self.desc1 = text_image("Slice pixel-art tilesheets", FONT_SIZE, TEXT_WHITE)
        self.desc2 = text_image("into 16x16 or 32x32 tiles", FONT_SIZE, TEXT_WHITE)
        self.credits_head = text_image("Credits", FONT_SIZE, TEXT_GOLD)
        self.name = text_image("Hypnobius", FONT_SIZE, TEXT_WHITE)
        self.role = text_image("interface design tilesets", FONT_SIZE, TEXT_GRAY)
        self.font_name = text_image("datagoblin", FONT_SIZE, TEXT_WHITE)
        self.font_role = text_image("monogram.ttf pixel font", FONT_SIZE, TEXT_GRAY)

        self.render()

        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Leave>", self.on_leave)
        self.root.bind("<Key>", self.on_key)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.focus_force()

    # ------------------------------------------------------------ helpers --

    def hit(self, pos):
        return "close" if in_rect(pos, CLOSE_RECT) else None

    def _apply_hover(self, pos):
        hover = self.hit(pos)
        self.canvas.configure(cursor="hand2" if hover else "")
        if hover != self.hover:
            self.hover = hover
            self.render()

    # ------------------------------------------------------------ drawing --

    def compose(self):
        img = self.scene.copy()
        paste_centered(img, self.heading, 192, AB_HEAD_Y)
        paste_centered(img, self.desc1, 192, AB_DESC1_Y)
        paste_centered(img, self.desc2, 192, AB_DESC2_Y)
        paste_centered(img, self.credits_head, 192, AB_CREDITS_Y)
        paste_centered(img, self.name, 192, AB_NAME_Y)
        paste_centered(img, self.role, 192, AB_ROLE_Y)
        paste_centered(img, self.font_name, 192, AB_FONT_NAME_Y)
        paste_centered(img, self.font_role, 192, AB_FONT_ROLE_Y)
        return img

    # ------------------------------------------------------------- events --

    def on_motion(self, event):
        if self._drag is not None:
            dx, dy, sx, sy = self._drag
            if not self._drag_moved:
                if abs(event.x_root - sx) < 3 and abs(event.y_root - sy) < 3:
                    return
                self._drag_moved = True
            self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")
            return
        self._apply_hover((event.x, event.y))

    def on_press(self, event):
        self.root.focus_force()
        self.press = self.hit((event.x, event.y))
        if self.press is None:          # empty space / border: start a window drag
            self._drag = (event.x_root - self.root.winfo_x(),
                          event.y_root - self.root.winfo_y(),
                          event.x_root, event.y_root)
            self._drag_moved = False
        else:
            self.render()

    def on_release(self, event):
        pos = (event.x, event.y)
        if self._drag is not None:
            moved = self._drag_moved
            self._drag = None
            if moved:                   # the window was dragged, not clicked
                return
        pressed, self.press = self.press, None
        self.hover = self.hit(pos)
        self.render()
        if pressed and pressed == self.hover:
            self.activate(pressed)

    def on_leave(self, event):
        if self.hover or self.press:
            self.hover = self.press = None
            self.render()

    def on_key(self, event):
        if event.keysym == "Escape":
            self.close()

    def activate(self, name):
        if name == "close":
            self.close()

    def close(self):
        self.alive = False
        self.root.destroy()


def main():
    TileSlicerGUI().run()


if __name__ == "__main__":
    main()
