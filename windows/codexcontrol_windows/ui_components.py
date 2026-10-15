"""Small, antialiased Tk controls used by the Windows desktop UI.

RoundedPanel.inner is an ordinary Frame: pack/grid existing content into it.
ActionButton keeps text native (and crisp at the active Windows text scale),
while Pillow draws its rounded surface and consistent 24-unit line icons.
"""
from __future__ import annotations

import math
import sys
import tkinter as tk
import tkinter.font as tkfont
from functools import lru_cache
from typing import Any, Callable

from PIL import Image, ImageColor, ImageDraw, ImageTk

from .native_window import flush_native_paint

_SCALE = 3


def _blend(a: str, b: str, amount: float) -> str:
    left, right = ImageColor.getrgb(a), ImageColor.getrgb(b)
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(left, right))


def _tk_color(widget: tk.Misc, value: str) -> str:
    """Resolve Windows system colors before passing them to Pillow."""
    return "#" + "".join(f"{component // 257:02x}" for component in widget.winfo_rgb(value))


@lru_cache(maxsize=48)
def _surface(
    width: int, height: int, fill: str, border: str, background: str,
    radius: int, border_width: int = 1, satin: bool = False, focused: bool = False,
    focus_color: str = "#80ded0",
) -> Image.Image:
    """Compose large panels from a cached antialiased nine-slice skin.

    Only corners, edges and the upper sheen vary. Supersampling the entire
    panel every animation frame needlessly filters hundreds of thousands of
    solid pixels and can block Tk for 50ms. Nine-slicing preserves the same
    optical corners while making animated heights inexpensive.
    """
    width, height = max(1, width), max(1, height)
    cap_x = max(radius, border_width) + 4
    cap_y = max(cap_x, 28 if satin else cap_x)
    if width <= cap_x * 2 + 4 or height <= cap_y * 2 + 4:
        return _surface_raster(width, height, fill, border, background, radius,
                               border_width, satin, focused, focus_color)
    skin_width, skin_height = cap_x * 2 + 4, cap_y * 2 + 4
    skin = _surface_raster(skin_width, skin_height, fill, border, background,
                           radius, border_width, satin, focused, focus_color)
    image = Image.new("RGBA", (width, height), background)
    source_x, source_y = (0, cap_x, skin_width - cap_x, skin_width), (0, cap_y, skin_height - cap_y, skin_height)
    target_x, target_y = (0, cap_x, width - cap_x, width), (0, cap_y, height - cap_y, height)
    for row in range(3):
        for col in range(3):
            part = skin.crop((source_x[col], source_y[row], source_x[col+1], source_y[row+1]))
            target_size = target_x[col+1] - target_x[col], target_y[row+1] - target_y[row]
            if part.size != target_size:
                # The stretchable strips contain constant rows/columns only.
                # Nearest preserves their exact colors and crisp 1px borders.
                part = part.resize(target_size, Image.Resampling.NEAREST)
            image.paste(part, (target_x[col], target_y[row]))
    return image


@lru_cache(maxsize=96)
def _surface_raster(
    width: int, height: int, fill: str, border: str, background: str,
    radius: int, border_width: int = 1, satin: bool = False, focused: bool = False,
    focus_color: str = "#80ded0",
) -> Image.Image:
    """Supersample small controls and reusable panel edge/corner skins."""
    width, height = max(1, width), max(1, height)
    scale = _SCALE
    size = width * scale, height * scale
    image = Image.new("RGBA", size, background)
    shape = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shape)
    inset = scale if focused else 0
    box = (inset, inset, size[0] - 1 - inset, size[1] - 1 - inset)
    corner = min(radius * scale, (size[0] - 2 * inset) // 2, (size[1] - 2 * inset) // 2)
    if box[2] <= box[0] or box[3] <= box[1]:
        return image.resize((width, height), Image.Resampling.LANCZOS)
    draw.rounded_rectangle(box, radius=max(0, corner), fill=fill)
    if satin:
        # A soft upper rim gives a satin impression; the content area retains
        # a solid fill so embedded native labels blend without visible seams.
        mask = shape.getchannel("A")
        sheen = Image.new("RGBA", size, (0, 0, 0, 0))
        sheen_draw = ImageDraw.Draw(sheen)
        band = min(24 * scale, size[1])
        for y in range(band):
            opacity = round(11 * (1 - y / max(1, band - 1)) ** 2)
            sheen_draw.line((0, y, size[0], y), fill=(255, 255, 255, opacity))
        sheen.putalpha(Image.composite(sheen.getchannel("A"), Image.new("L", size), mask))
        shape = Image.alpha_composite(shape, sheen)
        draw = ImageDraw.Draw(shape)
    if border_width and border:
        draw.rounded_rectangle(box, radius=max(0, corner), outline=border, width=border_width * scale)
    if focused:
        outer = ImageDraw.Draw(image)
        outer.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=corner + scale,
                                outline=focus_color, width=scale)
    image = Image.alpha_composite(image, shape)
    return image.resize((width, height), Image.Resampling.LANCZOS)


@lru_cache(maxsize=192)
def draw_icon(name: str, size: int = 18, color: str = "#d6dee8", stroke_width: float = 1.7) -> Image.Image:
    """A consistent rounded-line icon set, returned as an RGBA Pillow image.

    Names: plus, refresh, switch, folder, trash, edit, check, close, chevron,
    search, logout, key, clock, minimize, activity, accounts, warning, more.
    All icons use the same optical 24-unit grid and round line caps.
    """
    size = max(1, int(size))
    scale = size * _SCALE / 24
    image = Image.new("RGBA", (size * _SCALE, size * _SCALE))
    draw = ImageDraw.Draw(image)
    pen = max(1, round(stroke_width * scale))

    def line(points: list[tuple[float, float]], caps: bool = True) -> None:
        xy = [(round(x * scale), round(y * scale)) for x, y in points]
        draw.line(xy, fill=color, width=pen, joint="curve")
        if caps:
            r = pen / 2
            for x, y in (xy[0], xy[-1]):
                draw.ellipse((x-r, y-r, x+r, y+r), fill=color)

    def oval(box: tuple[float, float, float, float], fill: bool = False) -> None:
        draw.ellipse(tuple(round(v * scale) for v in box), fill=color if fill else None,
                     outline=None if fill else color, width=pen)

    def rectangle(box: tuple[float, float, float, float], radius: float = 2) -> None:
        draw.rounded_rectangle(tuple(round(v * scale) for v in box), radius=radius * scale,
                               outline=color, width=pen)

    def arc(cx: float, cy: float, radius: float, start: float, end: float) -> None:
        steps = max(12, int(abs(end-start) / 6))
        line([(cx + math.cos(math.radians(start+(end-start)*n/steps))*radius,
               cy + math.sin(math.radians(start+(end-start)*n/steps))*radius)
              for n in range(steps+1)])

    if name in {"plus", "add"}:
        line([(12, 5), (12, 19)]); line([(5, 12), (19, 12)])
    elif name == "refresh":
        arc(12, 12, 7.5, -62, 210); line([(4.5, 7), (4.5, 12), (9.5, 12)])
    elif name == "switch":
        line([(4, 8), (20, 8)]); line([(16, 4), (20, 8), (16, 12)])
        line([(20, 16), (4, 16)]); line([(8, 12), (4, 16), (8, 20)])
    elif name == "folder":
        line([(3.5, 8), (3.5, 6), (9, 6), (11, 8), (20.5, 8), (20.5, 19), (3.5, 19), (3.5, 8)])
        line([(4, 10.5), (20, 10.5)])
    elif name == "trash":
        line([(4.5, 7), (19.5, 7)]); line([(9, 7), (9, 4.5), (15, 4.5), (15, 7)])
        line([(6.5, 7), (7.5, 20), (16.5, 20), (17.5, 7)])
        line([(10, 10.5), (10.5, 16.5)]); line([(14, 10.5), (13.5, 16.5)])
    elif name in {"edit", "save"}:
        line([(5, 15.5), (5, 20), (9.5, 19), (19.5, 9), (15.5, 5), (5, 15.5)])
        line([(13.5, 7), (17.5, 11)])
    elif name in {"check", "spark"}:
        line([(5, 12), (10, 17), (19, 7.5)])
    elif name in {"close", "x"}:
        line([(6, 6), (18, 18)]); line([(18, 6), (6, 18)])
    elif name in {"chevron", "chevron_down"}:
        line([(6.5, 9), (12, 14.5), (17.5, 9)])
    elif name == "chevron_right":
        line([(9, 6.5), (14.5, 12), (9, 17.5)])
    elif name == "chevron_up":
        line([(6.5, 14.5), (12, 9), (17.5, 14.5)])
    elif name == "search":
        oval((4, 4, 16, 16)); line([(14.5, 14.5), (20, 20)])
    elif name == "logout":
        line([(10, 4.5), (5, 4.5), (5, 19.5), (10, 19.5)])
        line([(10, 12), (20, 12)]); line([(16, 8), (20, 12), (16, 16)])
    elif name == "key":
        oval((3.5, 3.5, 13.5, 13.5)); line([(12, 12), (20.5, 20.5)])
        line([(16, 16), (19, 13)]); line([(18.5, 18.5), (21, 16)])
    elif name == "clock":
        oval((3.5, 3.5, 20.5, 20.5)); line([(12, 7), (12, 12.5), (16, 15)])
    elif name == "minimize":
        line([(5, 12), (19, 12)])
    elif name in {"activity", "live"}:
        line([(3, 12), (7, 12), (10, 5), (14, 19), (17, 12), (21, 12)])
    elif name in {"accounts", "user"}:
        oval((8, 3, 16, 11)); arc(12, 20, 7, 180, 360)
        line([(5, 20), (19, 20)])
    elif name in {"warning", "critical"}:
        line([(12, 3.5), (21, 20), (3, 20), (12, 3.5)])
        line([(12, 9), (12, 13.5)]); oval((11.25, 16.25, 12.75, 17.75), True)
    elif name == "more":
        for x in (5, 12, 19):
            oval((x-1, 11, x+1, 13), True)
    else:
        raise ValueError(f"Unknown icon: {name!r}")
    return image.resize((size, size), Image.Resampling.LANCZOS)


def icon_photo(name: str, size: int = 18, color: str = "#d6dee8", master: tk.Misc | None = None) -> ImageTk.PhotoImage:
    """Keep the returned PhotoImage alive on the widget displaying it."""
    return ImageTk.PhotoImage(draw_icon(name, size, color), master=master)


def _workarea_for_widget(widget: tk.Widget, anchor_rect: tuple[int, int, int, int] | None = None) -> tuple[int, int, int, int]:
    """Use the control's center so a straddling control chooses its own monitor."""
    fallback = (0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight())
    if sys.platform != "win32":
        return fallback
    try:
        import ctypes
        from ctypes import wintypes

        class MonitorInfo(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                        ("work", wintypes.RECT), ("flags", wintypes.DWORD)]

        point = (wintypes.POINT((anchor_rect[0] + anchor_rect[2]) // 2, (anchor_rect[1] + anchor_rect[3]) // 2)
                 if anchor_rect is not None else
                 wintypes.POINT(widget.winfo_rootx() + widget.winfo_width() // 2,
                               widget.winfo_rooty() + widget.winfo_height() // 2))
        monitor_from_point = ctypes.windll.user32.MonitorFromPoint
        monitor_from_point.argtypes = (wintypes.POINT, wintypes.DWORD)
        monitor_from_point.restype = wintypes.HANDLE
        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        monitor = monitor_from_point(point, 2)
        get_monitor_info = ctypes.windll.user32.GetMonitorInfoW
        get_monitor_info.argtypes = (wintypes.HANDLE, ctypes.POINTER(MonitorInfo))
        if get_monitor_info(monitor, ctypes.byref(info)):
            return info.work.left, info.work.top, info.work.right, info.work.bottom
    except (AttributeError, OSError):
        pass
    return fallback


class ToolTip:
    """A delayed, non-focus-taking label above its target; keyboard friendly."""
    def __init__(self, widget: tk.Widget, text: str, *, delay: int = 420,
                 fill: str = "#202b38", foreground: str = "#eef4f8", border: str = "#354759",
                 font: Any = ("Segoe UI", 9),
                 anchor_rect: Callable[[], tuple[int, int, int, int] | None] | None = None) -> None:
        self.widget, self.text, self.delay = widget, text, delay
        self.fill, self.foreground, self.border, self.font = fill, foreground, border, font
        self.anchor_rect = anchor_rect
        self.window: tk.Toplevel | None = None
        self._job: str | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._bindings: list[tuple[str, str]] = []
        # Composite controls can cancel pending/showing tooltips when their
        # content is clipped, even though the child remains mapped for preload.
        if not hasattr(widget, "_control_tooltips"):
            widget._control_tooltips = []
        widget._control_tooltips.append(self)
        for sequence, callback in (("<Enter>", self.schedule), ("<Leave>", self.hide),
                                   ("<FocusIn>", self.schedule), ("<FocusOut>", self.hide),
                                   ("<ButtonPress>", self.hide), ("<Unmap>", self.hide),
                                   ("<Escape>", self.hide), ("<Destroy>", self._destroy)):
            ident = widget.bind(sequence, callback, add="+")
            if ident:
                self._bindings.append((sequence, ident))

    def set_text(self, text: str) -> None:
        self.text = text
        self.hide()

    def _details_are_visible(self) -> bool:
        """Clipped, preloaded details stay mapped but must not show tooltips."""
        ancestor = self.widget
        while ancestor is not None:
            if getattr(ancestor, "_details_visible", None) is False:
                return False
            ancestor = getattr(ancestor, "master", None)
        return True

    def schedule(self, _: Any = None) -> None:
        self.hide()
        if self.text and self._details_are_visible():
            self._job = self.widget.after(self.delay, self.show)

    def show(self) -> None:
        # Also cancel a queued timer if show() is called directly while a
        # parent is collapsing; a late callback must not reopen the tooltip.
        self.hide()
        window = None
        try:
            if not self.text or not self._details_are_visible() or not self.widget.winfo_exists() or not self.widget.winfo_viewable():
                return
            window = self.window = tk.Toplevel(self.widget)
            window.withdraw()
            window.overrideredirect(True)
            window.attributes("-topmost", True)
            window.configure(bg="#010203")
            if sys.platform == "win32":
                window.wm_attributes("-transparentcolor", "#010203")
            canvas = tk.Canvas(window, highlightthickness=0, bd=0, bg="#010203")
            canvas.pack()
            item = canvas.create_text(11, 8, text=self.text, anchor="nw", width=300,
                                      fill=self.foreground, font=self.font, justify="left")
            bounds = canvas.bbox(item)
            width = max(24, bounds[2] + 11 if bounds else 24)
            height = max(24, bounds[3] + 8 if bounds else 24)
            canvas.configure(width=width, height=height)
            self._photo = ImageTk.PhotoImage(_surface(width, height, self.fill, self.border, "#010203", 8), master=window)
            background_item = canvas.create_image(0, 0, image=self._photo, anchor="nw")
            canvas.tag_lower(background_item)
            window.update_idletasks()
            # Idle staging can destroy the target or cancel/replace this tooltip.
            # Revalidate both objects before querying the target's screen geometry.
            if self.window is not window:
                return
            if (not self.widget.winfo_exists() or not window.winfo_exists()
                    or not self.widget.winfo_viewable() or not self._details_are_visible()):
                self.hide()
                return
            anchor = self.anchor_rect() if self.anchor_rect else (
                self.widget.winfo_rootx(), self.widget.winfo_rooty(),
                self.widget.winfo_rootx() + self.widget.winfo_width(),
                self.widget.winfo_rooty() + self.widget.winfo_height())
            if anchor is None:
                self.hide()
                return
            left, top, right, bottom = _workarea_for_widget(self.widget, anchor)
            x = (anchor[0] + anchor[2] - width) // 2
            y = anchor[1] - height - 7
            if y < top + 4:
                y = anchor[3] + 7
            x = max(left + 4, min(x, right - width - 4))
            y = max(top + 4, min(y, bottom - height - 4))
            window.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
            window.deiconify()
            if sys.platform == "win32" and (x < 0 or y < 0):
                try:
                    import ctypes
                    from ctypes import wintypes
                    get_parent = ctypes.windll.user32.GetParent
                    get_parent.argtypes = (wintypes.HWND,)
                    get_parent.restype = wintypes.HWND
                    hwnd = get_parent(window.winfo_id())
                    # Absolute screen placement for monitors with negative origins.
                    set_position = ctypes.windll.user32.SetWindowPos
                    set_position.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                             ctypes.c_int, ctypes.c_int, wintypes.UINT)
                    set_position(hwnd, None, x, y, width, height, 0x14)
                except (AttributeError, OSError):
                    pass
        except tk.TclError:
            # Destruction can also happen inside Tk geometry/monitor calls.
            # A reentrant show may already own a different tooltip window.
            if self.window is window:
                self.hide()

    def hide(self, _: Any = None) -> None:
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None
            self._photo = None

    def _destroy(self, event: Any = None) -> None:
        if event is None or event.widget is self.widget:
            self.hide()

    def destroy(self) -> None:
        self.hide()
        for sequence, ident in self._bindings:
            try:
                self.widget.unbind(sequence, ident)
            except tk.TclError:
                pass
        self._bindings.clear()
        registered = getattr(self.widget, "_control_tooltips", [])
        if self in registered:
            registered.remove(self)


class RoundedPanel(tk.Frame):
    """A responsive rounded surface with a normal `.inner` Frame for content.

    Its natural height follows the inner frame. Pack with fill='x' for cards,
    or fill='both', expand=True for a container. For nested panels pass the
    parent panel's fill as background. `padding` accepts an int or (x, y).
    """
    def __init__(self, parent: tk.Widget, *, fill: str = "#151e29", border: str = "#2b3949",
                 background: str | None = None, radius: int = 14,
                 padding: int | tuple[int, int] = 14, border_width: int = 1,
                 satin: bool = False, width: int | None = None, **kwargs: Any) -> None:
        background = _tk_color(parent, background or str(parent.cget("bg")))
        super().__init__(parent, bg=background, bd=0, highlightthickness=0, **kwargs)
        self.fill, self.border, self.background = fill, border, background
        self.radius, self.border_width, self.satin = radius, border_width, satin
        self.pad_x, self.pad_y = (padding, padding) if isinstance(padding, int) else padding
        self._natural_width = width is None
        self._width_request = width or 1
        self.canvas = tk.Canvas(self, bg=background, bd=0, highlightthickness=0,
                                width=width or 1, height=2*self.pad_y+1)
        self.canvas.pack(fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=fill, bd=0, highlightthickness=0)
        self._image_item = self.canvas.create_image(0, 0, anchor="nw")
        self._window_item = self.canvas.create_window(self.pad_x, self.pad_y, window=self.inner, anchor="nw")
        self._photo: ImageTk.PhotoImage | None = None
        self._job: str | None = None
        self._last_geometry: tuple[Any, ...] | None = None
        self._height_request = 0
        self._height_override: int | None = None
        self._destroyed = False
        self._paint_flush_running = False
        self.canvas.bind("<Configure>", self._schedule)
        self.inner.bind("<Configure>", self._schedule)
        self.bind("<Destroy>", self._destroy)
        # Defer the first layout by two idle turns. This lets pack/grid settle
        # their requested sizes even if the toplevel is initially withdrawn.
        self._job = self.after_idle(self._prime_layout)

    def _prime_layout(self) -> None:
        self._job = None
        self._schedule()

    def set_height_override(self, height: int | None) -> None:
        """Clip to a total height for animation; None restores natural height.

        The override includes the panel padding. The inner frame keeps its
        natural size, so hidden content is not squeezed or rebuilt during an
        animation. Tk widgets have a minimum physical size of one pixel.
        Repeated changes coalesce into a single idle layout pass.
        """
        if self._destroyed:
            return
        value = None if height is None else max(1, int(height))
        if value == self._height_override:
            return
        self._height_override = value
        # Prepare the backing image before geometry exposes any new pixels.
        # Waiting for _layout's idle callback after resizing lets Windows show
        # the canvas' darker background for one frame during expansion.
        width = self.canvas.winfo_width()
        if width <= 1:
            width = max(self.winfo_width(), int(self.canvas.cget("width")))
        paint_height = value if value is not None else self.inner.winfo_reqheight() + self.pad_y*2
        self._paint_surface(max(1, width), paint_height)
        # Submit the outer request in the same event turn as the animation.
        # Propagating a canvas request through the panel's packer otherwise
        # leaves the visible card several frames behind the requested clip.
        self.pack_propagate(value is None)
        if value is not None:
            self.configure(height=value, width=max(1, self.winfo_width()))
            self.canvas.configure(height=value)
        # A parent grid row may allocate extra height (for a taller neighbor).
        # Do not let pack stretch the clipping canvas back to that allocation.
        self.canvas.pack_configure(fill="both" if value is None else "x", expand=value is None)
        self._schedule()

    def set_style(self, *, fill: str | None = None, border: str | None = None,
                  background: str | None = None, satin: bool | None = None) -> None:
        if fill is not None:
            self.fill = fill
            self.inner.configure(bg=fill)
        if border is not None:
            self.border = border
        if background is not None:
            self.background = background
            self.configure(bg=background)
            self.canvas.configure(bg=background)
        if satin is not None:
            self.satin = satin
        self._last_geometry = None
        self._schedule()

    def _schedule(self, _: Any = None) -> None:
        if not self._destroyed and self._job is None:
            try:
                self._job = self.after_idle(self._layout)
            except tk.TclError:
                # A parent may already be tearing down its native children.
                self._job = None

    def _layout(self) -> None:
        self._job = None
        if self._destroyed or not self.winfo_exists():
            return
        if self._natural_width:
            requested_width = self.inner.winfo_reqwidth() + self.pad_x*2
            if requested_width != self._width_request:
                self._width_request = requested_width
                self.canvas.configure(width=requested_width)
        width = self.canvas.winfo_width()
        if width <= 1:
            width = int(self.canvas.cget("width"))
        self.canvas.itemconfigure(self._window_item, width=max(1, width - self.pad_x*2))
        natural_height = self.inner.winfo_reqheight() + self.pad_y*2
        requested_height = self._height_override if self._height_override is not None else natural_height
        if requested_height != self._height_request:
            self._height_request = requested_height
            self.canvas.configure(height=requested_height)
        # During animation, paint exactly the clipped surface; using the
        # inner's natural height here defeats collapse and leaves stale rims.
        height = requested_height if self._height_override is not None else max(requested_height, self.canvas.winfo_height())
        self._paint_surface(width, height)

    def _paint_surface(self, width: int, height: int) -> None:
        geometry = (width, height, self.fill, self.border, self.background, self.radius, self.border_width, self.satin)
        if geometry == self._last_geometry:
            return
        photo = ImageTk.PhotoImage(_surface(*geometry), master=self)
        # Keep the old PhotoImage alive until the new one is attached. Releasing
        # it first temporarily clears the canvas item in Tk's image table.
        self.canvas.itemconfigure(self._image_item, image=photo)
        self._photo = photo
        self._last_geometry = geometry

    def flush_visible_paint(self) -> int:
        """Repaint newly exposed native children after a clip-height change.

        Call once geometry has reached the requested animation height, before
        scheduling the next frame. A prebuilt Tk child can remain unpainted
        while outside its parent's clip; a background PhotoImage alone cannot
        refresh its native window. Explicit Expose rectangles schedule each
        visible child's own drawing, then one idle flush completes the paint.
        This does not dispatch timers/input via update(), or change Win32 styles.
        Returns the number of controls invalidated; reentrant/destroyed calls
        safely return zero.
        """
        if self._destroyed or self._paint_flush_running:
            return 0
        self._paint_flush_running = True
        count = 0

        def bounds(widget: tk.Widget) -> tuple[int, int, int, int]:
            x, y = widget.winfo_rootx(), widget.winfo_rooty()
            return x, y, x + widget.winfo_width(), y + widget.winfo_height()

        def intersect(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
            return max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])

        def repaint(widget: tk.Widget, clip: tuple[int, int, int, int]) -> None:
            nonlocal count
            if not widget.winfo_exists() or not widget.winfo_ismapped():
                return
            rectangle = bounds(widget)
            visible = intersect(clip, rectangle)
            if visible[2] <= visible[0] or visible[3] <= visible[1]:
                return
            widget.event_generate(
                "<Expose>", x=visible[0] - rectangle[0], y=visible[1] - rectangle[1],
                width=visible[2] - visible[0], height=visible[3] - visible[1],
                count=0, when="now",
            )
            count += 1
            for child in widget.winfo_children():
                if not isinstance(child, tk.Toplevel):
                    repaint(child, visible)

        try:
            if not self.winfo_exists() or not self.winfo_ismapped():
                return 0
            clip = bounds(self.canvas)
            ancestor: tk.Widget | None = self
            while ancestor is not None:
                if not ancestor.winfo_ismapped():
                    return 0
                clip = intersect(clip, bounds(ancestor))
                ancestor = getattr(ancestor, "master", None)
            if clip[2] <= clip[0] or clip[3] <= clip[1]:
                return 0
            # Drain queued native erasure before our explicit Tk drawing so
            # delayed WM_PAINT cannot clear freshly exposed child contents.
            flush_native_paint(self.canvas)
            if self._destroyed:
                return 0
            repaint(self.canvas, clip)
            if count and not self._destroyed:
                # Idle tasks include Tk drawing/geometry, but not queued user
                # input or after(ms) business timers. Guard against nested
                # paint requests from an application's own idle callback.
                self.update_idletasks()
            return count
        except tk.TclError:
            # An idle callback can retire this retained card during a refresh.
            return count
        finally:
            self._paint_flush_running = False

    def _destroy(self, event: Any) -> None:
        if event.widget is self:
            self._destroyed = True
            if self._job is not None:
                try:
                    self.after_cancel(self._job)
                except tk.TclError:
                    pass
                self._job = None


class ActionButton(tk.Canvas):
    """A rounded button with optional icon, real hover/press/focus states."""
    def __init__(self, parent: tk.Widget, text: str = "", command: Callable[[], Any] | None = None,
                 *, icon: str | None = None, fill: str = "#202c39", hover_fill: str = "#2b3b4c",
                 foreground: str = "#dde7f1", border: str = "#354659", background: str | None = None,
                 disabled_fill: str = "#17212d", disabled_foreground: str = "#617184",
                 focus_color: str = "#80ded0", font: Any = ("Segoe UI", 9), height: int = 34,
                 width: int | None = None, radius: int = 9, padding: int = 12,
                 icon_size: int = 17, gap: int = 7, tooltip: str | None = None,
                 satin: bool = False, **kwargs: Any) -> None:
        background = _tk_color(parent, background or str(parent.cget("bg")))
        super().__init__(parent, bg=background, highlightthickness=0, bd=0, relief="flat",
                         takefocus=1, cursor="hand2", **kwargs)
        self.text, self.icon, self.command = text, icon, command
        self.fill, self.hover_fill, self.foreground, self.border = fill, hover_fill, foreground, border
        self.disabled_fill, self.disabled_foreground = disabled_fill, disabled_foreground
        self.background, self.focus_color = background, focus_color
        self.radius, self.padding, self.icon_size, self.gap, self.satin = radius, padding, icon_size, gap, satin
        self._height, self._fixed_width = height, width
        self._font = tkfont.Font(master=self, font=font)
        self.enabled, self._hover, self._pressed, self._focused = True, False, False, False
        self._key_held = False
        self._photo: ImageTk.PhotoImage | None = None
        self._icon_photo: ImageTk.PhotoImage | None = None
        self._redraw_job: str | None = None
        self._image_item = self.create_image(0, 0, anchor="nw")
        self._icon_item = self.create_image(0, 0)
        self._text_item = self.create_text(0, 0, text=text, font=self._font)
        self._last_state: tuple[Any, ...] | None = None
        self.tooltip = ToolTip(self, tooltip) if tooltip else None
        self.bind("<Configure>", self._schedule)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<FocusIn>", self._focus_in, add="+")
        self.bind("<FocusOut>", self._focus_out, add="+")
        for key in ("Return", "space"):
            self.bind(f"<KeyPress-{key}>", self._key_press)
            self.bind(f"<KeyRelease-{key}>", self._key_release)
        self.bind("<Destroy>", self._destroy, add="+")
        self._measure()
        self._schedule()

    def _measure(self) -> None:
        content = self._font.measure(self.text) + (self.icon_size if self.icon else 0)
        if self.icon and self.text:
            content += self.gap
        width = self._fixed_width or max(self._height, content + self.padding*2)
        # Icon-only controls have no text to accommodate. Keep their target
        # square at every text scale, including the small 24/26px controls.
        height = max(self._height, self._font.metrics("linespace") + 10) if self.text else self._height
        self.configure(width=width, height=height)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not enabled:
            self._pressed = self._key_held = False
        self.configure(cursor="hand2" if enabled else "arrow", takefocus=int(enabled))
        self._schedule()

    def set_text(self, text: str) -> None:
        if self.text != text:
            self.text = text
            self._measure()
            self._schedule()

    def set_icon(self, icon: str | None) -> None:
        if self.icon != icon:
            self.icon = icon
            self._measure()
            self._schedule()

    def set_tooltip(self, text: str) -> None:
        if self.tooltip is None:
            if text:
                self.tooltip = ToolTip(self, text)
        else:
            self.tooltip.set_text(text)

    def set_theme(self, theme: Any) -> None:
        """Accept the app's existing RoundedButtonTheme for easy migration."""
        self.set_style(fill=theme.bg, hover_fill=theme.hover, foreground=theme.fg,
                       border=theme.border, disabled_fill=theme.disabled_bg,
                       disabled_foreground=theme.disabled_fg)

    def set_style(self, **values: Any) -> None:
        allowed = {"fill", "hover_fill", "foreground", "border", "disabled_fill", "disabled_foreground", "background", "focus_color", "satin"}
        for name, value in values.items():
            if name not in allowed:
                raise TypeError(f"Unknown button style: {name}")
            setattr(self, name, value)
        if "background" in values:
            self.configure(bg=self.background)
        self._schedule()

    def invoke(self) -> Any:
        if self.enabled and self.command is not None:
            if self.tooltip:
                self.tooltip.hide()
            return self.command()
        return None

    def _enter(self, _: Any) -> None:
        self._hover = True
        if self.tooltip:
            self.tooltip.schedule()
        self._schedule()

    def _leave(self, _: Any) -> None:
        self._hover = False
        self._pressed = False
        if self.tooltip:
            self.tooltip.hide()
        self._schedule()

    def _focus_in(self, _: Any) -> None:
        self._focused = True
        self._schedule()

    def _focus_out(self, _: Any) -> None:
        self._focused = self._pressed = self._key_held = False
        self._schedule()

    def _press(self, _: Any) -> str:
        if self.enabled:
            self.focus_set()
            if self.tooltip:
                self.tooltip.hide()
            self._pressed = True
            self._schedule()
        return "break"

    def _release(self, event: Any) -> str:
        invoke = self._pressed and 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        self._pressed = False
        self._schedule()
        if invoke:
            self.invoke()
        return "break"

    def _key_press(self, _: Any) -> str:
        if self.enabled and not self._key_held:
            self._key_held = self._pressed = True
            self._schedule()
        return "break"

    def _key_release(self, _: Any) -> str:
        invoke = self._key_held
        self._key_held = self._pressed = False
        self._schedule()
        if invoke:
            self.invoke()
        return "break"

    def _schedule(self, _: Any = None) -> None:
        if self._redraw_job is None:
            self._redraw_job = self.after_idle(self._redraw)

    def _redraw(self) -> None:
        self._redraw_job = None
        width, height = self.winfo_width(), self.winfo_height()
        if width <= 1:
            width, height = int(self.cget("width")), int(self.cget("height"))
        fill = self.disabled_fill if not self.enabled else self.hover_fill if self._hover else self.fill
        if self._pressed and self.enabled:
            fill = _blend(fill, "#000000", .15)
        foreground = self.foreground if self.enabled else self.disabled_foreground
        border = self.border if self.enabled else _blend(self.border, self.background, .45)
        state = (width, height, fill, border, self.background, foreground, self.text, self.icon,
                 self._focused, self.enabled, self.satin, self.radius, self.focus_color)
        if state == self._last_state:
            return
        self._last_state = state
        self._photo = ImageTk.PhotoImage(_surface(width, height, fill, border, self.background,
                            self.radius, 1, self.satin, self._focused and self.enabled, self.focus_color), master=self)
        self.itemconfigure(self._image_item, image=self._photo)
        text_width = self._font.measure(self.text)
        total = text_width + (self.icon_size if self.icon else 0) + (self.gap if self.icon and self.text else 0)
        start = (width-total)/2
        if self.icon:
            self._icon_photo = icon_photo(self.icon, self.icon_size, foreground, master=self)
            self.itemconfigure(self._icon_item, image=self._icon_photo, state="normal")
            self.coords(self._icon_item, start+self.icon_size/2, height/2)
            start += self.icon_size + (self.gap if self.text else 0)
        else:
            self.itemconfigure(self._icon_item, state="hidden")
        self.itemconfigure(self._text_item, text=self.text, fill=foreground, state="normal" if self.text else "hidden")
        self.coords(self._text_item, start+text_width/2, height/2)

    def _destroy(self, event: Any) -> None:
        if event.widget is self:
            if self._redraw_job is not None:
                try:
                    self.after_cancel(self._redraw_job)
                except tk.TclError:
                    pass
                self._redraw_job = None
            if self.tooltip:
                self.tooltip.destroy()


class IconButton(ActionButton):
    """Square icon button. Its tooltip is shown on hover and keyboard focus."""
    def __init__(self, parent: tk.Widget, icon: str, command: Callable[[], Any] | None = None,
                 *, size: int = 34, tooltip: str | None = None, **kwargs: Any) -> None:
        super().__init__(parent, text="", icon=icon, command=command, height=size, width=size,
                         tooltip=tooltip or icon.replace("_", " ").capitalize(), **kwargs)
