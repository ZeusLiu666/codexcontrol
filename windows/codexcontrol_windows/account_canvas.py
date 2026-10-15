"""Account cards drawn in one Canvas window, committed as a single scene.

No card, label, quota bar, toolbar button or token cell owns a native child
window. A temporary nickname Entry is the only create_window exception.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
import tkinter as tk
import tkinter.font as tkfont
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageTk

from .models import AccountRuntimeState
from .presentation_logic import AccountIdentityPresentation
from .token_usage import compact
from .ui_components import ToolTip, _surface, draw_icon


@dataclass
class HitRegion:
    key: tuple
    rect: tuple[int, int, int, int]
    command: Callable[[], Any] | None = None
    tooltip: str = ''
    enabled: bool = True
    focusable: bool = True
    background_item: int | None = None
    images: dict[str, Any] = field(default_factory=dict)


class AccountCanvasScene:
    """One native canvas; stable virtual controls and atomic scene replacement."""
    def __init__(self, app, canvas: tk.Canvas):
        self.app, self.canvas = app, canvas
        self.regions: list[HitRegion] = []
        self.card_bounds: dict[Any, tuple[int, int, int, int]] = {}
        self.content_height = 1
        self.focus_key: tuple | None = None
        self._hover_key = self._pressed_key = self._tip_key = None
        self._keyboard_pressed = False
        self._pointer_focus_pending = False
        self._has_focus = False
        self._disposed = False
        self._accounts = []
        self._width = 1
        self._selected = None
        self._generation = 0
        self._tag = None
        self._photos = []
        self._photo_cache = OrderedDict()
        self._fonts = {name: tkfont.Font(master=canvas, font=value) for name, value in app.fonts.items()}
        self._entry: tk.Entry | None = None
        self._editor_item = None
        self._editor_id = None
        self._editor_rect = None
        self._draft_var = None
        self._focus_item = None
        self._bindings = []
        self.tooltip = ToolTip(canvas, '', delay=120, font=app.fonts['body_small'],
                               anchor_rect=self._tooltip_rect)
        canvas.configure(takefocus=1)
        for event, handler in (
            ('<Motion>', self._motion), ('<Leave>', self._leave),
            ('<ButtonPress-1>', self._press), ('<ButtonRelease-1>', self._release),
            ('<FocusIn>', self._focus_in), ('<FocusOut>', self._focus_out),
            ('<Tab>', self._tab), ('<Shift-Tab>', self._shift_tab),
            ('<ISO_Left_Tab>', self._shift_tab),
            ('<KeyPress-Return>', self._key_press), ('<KeyRelease-Return>', self._key_release),
            ('<KeyPress-space>', self._key_press), ('<KeyRelease-space>', self._key_release),
            ('<Escape>', self._escape), ('<MouseWheel>', self._scroll),
            ('<Configure>', self._scroll), ('<Destroy>', self._destroy_event),
        ):
            ident = canvas.bind(event, handler, add='+')
            self._bindings.append((event, ident))

    def _font(self, name):
        return self._fonts[name]

    def _height(self, name):
        return self._font(name).metrics('linespace')

    def _ellipsize(self, text, font, width):
        text = str(text or '')
        measure = self._font(font).measure
        if measure(text) <= width:
            return text
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if measure(text[:middle] + '…') <= max(1, width):
                low = middle
            else:
                high = middle - 1
        return text[:low] + '…'

    def _photo(self, key, make):
        photo = self._photo_cache.get(key)
        if photo is None:
            photo = ImageTk.PhotoImage(make(), master=self.canvas)
            self._photo_cache[key] = photo
        self._photo_cache.move_to_end(key)
        while len(self._photo_cache) > 256:
            self._photo_cache.popitem(last=False)
        self._new_photos.append(photo)
        return photo

    def _image(self, x, y, photo):
        return self.canvas.create_image(round(x), round(y), image=photo, anchor='nw', tags=self._new_tag, state='hidden')

    def _surface(self, x, y, width, height, fill, border, background, radius=12, satin=False, focused=False):
        args = (max(1, round(width)), max(1, round(height)), fill, border, background, radius, 1, satin, focused, self.app.palette['accent'])
        photo = self._photo(('surface', *args), lambda: _surface(*args))
        return self._image(x, y, photo), photo

    def _text(self, x, y, text, font='body_small', color=None, *, anchor='nw', width=None):
        kwargs = dict(text=str(text), font=self._font(font), fill=color or self.app.palette['text'],
                      anchor=anchor, tags=self._new_tag, state='hidden', justify='left')
        if width is not None:
            kwargs['width'] = max(1, round(width))
        return self.canvas.create_text(round(x), round(y), **kwargs)

    def _line(self, x1, y, x2):
        self.canvas.create_line(round(x1), round(y), round(x2), round(y), fill=self.app.palette['hairline'],
                                tags=self._new_tag, state='hidden')

    def _icon(self, x, y, name, color, size=17):
        photo = self._photo(('icon', name, size, color), lambda: draw_icon(name, size, color))
        self._image(x, y, photo)

    def _region(self, key, rect, command=None, tooltip='', enabled=True, focusable=True):
        region = HitRegion(key, tuple(round(v) for v in rect), command, tooltip, bool(enabled), focusable)
        self._new_regions.append(region)
        return region

    def _button(self, key, x, y, icon, command, tooltip, *, size=32, enabled=True, accent=False, danger=False):
        p = self.app.palette
        fill = p['accent_soft'] if accent else p['panel']
        border = p['accent_line'] if accent else fill
        foreground = (p['danger'] if danger else p['accent'] if accent else p['muted']) if enabled else p['neutral']
        item, normal = self._surface(x, y, size, size, fill, border, p['panel'], radius=9)
        images = {'normal': normal}
        if enabled:
            for name, bg, focus in (('hover', p['hover'], False), ('focus', fill, True), ('pressed', p['accent_soft'], True)):
                args = (size, size, bg, border, p['panel'], 9, 1, False, focus, p['accent'])
                images[name] = self._photo(('surface', *args), lambda a=args: _surface(*a))
        self._icon(x + (size-17)/2, y + (size-17)/2, icon, foreground)
        region = self._region(key, (x, y, x+size, y+size), command, tooltip, enabled)
        region.background_item, region.images = item, images
        return region

    def _quota(self, x, y, width, window):
        p = self.app.palette
        height = self._height('headline') + self._height('caption') + 44
        self._surface(x, y, width, height, p['panel_alt'], p['panel_alt'], p['panel'], radius=12)
        self._text(x+11, y+11, window.display_name, 'caption', p['muted'])
        self._text(x+width-11, y+9, f'{window.remaining_percent:.0f}%', 'headline', anchor='ne')
        bar_y = y + 11 + self._height('headline') + 10
        bar_w = max(1, round(width-22))
        value = max(0, min(100, window.remaining_percent))
        color = self.app._quota_color(value)
        def bar_image():
            image = Image.new('RGB', (bar_w*3, 15), p['panel_alt'])
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((0, 0, bar_w*3-1, 14), radius=7, fill=p['track'])
            filled = round(bar_w*3*value/100)
            if filled:
                draw.rounded_rectangle((0, 0, max(1, filled-1), 14), radius=min(7, filled/2), fill=color)
            return image.resize((bar_w, 5), Image.Resampling.LANCZOS)
        self._image(x+11, bar_y, self._photo(('quota', bar_w, value, color, p['panel_alt'], p['track']), bar_image))
        reset = window.compact_reset_at_display or 'Reset time unavailable'
        self._text(x+11, bar_y+13, self._ellipsize(reset, 'caption', width-22), 'caption', p['muted'])
        return height

    def _card(self, account, x, y, width, identity, duplicate):
        p = self.app.palette
        state = self.app.runtime_states.get(account.id, AccountRuntimeState())
        selected = self._selected == account.id
        active = self.app._is_active_account(account)
        left, right = x+16, x+width-16
        inner_w = width-32
        top = y+16
        header_h = max(34, self._height('headline')+4+self._height('caption'))
        # Draw the panel last and lower it beneath all of this card's items.
        first_item = self.canvas.create_rectangle(0, 0, 0, 0, outline='', tags=self._new_tag, state='hidden')
        self._region((account.id, 'header'), (left, top, right, top+header_h),
                     lambda a=account: self.app._toggle_selection(a.id), focusable=False)
        action_x = right-26
        self._button((account.id, 'details'), action_x, top, 'chevron_up' if selected else 'chevron',
                     lambda a=account: self.app._toggle_selection(a.id),
                     'Collapse details' if selected else 'Usage & account details', size=26)
        action_x -= 4
        if active:
            chip_w = self._font('caption').measure('Active')+16
            action_x -= chip_w
            self._surface(action_x, top+1, chip_w, 26, p['accent_soft'], p['accent_soft'], p['panel'], radius=10)
            self._text(action_x+chip_w/2, top+14, 'Active', 'caption', p['accent'], anchor='center')
        elif self.app._can_switch_account(account):
            action_x -= 32
            self._button((account.id, 'switch'), action_x, top-2, 'switch', lambda a=account: self.app.switch_account(a),
                         f'Switch to {account.display_name}', accent=True)
        title_w = max(40, action_x-left-9)
        display = identity.display_name(account)
        if display == account.email_hint and '@' in display:
            display = display.split('@', 1)[0]
        self._text(left, top, self._ellipsize(display, 'headline', title_w), 'headline')
        email = account.email_hint or account.source.display_name
        email_y = top + self._height('headline') + 4
        self._text(left, email_y, self._ellipsize(email, 'caption', title_w), 'caption', p['muted'])
        self._region((account.id, 'identity'), (left, top, left+title_w, top+header_h),
                     lambda a=account: self.app._toggle_selection(a.id), f'{display}\n{email}', focusable=False)
        cy = top+header_h+12
        plan = state.snapshot.plan_display_name if state.snapshot else 'Codex account'
        self._text(left, cy, plan, 'caption', p['muted'])
        status = ('Duplicate login' if duplicate else 'Refreshing…' if state.is_loading else
                  'Cached · refresh failed' if state.error_message and state.snapshot else
                  'Needs attention' if state.error_message else 'Remaining quota')
        status_color = p['warning'] if duplicate else self.app._status_color(state) if state.error_message else p['muted']
        status_text = self._ellipsize(status, 'caption', max(70, inner_w-self._font('caption').measure(plan)-12))
        self._text(right, cy, status_text, 'caption', status_color, anchor='ne')
        self._region((account.id, 'status'), (right-self._font('caption').measure(status_text), cy, right, cy+self._height('caption')),
                     tooltip=state.error_message or status, focusable=False)
        cy += self._height('caption')+10
        if state.snapshot and state.snapshot.has_quota_windows:
            windows = [w for w in (state.snapshot.primary_window, state.snapshot.secondary_window) if w]
            tile_w = (inner_w-10*(len(windows)-1))/len(windows)
            tile_h = 0
            for index, window in enumerate(windows):
                tx = left+index*(tile_w+10)
                tile_h = self._quota(tx, cy, tile_w, window)
                self._region((account.id, 'quota', index), (tx, cy, tx+tile_w, cy+tile_h),
                             tooltip=f'{window.used_percent:.0f}% used · {window.remaining_percent:.0f}% remaining\nResets {window.compact_reset_at_display or "at an unknown time"}',
                             focusable=False)
            cy += tile_h
        else:
            message = self.app._inline_message(state)
            self._text(left, cy+5, self._ellipsize(message, 'caption', inner_w), 'caption', p['muted'])
            self._region((account.id, 'message'), (left, cy, right, cy+self._height('caption')+15), tooltip=message, focusable=False)
            cy += self._height('caption')+15
        if selected:
            cy += 16
            self._line(left, cy, right)
            cy += 15
            if duplicate:
                self._text(left, cy, 'This slot shares another account’s login.\nSign in again to restore its identity.',
                           'caption', p['warning'], width=inner_w)
                cy += self._height('caption')*2+12
            else:
                cy = self._tokens(account, left, cy, inner_w)
            cy += 14
            self._line(left, cy, right)
            cy += 11
            switching = self.app._desktop_restart_busy or self.app._pending_switch_account_id is not None
            actions = [
                ('refresh', lambda a=account: self.app.refresh_account(a), 'Refresh this account', not state.is_loading and not switching, False),
                ('key', lambda a=account: self.app.reauthenticate(a), 'Sign in again', self.app.reauthenticating_account_id is None and not self.app.is_adding_account and not switching, False),
                ('folder', lambda a=account: self.app.open_folder(a), f'Open account folder\n{account.codex_home_path}', True, False),
                ('edit', lambda a=account: self.app._edit_account(a), 'Rename account', True, False),
            ]
            if account.source.owns_files:
                actions.append(('trash', lambda a=account: self.app.remove_account(a), 'Remove account', not self.app._desktop_restart_busy, True))
            for index, (icon, command, tip, enabled, danger) in enumerate(actions):
                self._button((account.id, icon), left+index*36, cy, icon, command, tip, enabled=enabled, danger=danger)
            if state.snapshot:
                self._text(right, cy+16, state.snapshot.updated_at.astimezone().strftime('%H:%M'), 'caption', p['muted'], anchor='e')
            cy += 32
            if self.app._editing_account_id == account.id:
                cy += 10
                editor_h = max(38, self._height('body_small')+18)
                self._surface(left, cy, inner_w, editor_h, p['panel_alt'], p['hairline'], p['panel'], radius=10)
                self._editor_rect = (left+10, cy+8, right-42, cy+editor_h-8)
                self._button((account.id, 'save'), right-35, cy+(editor_h-28)/2, 'check',
                             lambda: self.close_editor(save=True), 'Save name · Enter', size=28, accent=True)
                cy += editor_h
        height = round(cy-y+16)
        background_item, _ = self._surface(x, y, width, height, p['panel'], p['accent_line'] if selected else p['hairline'],
                                            p['shell'], radius=18, satin=True)
        self.canvas.tag_lower(background_item, first_item)
        self._new_bounds[account.id] = (round(x), round(y), round(x+width), round(y+height))
        return height

    def _tokens(self, account, x, y, width):
        p = self.app.palette
        snapshot = self.app.token_usage_states.get(account.id)
        self._text(x, y, 'Token usage', 'body_small', p['muted'])
        y += self._height('body_small')+10
        if not snapshot:
            self._text(x, y, 'Collecting local usage…', 'caption', p['muted'])
            return y+self._height('caption')
        for index, (title, key) in enumerate((('Today', 'today'), ('7 days', 'lastSevenDays'), ('All time', 'allTime'))):
            tx = x+index*width/3
            value = snapshot.get(key, {}).get('totalTokens', 0)
            self._text(tx, y, compact(value), 'headline')
            self._text(tx, y+self._height('headline')+3, title, 'caption', p['muted'])
            self._region((account.id, 'total', key), (tx, y, tx+width/3, y+self._height('headline')+self._height('caption')+3),
                         tooltip=f'{title}\n{value:,} tokens', focusable=False)
        y += self._height('headline')+3+self._height('caption')+16
        daily = snapshot.get('daily', [])[-7:]
        maximum = max([1]+[point.get('usage', {}).get('totalTokens', 0) for point in daily])
        colors = ('#323a40', '#344e49', '#416d60', '#568d79', '#92c8ae')
        spacing = width/max(1, len(daily))
        cell_w = max(16, min(38, round(spacing-6)))
        for index, point in enumerate(daily):
            value = point.get('usage', {}).get('totalTokens', 0)
            ratio = value/maximum
            level = 0 if not value else 1 if ratio < .2 else 2 if ratio < .4 else 3 if ratio < .7 else 4
            tx = x+index*spacing+(spacing-cell_w)/2
            self._surface(tx, y, cell_w, 24, colors[level], colors[level], p['panel'], radius=5)
            try:
                date = datetime.fromisoformat(point['date']).strftime('%a')
            except (ValueError, TypeError):
                date = str(point['date'])[-5:]
            self._text(tx+cell_w/2, y+29, date, 'caption', p['muted'], anchor='n')
            self._region((account.id, 'token', point['date']), (tx, y, tx+cell_w, y+24),
                         tooltip=f"{point['date']}\n{value:,} tokens")
        y += 24+5+self._height('caption')+10
        values = snapshot.get('lastSevenDays', {})
        for index, (name, key) in enumerate((('Input', 'inputTokens'), ('Cached', 'cachedInputTokens'),
                                           ('Output', 'outputTokens'), ('Reasoning', 'reasoningOutputTokens'))):
            tx = x+index*width/4
            value = values.get(key, 0)
            self._text(tx, y, f'{name}\n{compact(value)}', 'caption', p['muted'])
            self._region((account.id, 'breakdown', key), (tx, y, tx+width/4, y+2*self._height('caption')),
                         tooltip=f'Last 7 days · {name}\n{value:,} tokens', focusable=False)
        return y+2*self._height('caption')

    def _empty(self, width):
        p = self.app.palette
        query = self.app.search_var.get()
        self._surface(0, 0, width, 190, p['panel'], p['hairline'], p['shell'], radius=18)
        self._icon(width/2-12, 24, 'search' if query else 'plus', p['accent'], 24)
        self._text(width/2, 62, 'No matching accounts' if query else 'A quieter way to manage Codex', 'headline', anchor='n')
        self._text(width/2, 93, 'Try another name or email.' if query else 'Add an account to see quota and token usage.', 'caption', p['muted'], anchor='n')
        title = 'Clear search' if query else 'Add account'
        command = (lambda: self.app.search_var.set('')) if query else self.app.start_add_account
        button_w = self._font('button').measure(title)+28
        self._surface((width-button_w)/2, 129, button_w, 34, p['accent_soft'], p['accent_line'], p['panel'], radius=9)
        self._text(width/2, 146, title, 'button', p['accent'], anchor='center')
        self._region(('empty', 'action'), ((width-button_w)/2, 129, (width+button_w)/2, 163), command, title)
        return 190

    def render(self, accounts, width=None, selected_account_id=None):
        if self._disposed or not self.canvas.winfo_exists():
            return
        accounts = list(accounts)
        width = max(260, round(width if width is not None else self.canvas.winfo_width()))
        same_view = self._selected == selected_account_id and self._width == width
        old_hover = self._find(self._hover_key) if same_view else None
        restore_tip_key = (self._tip_key if same_view and
                           (self.tooltip.window is not None or self.tooltip._job is not None) else None)
        tip_was_visible = self.tooltip.window is not None
        previous_selected, previous_bounds = self._selected, self.card_bounds
        old_top = self.canvas.canvasy(0)
        anchor_id = selected_account_id if selected_account_id is not None else previous_selected
        old_anchor = previous_bounds.get(anchor_id)
        self._accounts, self._width, self._selected = accounts, width, selected_account_id
        editing = self.app._editing_account_id
        if editing is not None and (editing != selected_account_id or not any(a.id == editing for a in accounts)):
            self._close_editor_only()
        self.hide_tooltip()
        self._hover_key = self._pressed_key = None
        self._generation += 1
        self._new_tag = f'account-scene-{id(self)}-{self._generation}'
        self._new_photos, self._new_regions, self._new_bounds = [], [], {}
        self._editor_rect = None
        identity = AccountIdentityPresentation(self.app.accounts)
        duplicates = identity.duplicate_ids
        columns = 2 if width >= 860 else 1
        gap = 10
        card_width = (width-gap*(columns-1))/columns
        y = 0
        committed = False
        try:
            if not accounts:
                y = self._empty(width)
            for offset in range(0, len(accounts), columns):
                heights = [self._card(account, column*(card_width+gap), y, card_width, identity, account.id in duplicates)
                           for column, account in enumerate(accounts[offset:offset+columns])]
                y += max(heights)+gap
            # No update()/idle flush occurs in this transaction: Tk paints the
            # final set of pure Canvas items together after this callback exits.
            self.canvas.itemconfigure(self._new_tag, state='normal')
            if self._tag is not None:
                self.canvas.delete(self._tag)
            self._tag = self._new_tag
            self._photos = self._new_photos  # Old photos live until old items are gone.
            self.regions, self.card_bounds = self._new_regions, self._new_bounds
            committed = True
            self.content_height = max(1, round(y if not accounts else y-gap+2))
            self.canvas.configure(scrollregion=(0, 0, width, self.content_height))
            new_anchor = self.card_bounds.get(anchor_id)
            if previous_selected != selected_account_id and old_anchor and new_anchor:
                old_top += new_anchor[1]-old_anchor[1]
            self.canvas.yview_moveto(max(0, old_top)/self.content_height)
            if not self._find(self.focus_key):
                fallback = (selected_account_id or previous_selected, 'details')
                self.focus_key = fallback if self._find(fallback) else None
            self._sync_editor()
            self._refresh_focus()
            if old_hover:
                hovered = self._find(old_hover.key)
                if hovered and hovered.rect == old_hover.rect:
                    self._hover_key = hovered.key
                    self._paint_button(hovered)
            if restore_tip_key:
                restored = self._find(restore_tip_key)
                if restored and (self._hover_key == restore_tip_key or
                                 (self._has_focus and self.focus_key == restore_tip_key)):
                    # A data refresh can occur under a stationary pointer.
                    # Reopen only an already-visible/pending tip, with new text.
                    # after(0) yields normally; no rendering event-loop reentry.
                    self._show_tip(restored, immediate=tip_was_visible)
        except Exception:
            # Editor setup happens after the pure Canvas transaction commits.
            # Its failure must not erase the already-complete new card scene.
            if not committed:
                self.canvas.delete(self._new_tag)
            raise

    def sync_selection(self):
        self.render(self._accounts, self._width, self.app.selected_account_id)

    def _find(self, key):
        return next((region for region in self.regions if region.key == key), None)

    def tooltip_for(self, key):
        region = self._find(key)
        return region.tooltip if region else ''

    def invoke(self, key):
        region = self._find(key)
        if region and region.enabled and region.command:
            self.hide_tooltip()
            return region.command()

    def _hit(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        return next((r for r in reversed(self.regions) if r.rect[0] <= x <= r.rect[2] and r.rect[1] <= y <= r.rect[3]), None)

    def _paint_button(self, region):
        if region and region.background_item:
            state = 'pressed' if region.key == self._pressed_key else 'focus' if self._has_focus and region.key == self.focus_key else 'hover' if region.key == self._hover_key else 'normal'
            self.canvas.itemconfigure(region.background_item, image=region.images.get(state, region.images['normal']))

    def _motion(self, event):
        region = self._hit(event)
        key = region.key if region else None
        if key != self._hover_key:
            previous = self._find(self._hover_key)
            self._hover_key = key
            self._paint_button(previous)
            self._paint_button(region)
            self._show_tip(region)
        self.canvas.configure(cursor='hand2' if region and region.command and region.enabled else 'arrow')

    def _leave(self, event=None):
        previous = self._find(self._hover_key)
        self._hover_key = None
        self._paint_button(previous)
        self.hide_tooltip()

    def _press(self, event):
        region = self._hit(event)
        self.hide_tooltip()
        if region and region.enabled:
            self._pressed_key = region.key
            if region.focusable:
                self.focus_key = region.key
            elif region.command and self._find((region.key[0], 'details')):
                self.focus_key = (region.key[0], 'details')
            self._pointer_focus_pending = self.canvas.focus_get() is not self.canvas
            self.canvas.focus_set()
            self._refresh_focus()
            self._paint_button(region)
        return 'break'

    def _release(self, event):
        key, self._pressed_key = self._pressed_key, None
        region = self._hit(event)
        self._paint_button(self._find(key))
        if region and region.key == key:
            if region.command is None and region.tooltip:
                self._show_tip(region)
            else:
                self.invoke(key)
        return 'break'

    def _focus_in(self, event=None):
        self._has_focus = True
        pointer_entry, self._pointer_focus_pending = self._pointer_focus_pending, False
        if not self._find(self.focus_key):
            available = [r for r in self.regions if r.focusable and r.enabled]
            self.focus_key = available[0].key if available else None
        if pointer_entry or not self.focus_key:
            # Mouse-down must retain its hit rectangle until button release.
            self._refresh_focus()
        else:
            self.focus_region(self.focus_key)

    def _focus_out(self, event=None):
        self._has_focus = False
        self._pointer_focus_pending = False
        self._keyboard_pressed = False
        self._pressed_key = None
        self.hide_tooltip()
        self._refresh_focus()

    def _refresh_focus(self):
        if self._focus_item:
            self.canvas.delete(self._focus_item)
            self._focus_item = None
        for region in self.regions:
            self._paint_button(region)
        region = self._find(self.focus_key)
        if region and region.enabled and self._has_focus and not region.background_item:
            x1, y1, x2, y2 = region.rect
            self._focus_item = self.canvas.create_rectangle(x1-2, y1-2, x2+2, y2+2, outline=self.app.palette['accent'], width=1, dash=(2, 2))

    def focus_region(self, key):
        region = self._find(key)
        if not region or not region.enabled or not region.focusable:
            return False
        self.focus_key = key
        self._refresh_focus()
        top = self.canvas.canvasy(0)
        height = self.canvas.winfo_height()
        if region.rect[1] < top:
            self.canvas.yview_moveto(max(0, region.rect[1]-8)/self.content_height)
        elif region.rect[3] > top+height:
            self.canvas.yview_moveto(max(0, region.rect[3]-height+8)/self.content_height)
        self._show_tip(region)
        return True

    def _tab(self, event=None):
        return self._traverse(1)

    def _shift_tab(self, event=None):
        return self._traverse(-1)

    def _traverse(self, direction):
        available = [r for r in self.regions if r.enabled and r.focusable]
        keys = [r.key for r in available]
        index = keys.index(self.focus_key) if self.focus_key in keys else (-1 if direction > 0 else len(keys))
        index += direction
        if 0 <= index < len(keys):
            self.focus_region(keys[index])
        else:
            self.hide_tooltip()
            target = self.canvas.tk_focusNext() if direction > 0 else self.canvas.tk_focusPrev()
            if target and target is not self.canvas:
                target.focus_set()
        return 'break'

    def _key_press(self, event=None):
        if not self._keyboard_pressed:
            self._keyboard_pressed = True
            self._pressed_key = self.focus_key
            self._paint_button(self._find(self.focus_key))
        return 'break'

    def _key_release(self, event=None):
        if self._keyboard_pressed:
            key = self._pressed_key
            self._keyboard_pressed = False
            self._pressed_key = None
            self._paint_button(self._find(key))
            self.invoke(key)
        return 'break'

    def _escape(self, event=None):
        if self._entry is not None:
            self.close_editor(False)
        else:
            self.hide_tooltip()
            self.app.hide_window()
        return 'break'

    def _show_tip(self, region, *, immediate=False):
        self.hide_tooltip()
        if region and region.tooltip:
            self._tip_key = region.key
            self.tooltip.text = region.tooltip
            self.tooltip.delay = 0 if immediate else 80 if 'token' in region.key else 420
            self.tooltip.schedule()

    def _tooltip_rect(self):
        region = self._find(self._tip_key)
        if region is None or self._disposed:
            return None
        x1, y1, x2, y2 = region.rect
        left, top = self.canvas.canvasx(0), self.canvas.canvasy(0)
        if y2 <= top or y1 >= top+self.canvas.winfo_height():
            return None
        sx, sy = self.canvas.winfo_rootx(), self.canvas.winfo_rooty()
        return tuple(round(v) for v in (sx+x1-left, sy+y1-top, sx+x2-left, sy+y2-top))

    def hide_tooltip(self):
        self._tip_key = None
        self.tooltip.text = ''
        self.tooltip.hide()

    def _scroll(self, event=None):
        self.hide_tooltip()

    def edit_account(self, account):
        if self.app._editing_account_id == account.id:
            self.close_editor(False)
            return
        self._close_editor_only()
        self.app._editing_account_id = account.id
        self.app.selected_account_id = account.id
        self.render(self._accounts, self._width, account.id)
        if self._entry:
            self._entry.focus_set()
            self._entry.icursor('end')

    def _sync_editor(self):
        account_id = self.app._editing_account_id
        if self._editor_rect is None or account_id is None:
            self._close_editor_only()
            return
        if self._editor_id != account_id:
            self._close_editor_only()
            self.app._editing_account_id = account_id
            account = next(a for a in self._accounts if a.id == account_id)
            p = self.app.palette
            self._draft_var = tk.StringVar(master=self.canvas, value=self.app.nickname_drafts.get(account_id, account.nickname or ''))
            self._draft_var.trace_add('write', lambda *_: self.app.nickname_drafts.__setitem__(account_id, self._draft_var.get()))
            self._entry = tk.Entry(self.canvas, textvariable=self._draft_var, bg=p['panel_alt'], fg=p['text'],
                                   insertbackground=p['accent'], relief='flat', bd=0, font=self._font('body_small'))
            self._entry.bind('<Return>', lambda _: self._editor_key(True))
            self._entry.bind('<Escape>', lambda _: self._editor_key(False))
            self._editor_item = self.canvas.create_window(0, 0, anchor='nw', window=self._entry)
            self._editor_id = account_id
            self.app._card_entries[account_id] = self._entry
        x1, y1, x2, y2 = self._editor_rect
        self.canvas.coords(self._editor_item, x1, y1)
        self.canvas.itemconfigure(self._editor_item, width=max(1, x2-x1), height=max(1, y2-y1))
        self.canvas.tag_raise(self._editor_item)

    def _editor_key(self, save):
        self.close_editor(save)
        return 'break'

    def _close_editor_only(self):
        if self._editor_item is not None:
            self.canvas.delete(self._editor_item)
        if self._entry is not None:
            self._entry.destroy()
        if self._editor_id is not None:
            self.app._card_entries.pop(self._editor_id, None)
        self._entry = self._editor_item = self._editor_id = self._draft_var = None
        self.app._editing_account_id = None

    def close_editor(self, save=False):
        account_id = self._editor_id
        self._close_editor_only()
        if save and account_id is not None:
            self.app.update_nickname(account_id)
        self.render(self._accounts, self._width, self.app.selected_account_id)
        if account_id:
            self.focus_key = (account_id, 'edit')
        self.canvas.focus_set()
        self._refresh_focus()

    def _destroy_event(self, event):
        if event.widget is self.canvas:
            self.dispose()

    def dispose(self):
        if self._disposed:
            return
        self._disposed = True
        self.tooltip.destroy()
        try:
            self._close_editor_only()
            if self._tag:
                self.canvas.delete(self._tag)
            if self._focus_item:
                self.canvas.delete(self._focus_item)
            for event, ident in self._bindings:
                if ident:
                    self.canvas.unbind(event, ident)
        except tk.TclError:
            pass
        self.regions.clear()
        self.card_bounds.clear()
        self._photos.clear()
        self._photo_cache.clear()
