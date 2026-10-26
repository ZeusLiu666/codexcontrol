from __future__ import annotations

import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
import time
import os
import queue
import shutil
import threading
import sys
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass, replace
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable
from uuid import UUID

from PIL import Image, ImageDraw, ImageTk
import pystray

from .account_manager import CodexAccountManager, CodexAccountManagerError, ManagedLoginProcess
from .brand_icon import build_orbit_dial_icon
from .codex_api import AuthBackedIdentity
from .codex_api import CodexApiError
from .codex_api import fetch_snapshot
from .codex_desktop import CodexDesktopControlError, RESTART_STATUS_PATH, restart_codex_desktop
from .models import AccountRuntimeState, AccountUsageSnapshot, RemovedAccountIdentity, StoredAccount, StoredAccountSource, utc_now
from .presentation_logic import account_sort_key, is_active_account, AccountIdentityPresentation
from .token_usage import TokenUsageTracker, RemoteTokenUsageMirror, compact, zero
from .stores import AccountStore, SnapshotStore
from .dashboard_view import DashboardView
from .native_window import bring_window_to_front, apply_window_appearance
from .file_locations import APP_SUPPORT_DIRECTORY
from .file_locations import MANAGED_HOMES_DIRECTORY


@dataclass(slots=True)
class RoundedButtonTheme:
    bg: str
    fg: str
    hover: str
    border: str
    disabled_bg: str
    disabled_fg: str


@dataclass(slots=True)
class PresentationState:
    search_query: str
    filtered_accounts: list[StoredAccount]
    account_count: int
    low_quota_count: int
    usable_quota_count: int
    exhausted_count: int

    @property
    def menu_bar_quota_state(self) -> str:
        if self.account_count == 0:
            return "empty"
        if self.usable_quota_count > 0:
            return "available"
        if self.exhausted_count == self.account_count:
            return "unavailable"
        return "unresolved"


class RoundedButton(tk.Canvas):
    def __init__(
        self,
        parent: tk.Widget,
        text: str,
        command: Callable[[], None],
        theme: RoundedButtonTheme,
        font: tuple[str, int] | tuple[str, int, str],
        icon: str | None,
        icon_font: tuple[str, int] | tuple[str, int, str] | None,
        radius: int,
        pad_x: int,
        pad_y: int,
    ) -> None:
        super().__init__(
            parent,
            highlightthickness=0,
            bd=0,
            relief="flat",
            bg=parent.cget("bg"),
            cursor="hand2",
            takefocus=0,
        )
        self.text = text
        self.command = command
        self.theme = theme
        self.font = font
        self.icon = icon
        self.icon_font = icon_font
        self.radius = radius
        self.pad_x = pad_x
        self.pad_y = pad_y
        self.enabled = True
        self._hovering = False
        self._text_font = tkfont.Font(font=self.font)
        self._icon_resolved_font = tkfont.Font(font=self.icon_font) if self.icon_font else None

        self.bind("<Configure>", self._redraw)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

        width, height = self._measure()
        self.configure(width=width, height=height)
        self._redraw()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._redraw()

    def set_text(self, text: str) -> None:
        self.text = text
        width, height = self._measure()
        self.configure(width=width, height=height)
        self._redraw()

    def set_theme(self, theme: RoundedButtonTheme) -> None:
        self.theme = theme
        self._redraw()

    def set_icon(self, icon: str | None) -> None:
        self.icon = icon
        width, height = self._measure()
        self.configure(width=width, height=height)
        self._redraw()

    def _on_enter(self, _: tk.Event[Any]) -> None:
        self._hovering = True
        self._redraw()

    def _on_leave(self, _: tk.Event[Any]) -> None:
        self._hovering = False
        self._redraw()

    def _on_click(self, _: tk.Event[Any]) -> None:
        if self.enabled:
            self.command()

    def _redraw(self, _: tk.Event[Any] | None = None) -> None:
        self.delete("all")
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())

        if self.enabled:
            fill = self.theme.hover if self._hovering else self.theme.bg
            fg = self.theme.fg
            border = self.theme.border
        else:
            fill = self.theme.disabled_bg
            fg = self.theme.disabled_fg
            border = self.theme.border

        self._rounded_rect(0, 0, width - 1, height - 1, self.radius, fill, border)
        text_width = self._text_font.measure(self.text)
        icon_width = 0
        if self.icon and self._icon_resolved_font:
            icon_width = self._icon_resolved_font.measure(self.icon) + 8

        total_width = text_width + icon_width
        start_x = (width - total_width) / 2

        if self.icon and self._icon_resolved_font:
            icon_text_width = self._icon_resolved_font.measure(self.icon)
            self.create_text(
                start_x + (icon_text_width / 2),
                height // 2,
                text=self.icon,
                fill=fg,
                font=self._icon_resolved_font,
            )
            start_x += icon_text_width + 8

        self.create_text(
            start_x + (text_width / 2),
            height // 2,
            text=self.text,
            fill=fg,
            font=self._text_font,
        )

    def _measure(self) -> tuple[int, int]:
        text_width = self._text_font.measure(self.text)
        text_height = self._text_font.metrics("linespace")
        icon_width = 0
        icon_height = 0
        if self.icon and self._icon_resolved_font:
            icon_width = self._icon_resolved_font.measure(self.icon) + 8
            icon_height = self._icon_resolved_font.metrics("linespace")

        width = text_width + icon_width + (self.pad_x * 2)
        height = max(text_height, icon_height) + (self.pad_y * 2)
        return width, height

    def _rounded_rect(self, x1: int, y1: int, x2: int, y2: int, radius: int, fill: str, outline: str) -> None:
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        ]
        self.create_polygon(points, smooth=True, fill=fill, outline=outline)


class DarkScrollbar(tk.Canvas):
    def __init__(
        self,
        parent: tk.Widget,
        command: Callable[..., Any],
        palette: dict[str, str],
        width: int = 11,
    ) -> None:
        super().__init__(
            parent,
            width=width,
            highlightthickness=0,
            bd=0,
            relief="flat",
            bg=palette["shell"],
            cursor="hand2",
            takefocus=0,
        )
        self.command = command
        self.palette = palette
        self.bar_width = width
        self.first = 0.0
        self.last = 1.0
        self.thumb_top = 0
        self.thumb_bottom = 0
        self.drag_offset = 0
        self.dragging = False

        self.bind("<Configure>", self._redraw)
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

        self._redraw()

    def set(self, first: str | float, last: str | float) -> None:
        self.first = max(0.0, min(1.0, float(first)))
        self.last = max(self.first, min(1.0, float(last)))
        self._redraw()

    def _on_press(self, event: tk.Event[Any]) -> None:
        if self.thumb_top <= event.y <= self.thumb_bottom:
            self.dragging = True
            self.drag_offset = event.y - self.thumb_top
            return

        self._jump_to(event.y)

    def _on_drag(self, event: tk.Event[Any]) -> None:
        if not self.dragging:
            return

        height = max(1, self.winfo_height())
        thumb_size = max(24, self.thumb_bottom - self.thumb_top)
        track = max(1, height - thumb_size)
        top = min(max(0, event.y - self.drag_offset), track)
        first = top / track if track else 0.0
        self.command("moveto", str(first))

    def _on_release(self, _: tk.Event[Any]) -> None:
        self.dragging = False

    def _jump_to(self, y: int) -> None:
        height = max(1, self.winfo_height())
        visible = max(0.05, self.last - self.first)
        thumb_size = max(24, int(height * visible))
        track = max(1, height - thumb_size)
        target = min(max(0, y - (thumb_size // 2)), track)
        first = target / track if track else 0.0
        self.command("moveto", str(first))

    def _redraw(self, _: Any = None) -> None:
        self.delete("all")
        height = max(1, self.winfo_height())
        if self.last - self.first >= .999:
            return
        self.thumb_top = int(height * self.first)
        self.thumb_bottom = max(self.thumb_top + 26, int(height * self.last))
        width = self.bar_width
        self.create_line(width / 2, self.thumb_top + width / 2, width / 2,
                         self.thumb_bottom - width / 2, fill=self.palette["hairline"],
                         width=width, capstyle="round")


class CodexControlWindowsApp(DashboardView):
    AUTO_REFRESH_MS = 5 * 60 * 1000
    GROUP_REFRESH_FLUSH_MS = 120
    QUEUE_POLL_MS = 150
    SEARCH_RENDER_MS = 80
    CARD_RENDER_BATCH_ROWS = 2
    ELLIPSIS_CACHE_MAX = 4096

    def __init__(self, start_hidden: bool = False) -> None:
        self.token_tracker = TokenUsageTracker()
        self.remote_mirror = RemoteTokenUsageMirror()
        self.token_usage_states = {}
        self.remote_token_statuses = []
        self._token_busy = False
        self._token_job = None
        self.account_store = AccountStore()
        self.snapshot_store = SnapshotStore()
        self.account_manager = CodexAccountManager()
        worker_count = min(12, max(4, (os.cpu_count() or 4) * 2))
        self.executor = ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="codexcontrol")
        self.events: queue.Queue[tuple[Any, ...]] = queue.Queue()

        self.accounts: list[StoredAccount] = []
        self.removed_accounts: list[RemovedAccountIdentity] = []
        self.runtime_states: dict[UUID, AccountRuntimeState] = {}
        self.nickname_drafts: dict[UUID, str] = {}
        self.selected_account_id: UUID | None = None
        self.active_identity: AuthBackedIdentity | None = None
        self.status_message: str | None = None
        self.is_refreshing_all = False
        self.is_adding_account = False
        self.reauthenticating_account_id: UUID | None = None
        self._group_refresh_pending = 0
        self._add_handle: ManagedLoginProcess | None = None
        self._reauth_handle: ManagedLoginProcess | None = None
        self._quitting = False
        self._operation_sequence = 0
        self._refresh_requests: dict[UUID, tuple[int, bool]] = {}
        self._refresh_futures: dict[int, Future[Any]] = {}
        self._pending_switch_account_id: UUID | None = None
        self._account_operation_locks: dict[UUID, Any] = {}
        self._pending_futures: set[Future[Any]] = set()
        self._add_request_id: int | None = None
        self._reauth_request_id: int | None = None
        self._cancelled_add_requests: set[int] = set()
        self._account_cleanup_count = 0
        self._token_request_id: int | None = None
        self._token_context_revision = 0
        self._group_refresh_flush_job: str | None = None
        self._group_refresh_flush_pending = False
        self._resize_job: str | None = None
        self._render_job: str | None = None
        self._cards_render_job: str | None = None
        self._search_render_job: str | None = None
        self._queue_poll_job: str | None = None
        self._auto_refresh_job: str | None = None
        self._initial_refresh_job: str | None = None
        self._restart_status_job = None
        self._desktop_restart_busy = False
        self._desktop_restart_process = None
        self._desktop_restart_started = 0
        self._restart_desktop_job: str | None = None
        self._cards_render_token = 0
        self._last_render_width = 0
        self._accounts_revision = 0
        self._runtime_revision = 0
        self._search_revision = 0
        self._presentation_cache_key: tuple[int, int, int] | None = None
        self._presentation_cache: PresentationState | None = None
        self._font_object_cache: dict[tuple[Any, ...], tkfont.Font] = {}
        self._ellipsize_cache: dict[tuple[str, tuple[Any, ...], int], str] = {}
        self._metric_value_labels: dict[str, tk.Label] = {}
        self.start_hidden = start_hidden

        # A quiet, cool palette keeps the information dense without making the
        # window feel heavy.  Borders are intentionally low contrast so cards
        # read as one surface instead of a grid of boxes.
        self.palette = {'bg': '#1b1d22', 'shell': '#1b1d22', 'panel': '#24272d', 'panel_alt': '#2b3037', 'selected': '#252e35', 'text': '#edf0f2', 'muted': '#9aA3ad', 'hairline': '#373d44', 'accent': '#b0ddd0', 'accent_soft': '#304c49', 'accent_line': '#47665f', 'success': '#94c8ad', 'warning': '#ddbc85', 'danger': '#df9e9a', 'neutral': '#89939e', 'dark_icon': '#181c20', 'track': '#414950', 'hover': '#353d45'}

        self.root = tk.Tk()
        self.root.report_callback_exception = self._report_ui_error
        self.root.title("CodexControl")
        self.root.geometry("520x800")
        self.root.minsize(460, 620)
        self.root.configure(bg=self.palette["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        self.search_var = tk.StringVar(master=self.root)
        self.root.bind("<Configure>", self._on_root_configure)

        self._configure_fonts()

        self.window_icon_images: list[ImageTk.PhotoImage] = []
        self.brand_icon_image: ImageTk.PhotoImage | None = None
        self._set_window_icon()

        self._configure_styles()
        self._build_ui()
        self.root.update_idletasks()
        self._apply_dark_title_bar()
        self._setup_tray_icon()
        self._load_initial_state()
        if self.selected_account_id is None and self.accounts:
            self.selected_account_id = self._active_account_id() or self.accounts[0].id
        self._render_now()
        if self.start_hidden:
            self.hide_window()

        self.search_var.trace_add("write", lambda *_: self._on_search_change())
        self._queue_poll_job = self.root.after(self.QUEUE_POLL_MS, self._process_event_queue)
        self._initial_refresh_job = self.root.after(800, self.refresh_all)
        self._auto_refresh_job = self.root.after(self.AUTO_REFRESH_MS, self._auto_refresh_tick)
        self._token_job = self.root.after(1200, self._token_tick)

    def run(self) -> None:
        self.root.mainloop()

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._pending_switch_account_id = None
        for handle in (self._add_handle, self._reauth_handle):
            if handle is not None:
                self._cancel_login_in_background(handle)
        for future in tuple(self._pending_futures):
            future.cancel()
        # A final flush includes results received during the group debounce.
        self._persist_accounts_silently()
        self._persist_snapshots_silently()
        for job_name in (
            "_token_job", "_search_render_job", "_cards_render_job", "_render_job",
            "_resize_job", "_group_refresh_flush_job", "_queue_poll_job",
            "_auto_refresh_job", "_initial_refresh_job", "_restart_desktop_job",
            "_restart_status_job", "_cards_commit_job",
        ):
            job = getattr(self, job_name, None)
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, job_name, None)
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.executor.shutdown(wait=False, cancel_futures=True)
        if getattr(self, 'card_scene', None) is not None:
            self.card_scene.dispose()
        self.root.destroy()

    def show_window(self) -> None:
        if not self._quitting:
            bring_window_to_front(self.root)

    def hide_window(self) -> None:
        self.root.withdraw()

    def refresh_all(self) -> None:
        if self._quitting or self._desktop_restart_busy or self._pending_switch_account_id is not None:
            return
        if self._initial_refresh_job is not None:
            try:
                self.root.after_cancel(self._initial_refresh_job)
            except tk.TclError:
                pass
            self._initial_refresh_job = None
        if not self.accounts or self.is_refreshing_all:
            return
        duplicates = AccountIdentityPresentation(self.accounts).duplicate_ids
        refreshable_accounts = [
            account for account in self.accounts
            if not self._requires_reauthentication(account.id)
            and account.id not in duplicates
            and account.id not in self._refresh_requests
            and account.id != self.reauthenticating_account_id
        ]
        if not refreshable_accounts:
            return
        self.is_refreshing_all = True
        self._group_refresh_pending = len(refreshable_accounts)
        for account in refreshable_accounts:
            self._begin_refresh(account, from_group=True, verify_live_data=False)
        self._mark_runtime_dirty()
        self._render()

    def refresh_account(self, account: StoredAccount) -> None:
        if self._quitting or self._desktop_restart_busy or self._pending_switch_account_id is not None:
            return
        current = next((candidate for candidate in self.accounts if candidate.id == account.id), None)
        if current is None:
            return
        if current.id in AccountIdentityPresentation(self.accounts).duplicate_ids:
            self.status_message = "Duplicate login; reauthenticate this account slot."
            self._render()
            return
        if current.id in self._refresh_requests or current.id == self.reauthenticating_account_id:
            return
        self._begin_refresh(current, from_group=False, verify_live_data=True)
        self._mark_runtime_dirty()
        self._render()

    def _next_operation_id(self) -> int:
        self._operation_sequence += 1
        return self._operation_sequence

    def _account_lock(self, account_id: UUID):
        return self._account_operation_locks.setdefault(account_id, threading.RLock())

    def _begin_refresh(self, account: StoredAccount, *, from_group: bool, verify_live_data: bool) -> None:
        request_id = self._next_operation_id()
        self._refresh_requests[account.id] = (request_id, from_group)
        self.runtime_states.setdefault(account.id, AccountRuntimeState()).is_loading = True
        worker_account = replace(account)
        lock = self._account_lock(account.id)
        def fetch():
            with lock:
                if self._quitting or self._refresh_requests.get(worker_account.id) != (request_id, from_group):
                    return None
                return fetch_snapshot(worker_account, verify_live_data)
        try:
            future = self.executor.submit(fetch)
            self._refresh_futures[request_id] = future
            self._submit_future(future, "refresh_result", account.id, from_group, request_id)
        except Exception as error:
            self.events.put(("refresh_result", account.id, from_group, request_id, None, error))

    def _invalidate_account_refresh(self, account_id: UUID) -> None:
        request = self._refresh_requests.pop(account_id, None)
        state = self.runtime_states.get(account_id)
        if state is not None:
            state.is_loading = False
        if request and request[1]:
            self._group_refresh_pending = max(0, self._group_refresh_pending - 1)
            if self._group_refresh_pending == 0:
                self.is_refreshing_all = False
                self._flush_group_refresh_updates()

    def start_or_cancel_add_account(self) -> None:
        if self.is_adding_account:
            self.cancel_add_account()
        else:
            self.start_add_account()

    def start_add_account(self) -> None:
        if self._quitting or self.is_adding_account:
            return
        if self._desktop_restart_busy or self._pending_switch_account_id is not None:
            self.status_message = "Wait for the account switch to finish before signing in."
            self._render()
            return
        if self._account_cleanup_count:
            self.status_message = "Finishing account removal; try again in a moment."
            self._render()
            return
        if self.reauthenticating_account_id is not None:
            self.status_message = "Finish the current sign-in before adding another account."
            self._render()
            return
        request_id = self._next_operation_id()
        self._add_request_id = request_id
        self.is_adding_account = True
        self.status_message = "Complete or cancel the Codex sign-in flow in your browser."
        handle = self._add_handle = ManagedLoginProcess()
        def authenticate():
            if self._quitting or request_id in self._cancelled_add_requests:
                raise CodexAccountManagerError("Account setup cancelled.")
            return self.account_manager.add_managed_account(handle)
        try:
            self._submit_future(self.executor.submit(authenticate), "add_account_result", request_id)
        except Exception as error:
            self.events.put(("add_account_result", request_id, None, error))
        self._render()

    def cancel_add_account(self) -> None:
        if not self.is_adding_account or self._add_handle is None:
            return
        if self._add_request_id is not None:
            self._cancelled_add_requests.add(self._add_request_id)
        self.status_message = "Cancelling account setup."
        self._cancel_login_in_background(self._add_handle)
        self._render()

    def _cancel_login_in_background(self, handle: ManagedLoginProcess) -> None:
        # Process termination can wait; never block Tk or queue it behind a login.
        threading.Thread(target=handle.cancel, name="codexcontrol-cancel", daemon=True).start()

    def reauthenticate(self, account: StoredAccount) -> None:
        if self._quitting or self.reauthenticating_account_id is not None:
            return
        if self._desktop_restart_busy or self._pending_switch_account_id is not None:
            self.status_message = "Wait for the account switch to finish before signing in."
            self._render()
            return
        if not any(candidate.id == account.id for candidate in self.accounts):
            return
        if self.is_adding_account:
            self.status_message = "Finish or cancel account setup before signing in again."
            self._render()
            return
        self._invalidate_account_refresh(account.id)
        self._mark_runtime_dirty()
        request_id = self._next_operation_id()
        self._reauth_request_id = request_id
        self.reauthenticating_account_id = account.id
        self.status_message = f"Waiting for {account.display_name} to sign in again."
        handle = self._reauth_handle = ManagedLoginProcess()
        worker_account = replace(account)
        lock = self._account_lock(account.id)
        def authenticate():
            with lock:
                if self._quitting or self._reauth_request_id != request_id:
                    raise CodexAccountManagerError("Reauthentication cancelled.")
                return self.account_manager.reauthenticate(worker_account, handle)
        try:
            self._submit_future(self.executor.submit(authenticate), "reauth_result", account.id, request_id)
        except Exception as error:
            self.events.put(("reauth_result", account.id, request_id, None, error))
        self._render()

    def update_nickname(self, account_id: UUID) -> None:
        account = next((candidate for candidate in self.accounts if candidate.id == account_id), None)
        if account is None:
            return

        draft = self.nickname_drafts.get(account_id, "").strip()
        account.nickname = draft or None
        self.nickname_drafts[account_id] = draft
        account.updated_at = utc_now()
        self._mark_accounts_dirty()
        self._persist_accounts_silently()
        self._render()

    def remove_account(self, account: StoredAccount) -> None:
        if self._desktop_restart_busy:
            self.status_message = "Wait for Codex to finish restarting before removing an account."
            self._render()
            return
        if self._quitting or not any(candidate.id == account.id for candidate in self.accounts):
            return
        confirmed = messagebox.askyesno(
            "Remove Account", f"{account.display_name} will be removed from CodexControl.", parent=self.root,
        )
        if not confirmed:
            return
        removed_identity = RemovedAccountIdentity.from_account(account)
        removed_ids = {
            candidate.id for candidate in self.accounts
            if candidate.id == account.id or removed_identity.matches(candidate)
        }
        removed_accounts = [candidate for candidate in self.removed_accounts if not candidate.matches(account)]
        removed_accounts.append(removed_identity)
        retained = [candidate for candidate in self.accounts if candidate.id not in removed_ids]
        # Commit the tombstone before removing files, so failed persistence cannot
        # resurrect a deleted account during the next discovery.
        try:
            self.account_store.save_accounts(retained, removed_accounts)
        except Exception as error:
            self.status_message = f"Account could not be removed: {error}"
            self._render()
            return
        self.accounts, self.removed_accounts = retained, removed_accounts
        if self._pending_switch_account_id in removed_ids:
            self._pending_switch_account_id = None
        self._token_context_revision += 1
        if self.reauthenticating_account_id in removed_ids:
            self._reauth_request_id = None
            self.reauthenticating_account_id = None
            if self._reauth_handle is not None:
                self._cancel_login_in_background(self._reauth_handle)
                self._reauth_handle = None
        for account_id in removed_ids:
            self._invalidate_account_refresh(account_id)
            self.token_usage_states.pop(account_id, None)
            self.runtime_states.pop(account_id, None)
            self.nickname_drafts.pop(account_id, None)
        self._mark_accounts_dirty()
        self._mark_runtime_dirty()
        self._persist_snapshots_silently()
        self._ensure_selection()
        self.status_message = f"{account.display_name} removed."
        worker_account = replace(account)
        locks = [self._account_lock(account_id) for account_id in sorted(removed_ids, key=str)]
        def cleanup():
            from contextlib import ExitStack
            with ExitStack() as stack:
                for lock in locks:
                    stack.enter_context(lock)
                for account_id in removed_ids:
                    self.token_tracker.remove_account(account_id)
                self.account_manager.remove_managed_files_if_owned(worker_account)
        try:
            self._account_cleanup_count += 1
            self._submit_future(self.executor.submit(cleanup), "remove_account_result", account.display_name)
        except Exception as error:
            self._account_cleanup_count = max(0, self._account_cleanup_count - 1)
            self.status_message = f"Account removed; local files could not be cleaned up: {error}"
        self._render()

    def switch_account(self, account: StoredAccount) -> None:
        if self._quitting or self._desktop_restart_busy or self._pending_switch_account_id is not None:
            return
        if self.is_adding_account or self.reauthenticating_account_id is not None:
            self.status_message = "Finish or cancel the current sign-in before switching accounts."
            self._render()
            return
        if account.id in AccountIdentityPresentation(self.accounts).duplicate_ids:
            self.status_message = "Duplicate login; reauthenticate before switching."
            self._render()
            return
        if self._is_active_account(account):
            self.status_message = f"{account.display_name} is already the active Codex account."
            self._render()
            return
        if not any(candidate.id == account.id for candidate in self.accounts):
            return
        if self._refresh_requests or any(not future.done() for future in self._refresh_futures.values()):
            # A quota request can refresh auth.json. Wait for its worker, not
            # merely its loading badge, before writing the selected identity.
            self._pending_switch_account_id = account.id
            self.status_message = "Waiting for account refresh before switching…"
            self._render()
            return

        try:
            self.token_usage_states = self.token_tracker.scan(self._active_account_id())
            result = self.account_manager.switch_active_account(account, self.accounts)
            if result.materialized_account is not None:
                self._replace_or_append_account(result.materialized_account)
            self._refresh_active_identity()
            self._load_initial_state()
            self.token_usage_states = self.token_tracker.scan(self._active_account_id())
            self.status_message = (
                f"Active account switched to {account.display_name}. "
                "Restarting Codex Desktop to apply the new session."
            )
            self._render()
            if self._restart_desktop_job is not None:
                try:
                    self.root.after_cancel(self._restart_desktop_job)
                except tk.TclError:
                    pass
            self._desktop_restart_busy = True
            self._restart_desktop_job = self.root.after(
                250,
                lambda result=result: self._restart_codex_desktop(result),
            )
        except CodexAccountManagerError as error:
            self.status_message = str(error)
            self._render()

    def _continue_pending_switch(self) -> None:
        account_id = self._pending_switch_account_id
        if account_id is None or self._quitting or self._desktop_restart_busy:
            return
        if self._refresh_requests or any(not future.done() for future in self._refresh_futures.values()):
            return
        self._pending_switch_account_id = None
        account = next((candidate for candidate in self.accounts if candidate.id == account_id), None)
        if account is None:
            self.status_message = "Account switch cancelled: the selected account was removed."
            self._render()
            return
        # Reuse the normal checks for duplicate/current identity and sign-in
        # conflicts after all old workers have finished touching credentials.
        self.switch_account(account)

    def _restart_codex_desktop(self, result: Any = None) -> None:
        self._restart_desktop_job = None
        try:
            # Keep the tray process alive while Codex Desktop is restarted, but
            # remove the dashboard from the foreground so the switch feels like
            # one continuous action.
            self.hide_window()
            self._desktop_restart_process = restart_codex_desktop(
                backup_destination=Path(result.desktop_session_backup_path)
                if result and result.desktop_session_backup_path
                else None,
                restore_source=Path(result.desktop_session_restore_path)
                if result and result.desktop_session_restore_path and result.desktop_session_restore_exists
                else None,
                target_auth_path=Path(result.target_auth_path) if result and result.target_auth_path else None,
                ambient_auth_path=Path(result.ambient_auth_path) if result and result.ambient_auth_path else None,
            )
            self._desktop_restart_started = time.monotonic()
            self._restart_status_job = self.root.after(400, self._check_desktop_restart)
        except CodexDesktopControlError as error:
            self._desktop_restart_busy = False
            self.status_message = str(error)
            self.show_window()
            self._render()

    def _check_desktop_restart(self) -> None:
        self._restart_status_job = None
        status = {}
        try:
            status = json.loads(RESTART_STATUS_PATH.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            pass
        state = status.get("state")
        if state == "complete":
            self._desktop_restart_busy = False
            self.status_message = "Codex Desktop restarted with the selected account."
            self._refresh_active_identity()
            self._render()
            return
        process = self._desktop_restart_process
        if state == "failed" or (process and process.poll() is not None) or time.monotonic() - self._desktop_restart_started > 60:
            self._desktop_restart_busy = False
            detail = status.get("detail") if state == "failed" else "The background restart did not complete."
            self.status_message = f"Codex Desktop restart failed: {detail}"
            self.show_window()
            self._render()
            return
        if not self._quitting:
            self._restart_status_job = self.root.after(400, self._check_desktop_restart)

    def open_folder(self, account: StoredAccount) -> None:
        try:
            os.startfile(account.codex_home_path)
        except OSError as error:
            self.status_message = f"Could not open account folder: {error}"
            self._render()

    def _report_ui_error(self, exception, value, traceback) -> None:
        # A windowed build has no stderr console. Keep failures inspectable and
        # let later actions continue instead of losing the callback silently.
        try:
            APP_SUPPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)
            logger = logging.getLogger("codexcontrol.ui")
            if not logger.handlers:
                handler = RotatingFileHandler(APP_SUPPORT_DIRECTORY / "ui-errors.log", maxBytes=256_000, backupCount=1, encoding="utf-8")
                handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
                logger.addHandler(handler)
                logger.propagate = False
            logger.error("Interface callback failed", exc_info=(exception, value, traceback))
        except Exception:
            pass
        self.status_message = "An interface update failed. Please retry the action."
        if hasattr(self, "notice_label") and not self._quitting:
            try:
                self.notice_label.configure(text=self.status_message)
                self.notice_tip.set_text(self.status_message)
                self.notice.pack(fill="x", pady=(0, 12), before=self.list_shell)
            except tk.TclError:
                pass

    def _configure_styles(self) -> None:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")



    def _setup_tray_icon(self) -> None:
        self.tray_icon = None
        # Pystray runs on another thread. Only enqueue; Tk is main-thread-only.
        def action(name):
            return lambda icon, item: self.events.put(("tray_action", name))
        menu = pystray.Menu(
            pystray.MenuItem("Show Control Panel", action("show"), default=True, visible=False),
            pystray.MenuItem("Show Control Panel", action("show")),
            pystray.MenuItem("Hide Control Panel", action("hide")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Refresh All", action("refresh")),
            pystray.MenuItem("Add Account", action("add")),
            pystray.MenuItem("Quit", action("quit")),
        )
        self.tray_icon = pystray.Icon("CodexControl", self._create_icon_image("neutral", 64), "CodexControl", menu)
        try:
            self.tray_icon.run_detached()
        except Exception as error:
            self.tray_icon = None
            self.status_message = f"Tray unavailable: {error}"

    def _set_window_icon(self) -> None:
        self.window_icon_images = [
            ImageTk.PhotoImage(self._create_icon_image("neutral", size))
            for size in (16, 24, 32, 48, 64)
        ]
        self.root.iconphoto(True, *self.window_icon_images)

    def _toggle_window(self) -> None:
        if self.root.state() == "withdrawn":
            self.show_window()
        else:
            self.hide_window()

    def _load_initial_state(self) -> None:
        previous_accounts = list(self.accounts)
        previous_states = dict(self.runtime_states)
        fallback_accounts = previous_accounts
        self._account_store_read_failed = True
        self._refresh_requests.clear()
        self.is_refreshing_all = False
        self._group_refresh_pending = 0
        self._token_context_revision += 1
        try:
            loaded_accounts, removed_accounts = self.account_store.load_account_list()
            self._account_store_read_failed = False
            self.removed_accounts = removed_accounts
            loaded_accounts = [account for account in loaded_accounts if not self._is_removed(account)]
            fallback_accounts = loaded_accounts
            stored_accounts = [account for account in loaded_accounts if account.source is not StoredAccountSource.AMBIENT]
            discovered_accounts = self.account_manager.discover_managed_accounts(loaded_accounts)
            ambient_account = self.account_manager.discover_ambient_account(loaded_accounts)
            incoming_accounts = list(discovered_accounts)
            if ambient_account is not None:
                incoming_accounts.insert(0, ambient_account)
            incoming_accounts = [account for account in incoming_accounts if not self._is_removed(account)]
            self.accounts = self.account_store.merge(stored_accounts, incoming_accounts)
            if self.accounts != loaded_accounts:
                self._persist_accounts_silently()
        except Exception as error:
            self.status_message = f"Accounts could not be loaded: {error}"
            self.accounts = fallback_accounts
        valid_ids = {account.id for account in self.accounts}
        try:
            persisted = self.snapshot_store.load()
        except Exception as error:
            self.status_message = f"Saved snapshots could not be loaded: {error}"
            persisted = {}
        self.runtime_states = {}
        for account_id in valid_ids:
            old_state = previous_states.get(account_id)
            saved = persisted.get(account_id)
            if old_state is not None and old_state.snapshot is not None and (
                saved is None or old_state.snapshot.updated_at >= saved.updated_at
            ):
                old_state.is_loading = False
                self.runtime_states[account_id] = old_state
            else:
                self.runtime_states[account_id] = AccountRuntimeState(snapshot=saved)
        self.nickname_drafts = {account.id: account.nickname or "" for account in self.accounts}
        self._mark_accounts_dirty()
        self._mark_runtime_dirty()
        self._ensure_selection()
        self._refresh_active_identity()

    def _submit_future(self, future: Future[Any], event_name: str, *metadata: Any) -> None:
        self._pending_futures.add(future)
        def callback(completed: Future[Any]) -> None:
            self._pending_futures.discard(completed)
            if self._quitting:
                return
            try:
                result = completed.result()
                self.events.put((event_name, *metadata, result, None))
            except Exception as error:
                self.events.put((event_name, *metadata, None, error))
        future.add_done_callback(callback)

    def _process_event_queue(self) -> None:
        self._queue_poll_job = None
        if self._quitting:
            return
        try:
            for _ in range(100):
                try:
                    event = self.events.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._dispatch_event(event)
                except Exception as error:
                    # One bad result must not disable every later refresh.
                    self.status_message = f"An update could not be applied: {error}"
                    self._render()
                if self._quitting:
                    break
        finally:
            if not self._quitting:
                self._queue_poll_job = self.root.after(self.QUEUE_POLL_MS, self._process_event_queue)

    def _dispatch_event(self, event: tuple[Any, ...]) -> None:
        name = event[0]
        if name == "tray_action":
            actions = {"show": self.show_window, "hide": self.hide_window, "refresh": self.refresh_all,
                       "add": self.start_or_cancel_add_account, "quit": self.quit}
            action = actions.get(event[1])
            if action is not None:
                action()
        elif name == "refresh_result":
            _, account_id, from_group, request_id, snapshot, error = event
            try:
                self._apply_refresh_result(account_id, from_group, snapshot, error, request_id)
            finally:
                self._refresh_futures.pop(request_id, None)
                self._continue_pending_switch()
        elif name in ("token_result", "token_local_result"):
            _, request_id, revision, result, error = event
            if request_id != self._token_request_id:
                return
            if name == "token_result":
                self._token_busy = False
            if revision != self._token_context_revision:
                return
            if error is None and result is not None:
                snapshots, statuses = result
                valid_ids = {account.id for account in self.accounts}
                self.token_usage_states = {key: value for key, value in snapshots.items() if key in valid_ids}
                if statuses is not None:
                    self.remote_token_statuses = statuses
            elif error is not None:
                self.status_message = f"Token statistics could not be updated: {error}"
            self._render()
        elif name == "add_account_result":
            _, request_id, account, error = event
            self._apply_add_account_result(account, error, request_id)
        elif name == "reauth_result":
            _, account_id, request_id, account, error = event
            self._apply_reauth_result(account_id, account, error, request_id)
        elif name == "remove_account_result":
            _, display_name, _, error = event
            self._account_cleanup_count = max(0, self._account_cleanup_count - 1)
            if error is not None:
                self.status_message = f"{display_name} removed; some local files could not be cleaned up: {error}"
                self._render()

    def _apply_refresh_result(
        self, account_id: UUID, from_group: bool,
        snapshot: AccountUsageSnapshot | None, error: Exception | None,
        request_id: int | None = None,
    ) -> None:
        if self._quitting:
            return
        request = self._refresh_requests.get(account_id)
        if request is None or (request_id is not None and request[0] != request_id):
            return
        self._refresh_requests.pop(account_id, None)
        from_group = request[1]
        current = next((account for account in self.accounts if account.id == account_id), None)
        if current is not None:
            state = self.runtime_states.setdefault(account_id, AccountRuntimeState())
            state.is_loading = False
            if snapshot is not None:
                state.snapshot = snapshot
                state.error_message = None
                self._update_account_metadata(account_id, snapshot)
            else:
                if not self._should_preserve_snapshot_after(error):
                    state.snapshot = None
                state.error_message = str(error) if error else "Unknown refresh error."
            self._mark_runtime_dirty()
        if from_group:
            self._group_refresh_pending = max(0, self._group_refresh_pending - 1)
            self._group_refresh_flush_pending = True
            if self._group_refresh_pending == 0:
                self.is_refreshing_all = False
                self._flush_group_refresh_updates()
            else:
                self._schedule_group_refresh_flush()
        else:
            self._persist_snapshots_silently()
            self._render()

    def _should_preserve_snapshot_after(self, error: Exception | None) -> bool:
        if isinstance(error, CodexApiError) and error.preserve_snapshot:
            return True
        message = str(error).lower() if error else ""
        authentication_failure = any(part in message for part in (
            "unauthorized", "sign in again", "no `auth.json`", "required token fields are missing",
        ))
        # Keep the last verified quota through offline, timeout or malformed
        # responses. The error remains visible alongside that cached snapshot.
        return not authentication_failure

    def _apply_add_account_result(
        self, account: StoredAccount | None, error: Exception | None, request_id: int | None = None,
    ) -> None:
        if self._quitting:
            return
        if request_id is not None and request_id != self._add_request_id:
            return
        cancelled = request_id in self._cancelled_add_requests
        self._cancelled_add_requests.discard(request_id)
        self.is_adding_account = False
        self._add_handle = None
        self._add_request_id = None
        if cancelled:
            if account is not None:
                # Only this newly created home belongs to the cancelled flow.
                # Identity-wide cleanup could erase an existing duplicate login.
                target = Path(account.codex_home_path).resolve()
                managed_root = MANAGED_HOMES_DIRECTORY.resolve()
                if target != managed_root and target.is_relative_to(managed_root):
                    self._account_cleanup_count += 1
                    try:
                        self._submit_future(self.executor.submit(shutil.rmtree, target),
                                            "remove_account_result", account.display_name)
                    except Exception:
                        self._account_cleanup_count -= 1
                        raise
            self.status_message = "Account setup cancelled."
            self._render()
            return
        if account is not None:
            self._restore_removed_account(account)
            self.accounts = self.account_store.merge(self.accounts, [account])
            self._mark_accounts_dirty()
            self._token_context_revision += 1
            matched = next((candidate for candidate in self.accounts if candidate.matches(account)), account)
            # Adding an existing identity may replace its credentials/home. A
            # request using the old home must not overwrite this fresh login.
            self._invalidate_account_refresh(matched.id)
            self.selected_account_id = matched.id
            self.nickname_drafts[matched.id] = matched.nickname or ""
            self.status_message = f"{matched.display_name} added."
            self._persist_accounts_silently()
            self.refresh_account(matched)
            self._render()
        else:
            self.status_message = str(error) if error else "Account setup failed."
            self._render()

    def _apply_reauth_result(
        self, original_account_id: UUID, account: StoredAccount | None,
        error: Exception | None, request_id: int | None = None,
    ) -> None:
        if self._quitting:
            return
        if request_id is not None and request_id != self._reauth_request_id:
            return
        self.reauthenticating_account_id = None
        self._reauth_handle = None
        self._reauth_request_id = None
        current = next((candidate for candidate in self.accounts if candidate.id == original_account_id), None)
        if current is None:
            return
        if account is not None:
            # Reauthentication can change identity. Preserve the same UI slot
            # instead of adding a second object with the same UUID.
            account.nickname = current.nickname
            self.accounts = [account if candidate.id == original_account_id else candidate for candidate in self.accounts]
            self._restore_removed_account(account)
            self._mark_accounts_dirty()
            self._token_context_revision += 1
            self.runtime_states[original_account_id] = AccountRuntimeState()
            self._mark_runtime_dirty()
            self.status_message = f"{account.display_name} reauthenticated."
            self._persist_accounts_silently()
            self._persist_snapshots_silently()
            self.refresh_account(account)
            return
        self.status_message = str(error) if error else "Reauthentication failed."
        self._render()

    def _update_account_metadata(self, account_id: UUID, snapshot: AccountUsageSnapshot) -> None:
        account = next((candidate for candidate in self.accounts if candidate.id == account_id), None)
        if account is None:
            return

        did_change = False
        normalized_email = snapshot.email.strip().lower() if snapshot.email else None
        if normalized_email and account.email_hint != normalized_email:
            account.email_hint = normalized_email
            did_change = True

        if snapshot.provider_account_id and account.provider_account_id != snapshot.provider_account_id:
            account.provider_account_id = snapshot.provider_account_id
            did_change = True

        if did_change:
            self._mark_accounts_dirty()
            self._persist_accounts_silently()

    def _persist_accounts_silently(self) -> None:
        if getattr(self, "_account_store_read_failed", False):
            self.status_message = "Account storage could not be read; the existing file has been preserved."
            return
        try:
            self.account_store.save_accounts(self.accounts, self.removed_accounts)
        except Exception as error:
            self.status_message = str(error)

    def _persist_snapshots_silently(self) -> None:
        valid_ids = {account.id for account in self.accounts}
        snapshots = {
            account_id: state.snapshot for account_id, state in self.runtime_states.items()
            if state.snapshot is not None and account_id in valid_ids
        }
        try:
            self.snapshot_store.save(snapshots)
        except Exception as error:
            self.status_message = f"Snapshots could not be saved: {error}"

    def _schedule_group_refresh_flush(self) -> None:
        if self._group_refresh_flush_job is not None:
            return
        self._group_refresh_flush_job = self.root.after(
            self.GROUP_REFRESH_FLUSH_MS,
            self._flush_group_refresh_updates,
        )

    def _flush_group_refresh_updates(self) -> None:
        scheduled_job = self._group_refresh_flush_job
        self._group_refresh_flush_job = None
        if scheduled_job is not None:
            try:
                self.root.after_cancel(scheduled_job)
            except tk.TclError:
                pass

        if not self._group_refresh_flush_pending:
            return

        self._group_refresh_flush_pending = False
        self._persist_snapshots_silently()
        self._render()

    def _ensure_selection(self) -> None:
        valid_ids = {account.id for account in self.accounts}
        if self.selected_account_id in valid_ids:
            return
        presentation = self._build_presentation_state()
        if len(presentation.filtered_accounts) == 1:
            self.selected_account_id = presentation.filtered_accounts[0].id
        else:
            self.selected_account_id = None

    def _refresh_active_identity(self) -> None:
        previous_id = self._active_account_id()
        try:
            self.active_identity = self.account_manager.load_active_identity()
        except Exception as error:
            self.status_message = f"Active account could not be read: {error}"
            return
        if previous_id != self._active_account_id():
            self._token_context_revision += 1

    def _is_removed(self, account: StoredAccount) -> bool:
        return any(removed.matches(account) for removed in self.removed_accounts)

    def _restore_removed_account(self, account: StoredAccount) -> None:
        self.removed_accounts = [removed for removed in self.removed_accounts if not removed.matches(account)]

    def _requires_reauthentication(self, account_id: UUID) -> bool:
        state = self.runtime_states.get(account_id)
        if state is None or not state.error_message:
            return False

        message = state.error_message.lower()
        return "refresh token" in message and "sign in again" in message

    def _replace_or_append_account(self, account: StoredAccount) -> None:
        replaced = False
        for index, existing in enumerate(self.accounts):
            if existing.id == account.id or existing.matches(account):
                self.accounts[index] = account
                replaced = True
                break
        if not replaced:
            self.accounts.append(account)
        self._mark_accounts_dirty()
        self._persist_accounts_silently()

    def _is_active_account(self, account: StoredAccount) -> bool:
        return account.id == self._active_account_id()

    def _can_switch_account(self, account: StoredAccount) -> bool:
        if self._desktop_restart_busy or self._pending_switch_account_id is not None or self.is_adding_account or self.reauthenticating_account_id is not None:
            return False
        if self._is_active_account(account) or account.id in AccountIdentityPresentation(self.accounts).duplicate_ids:
            return False
        return (Path(account.codex_home_path) / "auth.json").exists()

    def _auto_refresh_tick(self) -> None:
        self._auto_refresh_job = None
        if not self._quitting:
            self.refresh_all()
            self._auto_refresh_job = self.root.after(self.AUTO_REFRESH_MS, self._auto_refresh_tick)

    @property
    def filtered_accounts(self) -> list[StoredAccount]:
        return self._build_presentation_state().filtered_accounts

    @property
    def account_count(self) -> int:
        return self._build_presentation_state().account_count

    @property
    def low_quota_count(self) -> int:
        return self._build_presentation_state().low_quota_count

    @property
    def usable_quota_count(self) -> int:
        return self._build_presentation_state().usable_quota_count

    @property
    def menu_bar_quota_state(self) -> str:
        return self._build_presentation_state().menu_bar_quota_state

    def _render(self) -> None:
        if self._quitting or self._render_job is not None:
            return
        try:
            self._render_job = self.root.after_idle(self._render_now)
        except tk.TclError:
            self._render_job = None



    def _build_metric_tile(
        self,
        parent: tk.Widget,
        label: str,
        value: str,
        icon: str,
        tone: str,
    ) -> tuple[tk.Frame, tk.Label]:
        tile = tk.Frame(
            parent,
            bg=self.palette["panel"],
            highlightthickness=1,
            highlightbackground=self.palette["hairline"],
            padx=10,
            pady=9,
        )

        top = tk.Frame(tile, bg=self.palette["panel"])
        top.pack(fill="x")

        badge = tk.Frame(
            top,
            bg=self.palette["panel_alt"],
            highlightthickness=1,
            highlightbackground=self.palette["hairline"],
            width=26,
            height=26,
        )
        badge.pack(side="left")
        badge.pack_propagate(False)

        tk.Label(
            badge,
            text=icon,
            bg=self.palette["panel_alt"],
            fg=tone,
            font=self.fonts["icon_small"],
        ).pack(expand=True)

        tk.Label(
            top,
            text=label,
            bg=self.palette["panel"],
            fg=self.palette["muted"],
            font=self.fonts["caption"],
        ).pack(side="left", padx=(8, 0))

        value_label = tk.Label(
            tile,
            text=value,
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=self.fonts["metric"],
        )
        value_label.pack(anchor="w", pady=(8, 0))
        return tile, value_label


    def _build_card_row_specs(self, accounts: list[StoredAccount]) -> list[tuple[list[StoredAccount], bool]]:
        columns = self._cards_column_count()
        pending: list[StoredAccount] = []
        rows: list[tuple[list[StoredAccount], bool]] = []

        for account in accounts:
            pending.append(account)
            if len(pending) == columns:
                rows.append((pending, False))
                pending = []

        if pending:
            rows.append((pending, False))
        return rows

    def _render_card_rows_chunk(
        self,
        row_specs: list[tuple[list[StoredAccount], bool]],
        start: int,
        token: int,
    ) -> None:
        if token != self._cards_render_token:
            return

        end = min(start + self.CARD_RENDER_BATCH_ROWS, len(row_specs))
        for accounts, span_all in row_specs[start:end]:
            self._render_card_row(accounts, span_all)

        if end >= len(row_specs):
            self._cards_render_job = None
            self._schedule_cards_commit()
            return

        self._cards_render_job = self.root.after(
            1,
            lambda next_start=end, next_token=token: self._render_card_rows_chunk(
                row_specs,
                next_start,
                next_token,
            )
        )

    def _cancel_cards_render_job(self) -> None:
        if self._cards_render_job is None:
            return
        try:
            self.root.after_cancel(self._cards_render_job)
        except tk.TclError:
            pass
        self._cards_render_job = None

    def _render_card_row(self, accounts: list[StoredAccount], span_all: bool) -> None:
        row = tk.Frame(self.cards_frame, bg=self.palette["shell"])
        row.pack(fill="x", pady=(0, 8))

        if span_all:
            card = self._build_account_card(
                row,
                accounts[0],
                width_hint=self._card_width(self._cards_column_count()),
            )
            card.pack(fill="x")
            return

        row_gap = self._card_gap()
        row_count = len(accounts)
        for index in range(row_count):
            row.columnconfigure(index, weight=1, uniform='account_cards')
        for index, account in enumerate(accounts):
            span = self._cards_column_count() if row_count == 1 else 1
            card = self._build_account_card(
                row,
                account,
                width_hint=self._card_width(span),
            )
            card.grid(row=0, column=index, sticky='new',
                      padx=(0 if index == 0 else row_gap // 2,
                            0 if index == row_count - 1 else row_gap // 2))



    def _active_account_id(self):
        return AccountIdentityPresentation(self.accounts).active_id(self.active_identity)

    def _token_tick(self):
        self._token_job = None
        if self._quitting:
            return
        try:
            if not self._token_busy:
                self._refresh_active_identity()
                active_id = self._active_account_id()
                accounts = [replace(account) for account in self.accounts]
                revision = self._token_context_revision
                request_id = self._next_operation_id()
                self._token_request_id = request_id
                self._token_busy = True
                def collect():
                    local = self.token_tracker.start(active_id)
                    self.events.put(("token_local_result", request_id, revision, (local, None), None))
                    if self._quitting or revision != self._token_context_revision:
                        return None
                    statuses = self.remote_mirror.sync(accounts, active_id)
                    if self._quitting or revision != self._token_context_revision:
                        return None
                    return self.token_tracker.scan(active_id), statuses
                self._submit_future(self.executor.submit(collect), "token_result", request_id, revision)
        except Exception as error:
            self._token_busy = False
            self.status_message = f"Token statistics could not be updated: {error}"
            self._render()
        finally:
            if not self._quitting:
                self._token_job = self.root.after(30000, self._token_tick)




    def _render_action_buttons(
        self,
        parent: tk.Widget,
        button_specs: list[tuple[str, Callable[[], None], str, str | None]],
        width_hint: int,
    ) -> None:
        max_per_row = 2 if width_hint < 370 else 3 if width_hint < 560 else 5
        for start in range(0, len(button_specs), max_per_row):
            row = tk.Frame(parent, bg=parent.cget("bg"))
            row.pack(fill="x", pady=(0, 6 if start + max_per_row < len(button_specs) else 0))
            current = button_specs[start:start + max_per_row]
            for index, (text, command, kind, icon) in enumerate(current):
                button = self._make_button(row, text, command, kind, icon=icon)
                button.pack(side="left")
                if index < len(current) - 1:
                    tk.Frame(row, bg=parent.cget("bg"), width=6).pack(side="left")



    def _toggle_selection(self, account_id: UUID) -> None:
        self.selected_account_id = None if self.selected_account_id == account_id else account_id
        self._sync_details_selection()
        self._render()

    def _header_status_text(self, presentation: PresentationState) -> str:
        if self.status_message:
            return self.status_message
        if presentation.low_quota_count > 0:
            return f"{presentation.account_count} accounts, {presentation.low_quota_count} critical"
        return f"{presentation.account_count} accounts"

    def _status_text(self, state: AccountRuntimeState) -> str:
        if state.is_loading:
            return "Syncing"
        if state.error_message:
            return "Attention"
        if state.snapshot is None:
            return "Pending"
        if state.snapshot.has_usable_quota_now:
            return "Available"
        if state.snapshot.is_quota_blocked:
            return "Blocked"
        return "Limited"

    def _status_value_text(self, state: AccountRuntimeState) -> str:
        if state.snapshot is not None:
            return f"{state.snapshot.lowest_remaining_percent:.0f}%"
        if state.is_loading:
            return "..."
        return "--"

    def _inline_message(self, state: AccountRuntimeState) -> str:
        if state.is_loading:
            return "Refreshing live quota data..."
        if state.error_message:
            return state.error_message
        if state.snapshot is None:
            return "Waiting for data."
        if state.snapshot.is_quota_blocked:
            return "Quota reached."
        return "No quota data."

    def _status_color(self, state: AccountRuntimeState) -> str:
        if state.error_message:
            return self.palette["warning"]
        if state.is_loading:
            return self.palette["neutral"]
        if state.snapshot is None:
            return self.palette["neutral"]
        return self._quota_color(state.snapshot.lowest_remaining_percent)

    def _quota_color(self, remaining: float) -> str:
        if remaining <= 10:
            return self.palette["danger"]
        if remaining <= 20:
            return self.palette["warning"]
        return self.palette["success"]

    def _make_button(
        self,
        parent: tk.Widget,
        text: str,
        command: Callable[[], None],
        kind: str,
        icon: str | None = None,
    ) -> RoundedButton:
        button = RoundedButton(
            parent,
            text=text,
            command=command,
            theme=self._button_theme(kind),
            font=self._button_font(kind),
            icon=icon,
            icon_font=self.fonts["icon_small"],
            radius=self._button_radius(kind),
            pad_x=self._button_pad(kind)[0],
            pad_y=self._button_pad(kind)[1],
        )
        return button

    def _button_theme(self, kind: str) -> RoundedButtonTheme:
        if kind == "accent":
            return RoundedButtonTheme(
                bg=self.palette["accent_soft"],
                fg=self.palette["accent"],
                hover="#17484d",
                border=self.palette["accent_line"],
                disabled_bg=self.palette["panel_alt"],
                disabled_fg=self.palette["neutral"],
            )
        if kind == "danger_small":
            return RoundedButtonTheme(
                bg="#351d21",
                fg=self.palette["danger"],
                hover="#46262c",
                border="#5a3338",
                disabled_bg=self.palette["panel_alt"],
                disabled_fg=self.palette["neutral"],
            )
        return RoundedButtonTheme(
            bg=self.palette["panel_alt"],
            fg=self.palette["text"],
            hover="#243342",
            border=self.palette["hairline"],
            disabled_bg=self.palette["panel_alt"],
            disabled_fg=self.palette["neutral"],
        )

    def _button_font(self, kind: str) -> tuple[str, int] | tuple[str, int, str]:
        if kind in {"surface_small", "danger_small", "surface_tiny"}:
            return self.fonts["button_small"]
        return self.fonts["button"]

    def _button_radius(self, kind: str) -> int:
        if kind == "surface_tiny":
            return 8
        if kind in {"surface_small", "danger_small"}:
            return 9
        return 10

    def _button_pad(self, kind: str) -> tuple[int, int]:
        if kind == "surface_tiny":
            return 8, 5
        if kind in {"surface_small", "danger_small"}:
            return 10, 6
        return 12, 6



    def _create_icon_image(self, state: str, size: int) -> Image.Image:
        color_map = {
            "available": self.palette["success"],
            "unavailable": self.palette["danger"],
            "unresolved": self.palette["neutral"],
            "empty": self.palette["neutral"],
            "neutral": self.palette["accent"],
        }
        accent = color_map.get(state, self.palette["accent"])
        return build_orbit_dial_icon(
            size,
            accent=accent,
            core="#ddfff2",
            panel_fill=self.palette["panel"],
            panel_fill_end=self.palette["bg"],
            dark=self.palette["dark_icon"],
            border=self.palette["hairline"],
        )

    def _short_path(self, path: str) -> str:
        if len(path) <= 34:
            return path
        return f"...{path[-31:]}"

    def _header_wrap_width(self) -> int:
        return max(220, self.shell.winfo_width() - 24)

    def _cards_available_width(self) -> int:
        return max(320, self.canvas.winfo_width() - 4)

    def _card_gap(self) -> int:
        return 10

    def _cards_column_count(self) -> int:
        return 2 if self._cards_available_width() >= 860 else 1

    def _card_width(self, span: int = 1) -> int:
        columns = self._cards_column_count()
        available = self._cards_available_width()
        if span >= columns:
            return available
        total_gap = self._card_gap() * (columns - 1)
        column_width = max(240, int((available - total_gap) / columns))
        return column_width

    def _card_wrap_width(self, width_hint: int) -> int:
        return max(180, width_hint - 58)

    def _card_progress_width(self, width_hint: int) -> int:
        return max(132, width_hint - 74)

    def _wrap_width(self) -> int:
        return self._card_wrap_width(self._cards_available_width())

    def _progress_width(self) -> int:
        return self._card_progress_width(self._cards_available_width())

    def _is_compact_card_layout(self) -> bool:
        return self.canvas.winfo_width() <= 420

    def _ellipsize(
        self,
        text: str,
        font_spec: tuple[str, int] | tuple[str, int, str],
        max_width: int,
    ) -> str:
        if max_width <= 0:
            return text

        font_key = tuple(font_spec)
        cache_key = (text, font_key, max_width)
        cached = self._ellipsize_cache.get(cache_key)
        if cached is not None:
            return cached

        font = self._font_object(font_spec)
        if font.measure(text) <= max_width:
            result = text
        else:
            ellipsis = "..."
            truncated = text
            while truncated and font.measure(truncated + ellipsis) > max_width:
                truncated = truncated[:-1]
            result = (truncated or text[:1]) + ellipsis

        if len(self._ellipsize_cache) >= self.ELLIPSIS_CACHE_MAX:
            self._ellipsize_cache.clear()
        self._ellipsize_cache[cache_key] = result
        return result

    def _font_object(
        self,
        font_spec: tuple[str, int] | tuple[str, int, str],
    ) -> tkfont.Font:
        key = tuple(font_spec)
        cached = self._font_object_cache.get(key)
        if cached is not None:
            return cached

        font = tkfont.Font(font=font_spec)
        self._font_object_cache[key] = font
        return font

    def _on_root_configure(self, event: tk.Event[Any]) -> None:
        if event.widget is not self.root:
            return

        if event.width == self._last_render_width:
            return

        self._last_render_width = event.width
        self._ellipsize_cache.clear()
        if self._resize_job is not None:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(90, self._render_after_resize)

    def _render_after_resize(self) -> None:
        self._resize_job = None
        self._render()

    def _apply_dark_title_bar(self) -> None:
        apply_window_appearance(self.root, self.palette)

    def _on_cards_configure(self, event: tk.Event[tk.Widget]) -> None:
        if event.widget is self._visible_cards_frame:
            self._update_cards_scrollregion()

    def _update_cards_scrollregion(self) -> None:
        offset = max(0, self.canvas.canvasy(0))
        scene = getattr(self, 'card_scene', None)
        content_height = scene.content_height if scene is not None else self._visible_cards_frame.winfo_reqheight()
        height = max(self.canvas.winfo_height(), content_height, 1)
        self.canvas.configure(scrollregion=(0, 0, max(1, self.canvas.winfo_width()), height))
        self.canvas.yview_moveto(offset / height)

    def _on_canvas_configure(self, event: tk.Event[tk.Widget]) -> None:
        if getattr(self, 'card_scene', None) is not None:
            self._card_signature = None
            self._render()
            return
        self.canvas.itemconfigure(self.cards_window, width=event.width)
        if self._staged_cards_window is not None:
            self.canvas.itemconfigure(self._staged_cards_window, width=event.width)
        elif self._staged_cards_frame is not None:
            self._staged_cards_frame.place_configure(width=event.width)

    def _on_mousewheel(self, event) -> None:
        if event.delta and self.canvas.bbox("all"):
            bounds = self.canvas.bbox("all")
            scene = getattr(self, 'card_scene', None)
            height = max(1, scene.content_height if scene is not None else bounds[3] - bounds[1])
            if height > self.canvas.winfo_height():
                step = -36 if event.delta > 0 else 36
                self.canvas.yview_moveto(self.canvas.yview()[0] + step / height)

    def _bind_click(self, widget: tk.Widget, callback: Callable[[tk.Event[Any]], None]) -> None:
        widget.bind("<Button-1>", callback)

    def _on_search_change(self) -> None:
        self._mark_search_dirty()
        if self._search_render_job is not None:
            try:
                self.root.after_cancel(self._search_render_job)
            except tk.TclError:
                pass
        self._search_render_job = self.root.after(self.SEARCH_RENDER_MS, self._flush_search_render)

    def _flush_search_render(self) -> None:
        self._search_render_job = None
        self._render()

    def _invalidate_presentation_cache(self) -> None:
        self._presentation_cache_key = None
        self._presentation_cache = None

    def _mark_accounts_dirty(self) -> None:
        self._accounts_revision += 1
        self._invalidate_presentation_cache()

    def _mark_runtime_dirty(self) -> None:
        self._runtime_revision += 1
        self._invalidate_presentation_cache()

    def _mark_search_dirty(self) -> None:
        self._search_revision += 1
        self._invalidate_presentation_cache()

    def _build_presentation_state(self) -> PresentationState:
        cache_key = (self._accounts_revision, self._runtime_revision, self._search_revision)
        if self._presentation_cache_key == cache_key and self._presentation_cache is not None:
            return self._presentation_cache

        query = self.search_var.get().strip().casefold()
        filtered: list[tuple[tuple[int, int, float, float, str], StoredAccount]] = []
        low_quota_count = 0
        usable_quota_count = 0
        exhausted_count = 0

        for account in self.accounts:
            snapshot = self.runtime_states.get(account.id, AccountRuntimeState()).snapshot
            if snapshot is not None:
                if snapshot.lowest_remaining_percent <= 20:
                    low_quota_count += 1
                if snapshot.has_usable_quota_now:
                    usable_quota_count += 1
                else:
                    exhausted_count += 1

            if query and not self._matches_search_query(account, query):
                continue

            filtered.append((account_sort_key(account, snapshot), account))

        filtered.sort(key=lambda item: item[0])
        presentation = PresentationState(
            search_query=query,
            filtered_accounts=[account for _, account in filtered],
            account_count=len(self.accounts),
            low_quota_count=low_quota_count,
            usable_quota_count=usable_quota_count,
            exhausted_count=exhausted_count,
        )
        self._presentation_cache_key = cache_key
        self._presentation_cache = presentation
        return presentation

    def _matches_search_query(self, account: StoredAccount, query: str) -> bool:
        return any(
            query in candidate.casefold()
            for candidate in (
                account.display_name,
                account.email_hint or "",
                account.auth_subject or "",
                account.provider_account_id or "",
                account.codex_home_path,
            )
        )


def main(argv: list[str] | None = None) -> None:
    arguments = list(sys.argv[1:] if argv is None else argv)
    start_hidden = any(argument.lower() in {"--hidden", "/hidden"} for argument in arguments)
    app = CodexControlWindowsApp(start_hidden=start_hidden)
    app.run()
