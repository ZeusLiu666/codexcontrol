"""The dashboard's visual layer; account and refresh logic lives in app.py."""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from typing import Any

from PIL import Image, ImageDraw, ImageTk

from .models import AccountRuntimeState
from .presentation_logic import AccountIdentityPresentation
from .token_usage import compact
from .ui_components import RoundedPanel, IconButton, ActionButton, ToolTip, icon_photo
from .account_canvas import AccountCanvasScene


class QuotaBar(tk.Canvas):
    """Small, antialiased progress track that follows its actual layout width."""
    def __init__(self, parent, value, color, track, height=5):
        super().__init__(parent, width=1, height=height, bg=parent.cget('bg'), bd=0, highlightthickness=0)
        self.value = max(0, min(100, value))
        self.color, self.track, self.bar_height = color, track, height
        self.bind('<Configure>', self._paint)

    def _paint(self, event=None):
        w, h = max(1, self.winfo_width()), self.bar_height
        image = Image.new('RGB', (w * 3, h * 3), self.cget('bg'))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, w * 3 - 1, h * 3 - 1), radius=h * 1.5, fill=self.track)
        fill = round(w * 3 * self.value / 100)
        if fill:
            draw.rounded_rectangle((0, 0, max(1, fill - 1), h * 3 - 1), radius=min(h * 1.5, fill / 2), fill=self.color)
        self._image = ImageTk.PhotoImage(image.resize((w, h), Image.Resampling.LANCZOS), master=self)
        self.delete('all')
        self.create_image(0, 0, image=self._image, anchor='nw')


class DashboardView:
    def _configure_fonts(self):
        names = {name.casefold(): name for name in tkfont.families(self.root)}
        family = next((names[n.casefold()] for n in ('Segoe UI Variable Text', 'Segoe UI', 'Aptos') if n.casefold() in names), 'Segoe UI')
        self.font_family_display = self.font_family_text = family
        self.font_family_mono = 'Consolas'
        self.font_family_icon = family
        self.fonts = {
            'title': (family, 18, 'bold'), 'headline': (family, 11, 'bold'),
            'body': (family, 10), 'body_small': (family, 9),
            'caption': (family, 8), 'label': (family, 8, 'bold'),
            'button': (family, 9, 'bold'), 'button_small': (family, 8),
            'metric': (family, 18, 'bold'), 'mono': ('Consolas', 8),
            'icon': (family, 11), 'icon_small': (family, 10),
        }
        self.icons = {name: name for name in ('search', 'refresh', 'folder', 'trash', 'switch', 'key', 'check', 'edit', 'close')}
        self.icons.update(add='plus', save='check', spark='activity', metric_accounts='accounts', metric_live='check', metric_critical='activity')

    def _label(self, parent, text='', font='body_small', color=None, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color or self.palette['text'], font=self.fonts[font], bd=0, **kwargs)

    def _icon(self, parent, name, color=None, size=16):
        label = tk.Label(parent, bg=parent.cget('bg'), bd=0)
        label._image = icon_photo(name, size, color or self.palette['muted'], master=label)
        label.configure(image=label._image)
        return label

    def _icon_button(self, parent, name, command, tooltip, accent=False, danger=False, size=32):
        p = self.palette
        button = IconButton(parent, icon=name, command=command, size=size,
                          background=parent.cget('bg'), fill=p['accent_soft'] if accent else parent.cget('bg'),
                          hover_fill='#354049' if accent else p['hover'],
                          foreground=p['danger'] if danger else p['accent'] if accent else p['muted'],
                          border=p['accent_line'] if accent else parent.cget('bg'), radius=10,
                          tooltip=tooltip)
        ancestor = parent
        while ancestor is not None:
            account_id = getattr(ancestor, '_account_id', None)
            if account_id is not None:
                button._focus_key = (account_id, 'details' if name.startswith('chevron') else name)
                self._card_focus_widgets[button._focus_key] = button
                break
            ancestor = getattr(ancestor, 'master', None)
        return button

    def _build_ui(self):
        p = self.palette
        self._editing_account_id = None
        self._card_signature = None
        self._card_entries = {}
        self._card_focus_widgets = {}
        self._account_cards = {}
        self._visible_account_cards = self._account_cards
        self._cards_refresh_deferred = False
        self._focus_restore_key = None
        self._dismissed_status = None
        self._notice_last_message = None
        self._last_tray_state = None
        self.shell = tk.Frame(self.root, bg=p['shell'])
        self.shell.pack(fill='both', expand=True, padx=22, pady=(20, 12))
        header = tk.Frame(self.shell, bg=p['shell'])
        header.pack(fill='x', pady=(0, 18))
        self.brand_icon_image = ImageTk.PhotoImage(self._create_icon_image('neutral', 34))
        tk.Label(header, image=self.brand_icon_image, bg=p['shell'], bd=0).pack(side='left', padx=(0, 11))
        titles = tk.Frame(header, bg=p['shell'])
        titles.pack(side='left', fill='x', expand=True)
        self.title_label = self._label(titles, 'CodexControl', 'title')
        self.title_label.pack(anchor='w')
        self.subtitle_label = self._label(titles, 'Your accounts, at a glance', 'caption', p['muted'])
        self.subtitle_label.pack(anchor='w', pady=(2, 0))
        controls = tk.Frame(header, bg=p['shell'])
        controls.pack(side='right')
        self.add_button = self._icon_button(controls, 'plus', self.start_or_cancel_add_account, 'Add account', accent=True, size=36)
        self.add_button.pack(side='left', padx=(0, 5))
        self.refresh_button = self._icon_button(controls, 'refresh', self.refresh_all, 'Refresh all accounts', size=36)
        self.refresh_button.pack(side='left')

        # Compact overview replaces the three large, heavily outlined boxes.
        self.metrics_frame = tk.Frame(self.shell, bg=p['shell'])
        self.metrics_frame.pack(fill='x', pady=(0, 18))
        for column, (key, title, color) in enumerate((('accounts', 'ACCOUNTS', p['text']), ('live', 'AVAILABLE', p['success']), ('critical', 'LOW QUOTA', p['warning']))):
            self.metrics_frame.columnconfigure(column, weight=1, uniform='summary')
            tile = tk.Frame(self.metrics_frame, bg=p['shell'])
            tile.grid(row=0, column=column, sticky='ew')
            self._label(tile, title, 'caption', p['muted']).pack(anchor='w')
            value = self._label(tile, '0', 'metric', color)
            value.pack(anchor='w', pady=(3, 0))
            self._metric_value_labels[key] = value

        self.search_shell = RoundedPanel(self.shell, fill=p['panel'], border=p['hairline'], background=p['shell'], radius=12, padding=9)
        self._icon(self.search_shell.inner, 'search').pack(side='left', padx=(3, 8))
        self.search_entry = tk.Entry(self.search_shell.inner, textvariable=self.search_var, relief='flat', bd=0,
                                     bg=p['panel'], fg=p['text'], insertbackground=p['accent'], font=self.fonts['body_small'])
        self.search_entry.pack(side='left', fill='x', expand=True)
        ToolTip(self.search_entry, 'Search by name or email · Ctrl+F')
        self._icon_button(self.search_shell.inner, 'close', lambda: self.search_var.set(''), 'Clear search', size=24).pack(side='right')

        self.notice = RoundedPanel(self.shell, fill=p['panel_alt'], border=p['hairline'], background=p['shell'], radius=12, padding=8)
        self.notice_label = self._label(self.notice.inner, '', 'caption', p['muted'], anchor='w')
        self.notice_label.pack(side='left', fill='x', expand=True)
        self.notice_tip = ToolTip(self.notice_label, '')
        self._icon_button(self.notice.inner, 'close', self._dismiss_notice, 'Dismiss message', size=24).pack(side='right')

        list_heading = tk.Frame(self.shell, bg=p['shell'])
        list_heading.pack(fill='x', pady=(0, 9))
        self._label(list_heading, 'Accounts', 'body_small', p['muted']).pack(side='left')
        self.list_status = self._label(list_heading, 'Auto refresh', 'caption', p['muted'])
        self.list_status.pack(side='right')
        self.list_shell = tk.Frame(self.shell, bg=p['shell'])
        self.list_shell.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(self.list_shell, bg=p['shell'], highlightthickness=0, bd=0)
        self.canvas.pack(side='left', fill='both', expand=True)
        # Keep the tiny scrollbar functional without drawing a second frame.
        from .app import DarkScrollbar
        self.scrollbar = DarkScrollbar(self.list_shell, command=self.canvas.yview, palette=p, width=5)
        self.scrollbar.pack(side='right', fill='y', padx=(7, 0))
        self.canvas.configure(yscrollcommand=self._on_cards_scroll, yscrollincrement=0)
        # Cards share one buffered drawing surface. No native child windows are
        # mapped or resized when details open, close, or receive fresh data.
        self.cards_frame = None
        self._visible_cards_frame = None
        self._staged_cards_frame = None
        self._staged_cards_window = None
        self._cards_commit_job = None
        self.cards_window = None
        self.card_scene = AccountCanvasScene(self, self.canvas)
        self.canvas.bind('<Configure>', self._on_canvas_configure, add='+')
        self.canvas.bind_all('<MouseWheel>', self._on_mousewheel)

        footer = tk.Frame(self.shell, bg=p['shell'])
        footer.pack(fill='x', pady=(12, 0))
        self.remote_label = self._label(footer, 'Local tracking', 'caption', p['muted'])
        self.remote_label.pack(side='left')
        self.remote_tip = ToolTip(self.remote_label, 'Token usage is collected locally.')
        self.footer_label = self._label(footer, 'Auto sync · 30s', 'caption', p['muted'])
        self.footer_label.pack(side='right')
        self.root.bind('<Control-r>', lambda _: self.refresh_all())
        self.root.bind('<Control-f>', self._focus_search)
        self.root.bind('<Escape>', lambda _: self.hide_window())
        self.root.bind('<FocusIn>', self._on_dashboard_focus, add='+')

    def _on_dashboard_focus(self, event):
        widget = event.widget
        ancestor = widget
        while ancestor is not None:
            if ancestor is self._visible_cards_frame:
                self.root.after_idle(lambda: self._scroll_widget_into_view(widget))
                break
            ancestor = getattr(ancestor, 'master', None)

    def _on_cards_scroll(self, first, last):
        self.scrollbar.set(first, last)
        viewport = (float(first), float(last))
        previous = getattr(self, '_last_cards_viewport', None)
        self._last_cards_viewport = viewport
        scene = getattr(self, 'card_scene', None)
        if scene is not None and viewport != previous:
            scene.hide_tooltip()

    def _scroll_widget_into_view(self, widget):
        if (self._quitting or self.root.focus_get() is not widget
                or not widget.winfo_exists() or not widget.winfo_viewable()):
            return
        ancestor = widget
        while ancestor is not None:
            details_id = getattr(ancestor, '_details_account_id', None)
            if details_id is not None:
                record = self._visible_account_cards.get(details_id)
                if record is None or record['details'] is not ancestor:
                    record = self._account_cards.get(details_id)
                if record and not record['expanded']:
                    return
                if record and record['job'] is not None:
                    record['focus_after_animation'] = widget
                    return
                break
            ancestor = getattr(ancestor, 'master', None)
        bounds = self.canvas.bbox('all')
        if not bounds:
            return
        height = max(1, bounds[3] - bounds[1])
        top = widget.winfo_rooty() - self.canvas.winfo_rooty()
        bottom = top + widget.winfo_height()
        viewport = self.canvas.winfo_height()
        delta = top - 8 if top < 8 else bottom - viewport + 8 if bottom > viewport - 8 else 0
        if delta:
            self.canvas.yview_moveto(self.canvas.yview()[0] + delta / height)

    def _restore_card_focus(self):
        key = self._focus_restore_key
        self._focus_restore_key = None
        widget = self._card_focus_widgets.get(key)
        if widget is not None and widget.winfo_exists() and getattr(widget, 'enabled', True):
            widget.focus_set()

    def _focus_search(self, _=None):
        if not self.search_shell.winfo_manager():
            self.search_shell.pack(fill='x', pady=(0, 14), before=self.list_shell)
        self.search_entry.focus_set()
        return 'break'

    def _dismiss_notice(self):
        self._dismissed_status = self.status_message
        self.notice.pack_forget()

    def _render_now(self):
        self._render_job = None
        if self._quitting:
            return
        presentation = self._build_presentation_state()
        total = sum(s['today']['totalTokens'] for s in self.token_usage_states.values())
        self.subtitle_label.configure(text=f'{compact(total)} tokens today  ·  Your workspace')
        self.add_button.set_icon('close' if self.is_adding_account else 'plus')
        self.add_button.set_tooltip('Cancel account setup' if self.is_adding_account else 'Add account')
        switching = self._desktop_restart_busy or self._pending_switch_account_id is not None
        self.add_button.set_enabled(not switching and self.reauthenticating_account_id is None)
        self.refresh_button.set_enabled(not self.is_refreshing_all and not switching)
        self.list_status.configure(text='Refreshing…' if self.is_refreshing_all else 'Auto refresh')
        self._render_metrics(presentation)
        if len(self.accounts) > 5 or self.search_var.get():
            if not self.search_shell.winfo_manager():
                self.search_shell.pack(fill='x', pady=(0, 14), before=self.list_shell)
        elif self.root.focus_get() is not self.search_entry:
            self.search_shell.pack_forget()
        if self.status_message != self._notice_last_message:
            self._dismissed_status = None
            self._notice_last_message = self.status_message
        if self.status_message and self.status_message != self._dismissed_status:
            self.notice_label.configure(text=self._ellipsize(self.status_message.replace('\n', ' '), self.fonts['caption'], self._cards_available_width() - 70))
            self.notice_tip.set_text(self.status_message)
            if not self.notice.winfo_manager():
                self.notice.pack(fill='x', pady=(0, 12), before=self.list_shell)
        else:
            self.notice.pack_forget()
        remote = [s for s in self.remote_token_statuses if not s.get('isOptional') or s.get('isAvailable')]
        if remote:
            available = all(s.get('isAvailable') for s in remote)
            self.remote_label.configure(text=('●  Remote connected' if available else '○  Remote offline'), fg=self.palette['success'] if available else self.palette['muted'])
            self.remote_tip.set_text('\n'.join(f"{s['host']}: {s['detail']}" for s in remote) + '\nLocal usage continues to update.')
        else:
            self.remote_label.configure(text='●  Local tracking', fg=self.palette['muted'])
        self._render_cards(presentation)
        self._update_tray(presentation)

    def _render_metrics(self, presentation):
        for key, count in (('accounts', presentation.account_count), ('live', presentation.usable_quota_count), ('critical', presentation.low_quota_count)):
            self._metric_value_labels[key].configure(text=str(count))
        self._metric_value_labels['critical'].configure(fg=self.palette['warning'] if presentation.low_quota_count else self.palette['muted'])

    def _render_cards(self, presentation):
        signature = (self._accounts_revision, self._runtime_revision,
                     self._editing_account_id, presentation.search_query, self._cards_available_width(),
                     repr(self.token_usage_states), self._active_account_id(), self._desktop_restart_busy,
                     self.reauthenticating_account_id, self.is_adding_account, self._pending_switch_account_id,
                     self.selected_account_id)
        if signature == self._card_signature:
            return
        ordered = sorted(presentation.filtered_accounts, key=lambda a: not self._is_active_account(a))
        self.card_scene.render(ordered, self._cards_available_width(), self.selected_account_id)
        self._card_signature = signature

    def _schedule_cards_commit(self):
        if self._quitting or self._staged_cards_frame is None or self._cards_commit_job is not None:
            return
        staged = self._staged_cards_frame
        self._cards_commit_job = self.root.after_idle(lambda: self._commit_staged_cards(staged))

    def _commit_staged_cards(self, staged, previous_size=None, attempts=0):
        self._cards_commit_job = None
        if self._quitting or staged is not self._staged_cards_frame or not staged.winfo_exists():
            return
        if self._cards_render_job is not None or self._details_work_pending():
            self._cards_commit_job = self.root.after(12, lambda: self._commit_staged_cards(staged))
            return
        pending_layout = self._warm_staged_panels(staged)
        for record in self._account_cards.values():
            if not record['expanded']:
                surface = record['surface']
                height = record['summary'].winfo_reqheight() + surface.pad_y * 2
                surface.set_height_override(height)
                pending_layout |= surface.winfo_height() != height
        size = (staged.winfo_width(), staged.winfo_reqheight())
        # Finish pending native geometry before moving the frame into view.
        if attempts < 24 and (pending_layout or size != previous_size or staged.winfo_height() != size[1]):
            self._cards_commit_job = self.root.after_idle(lambda: self._commit_staged_cards(staged, size, attempts + 1))
            return
        staged.place_forget()
        self._staged_cards_window = self.canvas.create_window(
            (0, 0), window=staged, anchor='nw', width=max(1, self.canvas.winfo_width()))
        staged.lower(self._visible_cards_frame)
        self.canvas.event_generate('<Expose>', x=0, y=0,
                                   width=max(1, self.canvas.winfo_width()), height=max(1, self.canvas.winfo_height()))
        self._cards_commit_job = self.root.after_idle(lambda: self._reveal_staged_cards(staged))

    def _reveal_staged_cards(self, staged, attempts=0):
        self._cards_commit_job = None
        if self._quitting or staged is not self._staged_cards_frame or not staged.winfo_exists():
            return
        if self._details_work_pending():
            self._cards_commit_job = self.root.after(12, lambda: self._reveal_staged_cards(staged, attempts))
            return
        pending = self._warm_staged_panels(staged)
        if pending and attempts < 24:
            self._cards_commit_job = self.root.after_idle(lambda: self._reveal_staged_cards(staged, attempts + 1))
            return
        for record in self._account_cards.values():
            record['surface'].flush_visible_paint()
        previous, previous_window = self._visible_cards_frame, self.cards_window
        # The user can move focus while the replacement is being prepared.
        # Capture the live focus immediately before removing the old controls.
        focused = self.root.focus_get()
        ancestor = focused
        while ancestor is not None and ancestor is not previous:
            ancestor = getattr(ancestor, 'master', None)
        focus_key = getattr(focused, '_focus_key', None) if ancestor is previous else None
        restore_editor = focused is self.root or (ancestor is previous and hasattr(focused, '_editor_surface'))
        staged.lift(previous)
        self.cards_window = self._staged_cards_window
        self._visible_cards_frame = staged
        self._visible_account_cards = self._account_cards
        self._staged_cards_frame = self._staged_cards_window = None
        self.canvas.delete(previous_window)
        if previous.winfo_exists():
            previous.destroy()
        self._update_cards_scrollregion()
        expected_focus = self.root.focus_get()
        self.root.after_idle(lambda: self._restore_committed_card_focus(expected_focus, focus_key, restore_editor))
        self._flush_details_refresh()

    def _warm_staged_panels(self, parent):
        pending = False
        for widget in parent.winfo_children():
            if isinstance(widget, RoundedPanel):
                # Tk does not map canvas window items until their first expose.
                # A placed frame outside the viewport gets no native exposure;
                # supply its real damage rectangle before the visible swap.
                if not widget.inner.winfo_ismapped() or widget.inner.winfo_height() <= 1:
                    canvas = widget.canvas
                    canvas.event_generate('<Expose>', x=0, y=0,
                                          width=max(1, canvas.winfo_width()), height=max(1, canvas.winfo_height()))
                    pending = True
                pending |= widget._job is not None
            pending |= self._warm_staged_panels(widget)
        return pending

    def _restore_committed_card_focus(self, expected_focus, focus_key, restore_editor):
        if self._quitting or self.root.focus_get() is not expected_focus:
            return
        entry = self._card_entries.get(self._editing_account_id)
        if restore_editor and entry is not None and entry.winfo_exists():
            entry.focus_set()
            entry.icursor('end')
        else:
            self._focus_restore_key = focus_key
            self._restore_card_focus()

    def _render_empty_state(self, query):
        panel = RoundedPanel(self.cards_frame, fill=self.palette['panel'], border=self.palette['hairline'], background=self.palette['shell'], radius=18, padding=24)
        panel.pack(fill='x')
        self._icon(panel.inner, 'search' if query else 'plus', self.palette['accent'], 24).pack(pady=(6, 12))
        self._label(panel.inner, 'No matching accounts' if query else 'A quieter way to manage Codex', 'headline').pack()
        self._label(panel.inner, 'Try another name or email.' if query else 'Add an account to see quota and token usage.', 'caption', self.palette['muted']).pack(pady=(8, 10))
        ActionButton(panel.inner, text='Clear search' if query else 'Add account', icon='close' if query else 'plus', command=(lambda: self.search_var.set('')) if query else self.start_add_account,
                     fill=self.palette['accent_soft'], foreground=self.palette['accent'], border=self.palette['accent_line'], background=self.palette['panel'], tooltip='Clear search' if query else 'Add a Codex account').pack(pady=5)

    def _build_account_card(self, parent, account, width_hint):
        p = self.palette
        state = self.runtime_states.get(account.id, AccountRuntimeState())
        selected = self.selected_account_id == account.id
        active = self._is_active_account(account)
        identity = AccountIdentityPresentation(self.accounts)
        duplicate = account.id in identity.duplicate_ids
        # Retain the same native surfaces when details open; only the rim changes.
        bg = p['panel']
        surface = RoundedPanel(parent, fill=bg, border=p['accent_line'] if selected else p['hairline'], background=p['shell'], radius=18, padding=16, satin=True)
        card = surface.inner
        card._account_id = account.id
        summary = tk.Frame(card, bg=bg)
        summary.pack(fill='x')
        card = summary
        header = tk.Frame(card, bg=bg)
        header.pack(fill='x')
        actions = tk.Frame(header, bg=bg)
        actions.pack(side='right', padx=(8, 0))
        if active:
            self._make_inline_chip(actions, 'Active', p['accent_soft'], p['accent']).pack(side='left', padx=(0, 4))
        elif self._can_switch_account(account):
            self._icon_button(actions, 'switch', lambda: self.switch_account(account), f'Switch to {account.display_name}', accent=True).pack(side='left', padx=(0, 4))
        expand = self._icon_button(actions, 'chevron_up' if selected else 'chevron', lambda: self._toggle_selection(account.id), 'Collapse details' if selected else 'Usage & account details', size=26)
        expand.pack(side='left')
        title_area = tk.Frame(header, bg=bg)
        title_area.pack(side='left', fill='x', expand=True)
        display = identity.display_name(account)
        if display == account.email_hint and '@' in display:
            display = display.split('@', 1)[0]
        title = self._label(title_area, self._ellipsize(display, self.fonts['headline'], max(130, width_hint - 175)), 'headline', anchor='w')
        title.pack(anchor='w')
        email = self._label(title_area, self._ellipsize(account.email_hint or account.source.display_name, self.fonts['caption'], max(150, width_hint - 155)), 'caption', p['muted'])
        email.pack(anchor='w', pady=(4, 0))
        ToolTip(email, account.email_hint or account.source.display_name)
        for widget in (surface, surface.canvas, card, header, title_area, title, email):
            widget.bind('<Button-1>', lambda _, aid=account.id: self._toggle_selection(aid))

        meta = tk.Frame(card, bg=bg)
        meta.pack(fill='x', pady=(12, 10))
        self._label(meta, state.snapshot.plan_display_name if state.snapshot else 'Codex account', 'caption', p['muted']).pack(side='left')
        status = 'Duplicate login' if duplicate else 'Refreshing…' if state.is_loading else 'Cached · refresh failed' if state.error_message and state.snapshot else 'Needs attention' if state.error_message else 'Remaining quota'
        status_label = self._label(meta, status, 'caption', self._status_color(state) if state.error_message or duplicate else p['muted'])
        status_label.pack(side='right')
        if state.error_message:
            ToolTip(status_label, state.error_message)

        if state.snapshot and state.snapshot.has_quota_windows:
            windows = [w for w in (state.snapshot.primary_window, state.snapshot.secondary_window) if w]
            quota = tk.Frame(card, bg=bg)
            quota.pack(fill='x')
            for i, window in enumerate(windows):
                quota.columnconfigure(i, weight=1, uniform='quota')
                tile = self._build_window_tile(quota, bg, window)
                tile.grid(row=0, column=i, sticky='nsew', padx=(0 if i == 0 else 5, 5 if i < len(windows)-1 else 0))
        else:
            message = self._label(card, self._ellipsize(self._inline_message(state), self.fonts['caption'], width_hint - 48), 'caption', p['muted'])
            message.pack(anchor='w', pady=(5, 10))
            ToolTip(message, self._inline_message(state))
        details = tk.Frame(surface.inner, bg=bg)
        details._details_account_id = account.id
        # Keep native children mapped and painted behind the clip even when
        # collapsed. Mapping freshly-created widgets on a click flashes dark.
        if not selected:
            surface.set_height_override(1)
        details.pack(fill='x')
        self._populate_details(details, account, width_hint)
        record = dict(surface=surface, summary=summary, details=details,
                      expand=expand, expanded=selected, job=None, generation=0,
                      ready=False, focus_after_animation=None)
        self._account_cards[account.id] = record
        surface.bind('<Destroy>', lambda event: self._cancel_details_animation(record)
                     if event.widget is surface else None, add='+')
        summary.bind('<Configure>', lambda _: self._sync_collapsed_clip(record), add='+')
        self._set_details_interaction(record, selected)
        record['job'] = self.root.after_idle(lambda: self._finish_details_preload(record))
        return surface

    def _finish_details_preload(self, record, previous_size=None, attempts=0):
        surface = record['surface']
        if self._quitting or not surface.winfo_exists():
            return
        size = (record['summary'].winfo_reqheight(), record['details'].winfo_reqheight(), surface.inner.winfo_width())
        collapsed_height = size[0] + 2 * surface.pad_y
        if not record['expanded']:
            surface.set_height_override(collapsed_height)
        layout_pending = (record['summary'].winfo_height() != size[0] or record['details'].winfo_height() != size[1])
        if (size != previous_size or layout_pending) and attempts < 8:
            record['job'] = self.root.after_idle(lambda: self._finish_details_preload(record, size, attempts + 1))
            return
        record['ready'] = True
        record['job'] = None
        self._sync_details_selection()
        self._flush_details_refresh()

    def _sync_collapsed_clip(self, record):
        if record['ready'] and record['job'] is None and not record['expanded']:
            surface = record['surface']
            surface.set_height_override(record['summary'].winfo_reqheight() + 2 * surface.pad_y)

    def _set_details_interaction(self, record, enabled):
        record['details']._details_visible = bool(enabled)
        def descendants(parent):
            for widget in parent.winfo_children():
                yield widget
                yield from descendants(widget)
        for widget in descendants(record['details']):
            if not enabled:
                for tip in getattr(widget, '_control_tooltips', ()):
                    tip.hide()
            try:
                if not hasattr(widget, '_details_takefocus'):
                    widget._details_takefocus = widget.cget('takefocus')
                widget.configure(takefocus=widget._details_takefocus if enabled and getattr(widget, 'enabled', True) else 0)
            except tk.TclError:
                pass

    def _flush_details_refresh(self):
        if self._staged_cards_frame is not None:
            self._schedule_cards_commit()
            return
        if self._cards_refresh_deferred and not any(r['job'] is not None for r in self._account_cards.values()):
            self._cards_refresh_deferred = False
            self._render()

    def _populate_details(self, card, account, width_hint):
        p = self.palette
        bg = p['panel']
        state = self.runtime_states.get(account.id, AccountRuntimeState())
        duplicate = account.id in AccountIdentityPresentation(self.accounts).duplicate_ids
        tk.Frame(card, bg=p['hairline'], height=1).pack(fill='x', pady=(16, 14))
        if duplicate:
            self._label(card, 'This slot shares another account’s login.\nSign in again to restore its identity.', 'caption', p['warning'], justify='left').pack(anchor='w', pady=(0, 12))
        else:
            self._build_token_panel(card, account, bg, width_hint)
        tk.Frame(card, bg=p['hairline'], height=1).pack(fill='x', pady=(14, 10))
        toolbar = tk.Frame(card, bg=bg)
        toolbar.pack(fill='x')
        refresh = self._icon_button(toolbar, 'refresh', lambda: self.refresh_account(account), 'Refresh this account')
        refresh.pack(side='left', padx=(0, 4))
        switching = self._desktop_restart_busy or self._pending_switch_account_id is not None
        refresh.set_enabled(not state.is_loading and not switching)
        reauth = self._icon_button(toolbar, 'key', lambda: self.reauthenticate(account), 'Sign in again')
        reauth.pack(side='left', padx=(0, 4))
        reauth.set_enabled(self.reauthenticating_account_id is None and not self.is_adding_account and not switching)
        self._icon_button(toolbar, 'folder', lambda: self.open_folder(account), f'Open account folder\n{account.codex_home_path}').pack(side='left', padx=(0, 4))
        self._icon_button(toolbar, 'edit', lambda: self._edit_account(account), 'Rename account').pack(side='left', padx=(0, 4))
        if account.source.owns_files:
            remove = self._icon_button(toolbar, 'trash', lambda: self.remove_account(account), 'Remove account', danger=True)
            remove.pack(side='left')
            remove.set_enabled(not self._desktop_restart_busy)
        if state.snapshot:
            self._label(toolbar, state.snapshot.updated_at.astimezone().strftime('%H:%M'), 'caption', p['muted']).pack(side='right')
        if self._editing_account_id == account.id:
            self._build_nickname_editor(card, account)

    def _cancel_details_animation(self, record):
        record['generation'] += 1
        if record['job'] is not None:
            try:
                self.root.after_cancel(record['job'])
            except tk.TclError:
                pass
            record['job'] = None

    def _sync_details_selection(self):
        if hasattr(self, 'card_scene'):
            self._card_signature = None
            self.card_scene.sync_selection()
            return
        seen = set()
        for account_id, record in [*self._visible_account_cards.items(), *self._account_cards.items()]:
            if id(record) in seen:
                continue
            seen.add(id(record))
            expanded = account_id == self.selected_account_id
            if record['ready'] and record['expanded'] != expanded:
                self._animate_details(record, expanded)

    def _details_work_pending(self):
        return any(record['job'] is not None for records in
                   (self._visible_account_cards, self._account_cards) for record in records.values())

    def _animate_details(self, record, expanded):
        """Reveal retained, prepainted details in one native layout commit."""
        surface, details = record['surface'], record['details']
        self._cancel_details_animation(record)
        generation = record['generation']
        start_height = max(1, surface.winfo_height())
        surface.set_height_override(start_height)
        record['expanded'] = expanded
        record['expand'].set_icon('chevron_up' if expanded else 'chevron')
        record['expand'].set_tooltip('Collapse details' if expanded else 'Usage & account details')
        surface.border = self.palette['accent_line'] if expanded else self.palette['hairline']
        self._set_details_interaction(record, expanded)
        if not expanded:
            focused = self.root.focus_get()
            ancestor = focused
            while ancestor is not None:
                if ancestor is details:
                    record['expand'].focus_set()
                    break
                ancestor = getattr(ancestor, 'master', None)
            account_id = surface.inner._account_id
            entry = self._card_entries.pop(account_id, None)
            if entry is not None and entry.winfo_exists():
                entry._editor_surface.destroy()
            if self._editing_account_id == account_id:
                self._editing_account_id = None

        def valid():
            return not self._quitting and generation == record['generation'] and surface.winfo_exists()

        def begin(previous_target=None, attempts=0):
            if not valid():
                return
            summary_height = record['summary'].winfo_reqheight()
            target = summary_height + (details.winfo_reqheight() if expanded else 0) + 2 * surface.pad_y
            # A rename editor or a resize can change nested geometry. Confirm
            # its natural target before revealing the already-painted content.
            if attempts < 8 and (target != previous_target or (expanded and details.winfo_height() != details.winfo_reqheight())):
                record['job'] = self.root.after_idle(lambda: begin(target, attempts + 1))
                return
            # Keep the operation busy while idle layout and native paint run;
            # a queued refresh must not replace this card halfway through.
            record['job'] = '__details_painting__'
            surface.set_height_override(None if expanded else target)
            self.root.update_idletasks()
            if not valid():
                return
            self._flush_visible_card_paint()
            if not valid():
                return
            record['job'] = None
            focus_widget = record['focus_after_animation']
            record['focus_after_animation'] = None
            if focus_widget is not None and self.root.focus_get() is focus_widget:
                self.root.after_idle(lambda: self._scroll_widget_into_view(focus_widget))
            self._flush_details_refresh()

        record['job'] = self.root.after_idle(begin)

    def _flush_visible_card_paint(self):
        top = self.canvas.winfo_rooty()
        bottom = top + self.canvas.winfo_height()
        for record in tuple(self._visible_account_cards.values()):
            surface = record['surface']
            if (surface.winfo_exists() and surface.winfo_ismapped()
                    and surface.winfo_rooty() < bottom
                    and surface.winfo_rooty() + surface.winfo_height() > top):
                surface.flush_visible_paint()

    def _edit_account(self, account):
        if hasattr(self, 'card_scene'):
            self.card_scene.edit_account(account)
            return
        self._editing_account_id = None if self._editing_account_id == account.id else account.id
        self.root.focus_set()
        self._render_now()

    def _build_nickname_editor(self, parent, account):
        p = self.palette
        row = RoundedPanel(parent, fill=p['panel_alt'], border=p['hairline'], background=parent.cget('bg'), radius=10, padding=8)
        row.pack(fill='x', pady=(10, 0))
        var = tk.StringVar(master=self.root, value=self.nickname_drafts.get(account.id, account.nickname or ''))
        var.trace_add('write', lambda *_: self.nickname_drafts.__setitem__(account.id, var.get()))
        entry = tk.Entry(row.inner, textvariable=var, bg=p['panel_alt'], fg=p['text'], insertbackground=p['accent'], relief='flat', bd=0, font=self.fonts['body_small'])
        entry._editor_surface = row
        entry.pack(side='left', fill='x', expand=True, padx=(4, 6))
        self._card_entries[account.id] = entry
        def save(_=None):
            self._editing_account_id = None
            self.root.focus_set()
            self.update_nickname(account.id)
            return 'break'
        entry.bind('<Return>', save)
        entry.bind('<Escape>', lambda _: (self._edit_account(account), 'break')[-1])
        self._icon_button(row.inner, 'check', save, 'Save name · Enter', accent=True, size=28).pack(side='right')
        if self._staged_cards_frame is None:
            entry.focus_set()
            entry.icursor('end')

    def _build_window_tile(self, parent, card_bg, window):
        p = self.palette
        surface = RoundedPanel(parent, fill=p['panel_alt'], border=p['panel_alt'], background=card_bg, radius=12, padding=11)
        tile = surface.inner
        heading = tk.Frame(tile, bg=p['panel_alt'])
        heading.pack(fill='x')
        self._label(heading, window.display_name, 'caption', p['muted']).pack(side='left')
        self._label(heading, f'{window.remaining_percent:.0f}%', 'headline').pack(side='right')
        QuotaBar(tile, window.remaining_percent, self._quota_color(window.remaining_percent), p['track']).pack(fill='x', pady=(10, 8))
        self._label(tile, window.compact_reset_at_display or 'Reset time unavailable', 'caption', p['muted']).pack(anchor='w')
        ToolTip(surface, f'{window.used_percent:.0f}% used · {window.remaining_percent:.0f}% remaining\nResets {window.compact_reset_at_display or "at an unknown time"}')
        return surface

    def _build_token_panel(self, parent, account, bg, width_hint):
        p = self.palette
        snapshot = self.token_usage_states.get(account.id)
        self._label(parent, 'Token usage', 'body_small', p['muted']).pack(anchor='w', pady=(0, 10))
        if not snapshot:
            self._label(parent, 'Collecting local usage…', 'caption', p['muted']).pack(anchor='w')
            return
        totals = tk.Frame(parent, bg=bg)
        totals.pack(fill='x')
        for col, (title, key) in enumerate((('Today', 'today'), ('7 days', 'lastSevenDays'), ('All time', 'allTime'))):
            totals.columnconfigure(col, weight=1, uniform='totals')
            self._label(totals, compact(snapshot[key]['totalTokens']), 'headline').grid(row=0, column=col, sticky='w')
            self._label(totals, title, 'caption', p['muted']).grid(row=1, column=col, sticky='w', pady=(3, 0))
        heat = tk.Frame(parent, bg=bg)
        heat.pack(fill='x', pady=(16, 10))
        daily = snapshot.get('daily', [])[-7:]
        maximum = max([1] + [point['usage']['totalTokens'] for point in daily])
        colors = ('#323a40', '#344e49', '#416d60', '#568d79', '#92c8ae')
        for col, point in enumerate(daily):
            heat.columnconfigure(col, weight=1, uniform='days')
            value = point['usage']['totalTokens']
            ratio = value / maximum
            level = 0 if not value else 1 if ratio < .2 else 2 if ratio < .4 else 3 if ratio < .7 else 4
            cell = tk.Canvas(heat, width=38, height=24, bg=bg, highlightthickness=0, bd=0, takefocus=1)
            cell.grid(row=0, column=col, pady=(0, 5))
            cell._token_cell = True
            cell._focus_key = (account.id, 'token', point['date'])
            self._card_focus_widgets[cell._focus_key] = cell
            im = Image.new('RGB', (114, 72), bg)
            ImageDraw.Draw(im).rounded_rectangle((0, 0, 113, 71), radius=17, fill=colors[level])
            cell._image = ImageTk.PhotoImage(im.resize((38, 24), Image.Resampling.LANCZOS), master=cell)
            cell.create_image(0, 0, image=cell._image, anchor='nw')
            date = datetime.fromisoformat(point['date'])
            self._label(heat, date.strftime('%a'), 'caption', p['muted']).grid(row=1, column=col)
            self._bind_token_tooltip(cell, f"{point['date']}\n{value:,} tokens")
        values = snapshot['lastSevenDays']
        detail = tk.Frame(parent, bg=bg)
        detail.pack(fill='x')
        for col, (name, key) in enumerate((('Input', 'inputTokens'), ('Cached', 'cachedInputTokens'), ('Output', 'outputTokens'), ('Reasoning', 'reasoningOutputTokens'))):
            detail.columnconfigure(col, weight=1, uniform='breakdown')
            label = self._label(detail, f'{name}\n{compact(values[key])}', 'caption', p['muted'], justify='left')
            label.grid(row=0, column=col, sticky='w')
            ToolTip(label, f'Last 7 days · {name}\n{values[key]:,} tokens')

    def _bind_token_tooltip(self, cell, text):
        cell._tooltip = ToolTip(cell, text, delay=80)

    def _make_inline_chip(self, parent, text, bg, fg):
        surface = RoundedPanel(parent, fill=bg, border=bg, background=parent.cget('bg'), radius=10, padding=5)
        self._label(surface.inner, text, 'caption', fg).pack(padx=3)
        return surface

    def _update_tray(self, presentation):
        if self.tray_icon is None:
            return
        status = presentation.menu_bar_quota_state
        title = f'CodexControl · {presentation.account_count} accounts · {presentation.usable_quota_count} available'
        if (status, title) == self._last_tray_state:
            return
        try:
            self.tray_icon.icon = self._create_icon_image(status, 64)
            self.tray_icon.title = title
            self._last_tray_state = (status, title)
        except Exception:
            pass
