from __future__ import annotations

import queue
import unittest
from concurrent.futures import Future
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from codexcontrol_windows.app import CodexControlWindowsApp
from codexcontrol_windows.codex_api import CodexApiError
from codexcontrol_windows.models import AccountRuntimeState, StoredAccount, StoredAccountSource
from codexcontrol_windows.stores import AccountStore


class ControlledExecutor:
    """Deterministically complete background jobs in any order without I/O."""
    def __init__(self):
        self.jobs = []

    def submit(self, function, *args):
        future = Future()
        self.jobs.append((future, function, args))
        return future

    def run(self, index):
        future, function, args = self.jobs[index]
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(function(*args))
        except Exception as error:
            future.set_exception(error)

    def shutdown(self, **kwargs):
        pass


def account(label="one"):
    now = datetime.now(timezone.utc)
    return StoredAccount(uuid4(), label, label + "@example.test", None, label,
                         "C:/fixture/" + label, StoredAccountSource.MANAGED_BY_APP, now, now)


def make_app(*accounts):
    app = object.__new__(CodexControlWindowsApp)
    app.accounts = list(accounts)
    app.removed_accounts = []
    app.runtime_states = {a.id: AccountRuntimeState() for a in accounts}
    app.nickname_drafts = {}
    app.active_identity = None
    app.selected_account_id = None
    app.status_message = None
    app.is_refreshing_all = app.is_adding_account = False
    app.reauthenticating_account_id = None
    app._quitting = False
    app._operation_sequence = 0
    app._refresh_requests = {}
    app._refresh_futures = {}
    app._pending_switch_account_id = None
    app._account_operation_locks = {}
    app._pending_futures = set()
    app._add_request_id = app._reauth_request_id = None
    app._cancelled_add_requests = set()
    app._account_cleanup_count = 0
    app._token_request_id = None
    app._token_context_revision = 0
    app._group_refresh_pending = 0
    app._group_refresh_flush_job = None
    app._group_refresh_flush_pending = False
    app._initial_refresh_job = None
    app._add_handle = app._reauth_handle = None
    app._token_busy = False
    app._token_job = app._queue_poll_job = None
    app._desktop_restart_busy = False
    app.token_usage_states = {}
    app.remote_token_statuses = []
    app._accounts_revision = app._runtime_revision = app._search_revision = 0
    app._presentation_cache = app._presentation_cache_key = None
    app._render = Mock()
    app._ensure_selection = Mock()
    app._cancel_login_in_background = Mock()
    app.root = Mock()
    app.root.after.return_value = "scheduled"
    app.executor = ControlledExecutor()
    app.events = queue.Queue()
    app.account_store = Mock(spec=AccountStore)
    app.account_store.merge.side_effect = AccountStore().merge
    app.snapshot_store = Mock()
    app.account_manager = Mock()
    app.account_manager.load_active_identity.return_value = None
    app.token_tracker = Mock()
    app.remote_mirror = Mock()
    app.tray_icon = None
    return app


class BackgroundStateTests(unittest.TestCase):
    def test_group_refresh_does_not_duplicate_individual_request(self):
        first, second = account(), account("two")
        app = make_app(first, second)
        app.refresh_account(first)
        first_request = app._refresh_requests[first.id]
        app.refresh_all()
        self.assertEqual(len(app.executor.jobs), 2)
        self.assertEqual(app._refresh_requests[first.id], first_request)
        self.assertEqual(app._group_refresh_pending, 1)
        self.assertTrue(app.runtime_states[first.id].is_loading)
        self.assertGreater(app._runtime_revision, 0)

    def test_removed_account_late_refresh_does_not_resurrect_state(self):
        first = account()
        app = make_app(first)
        app.refresh_all()
        request_id = app._refresh_requests[first.id][0]
        with patch("codexcontrol_windows.app.messagebox.askyesno", return_value=True):
            app.remove_account(first)
        app._apply_refresh_result(first.id, True, Mock(), None, request_id)
        self.assertNotIn(first.id, app.runtime_states)
        self.assertFalse(app.is_refreshing_all)
        self.assertEqual(app._group_refresh_pending, 0)
        self.assertEqual(app.accounts, [])

    def test_old_refresh_cannot_clear_newer_loading_state(self):
        first = account()
        app = make_app(first)
        app.refresh_account(first)
        stale_request = app._refresh_requests[first.id][0]
        app._invalidate_account_refresh(first.id)
        app.refresh_account(first)
        current_request = app._refresh_requests[first.id]
        app._apply_refresh_result(first.id, False, Mock(), None, stale_request)
        self.assertTrue(app.runtime_states[first.id].is_loading)
        self.assertEqual(app._refresh_requests[first.id], current_request)

    def test_failed_submit_clears_loading_when_event_arrives(self):
        first = account()
        app = make_app(first)
        app.executor.submit = Mock(side_effect=RuntimeError("executor closed"))
        app.refresh_all()
        app._process_event_queue()
        self.assertFalse(app.is_refreshing_all)
        self.assertFalse(app.runtime_states[first.id].is_loading)
        self.assertIn("executor closed", app.runtime_states[first.id].error_message)

    def test_offline_keeps_cached_snapshot_but_auth_failure_clears_it(self):
        first = account()
        app = make_app(first)
        cached = Mock()
        app.runtime_states[first.id].snapshot = cached
        app.refresh_account(first)
        request = app._refresh_requests[first.id][0]
        app._apply_refresh_result(first.id, False, None, OSError("offline"), request)
        self.assertIs(app.runtime_states[first.id].snapshot, cached)
        app.refresh_account(first)
        request = app._refresh_requests[first.id][0]
        app._apply_refresh_result(first.id, False, None, CodexApiError("unauthorized"), request)
        self.assertIsNone(app.runtime_states[first.id].snapshot)

    def test_removed_account_late_reauth_does_not_reappear(self):
        first = account()
        app = make_app(first)
        app.reauthenticate(first)
        request = app._reauth_request_id
        with patch("codexcontrol_windows.app.messagebox.askyesno", return_value=True):
            app.remove_account(first)
        app._apply_reauth_result(first.id, first, None, request)
        self.assertEqual(app.accounts, [])
        app._cancel_login_in_background.assert_called_once()

    def test_reauth_identity_change_preserves_slot_and_latest_nickname(self):
        first = account()
        app = make_app(first)
        app.reauthenticate(first)
        request = app._reauth_request_id
        incoming = account("new-identity")
        incoming.id = first.id
        first.nickname = "Renamed while signing in"
        app._apply_reauth_result(first.id, incoming, None, request)
        self.assertEqual(len(app.accounts), 1)
        self.assertEqual(app.accounts[0].provider_account_id, "new-identity")
        self.assertEqual(app.accounts[0].nickname, first.nickname)

    def test_cancel_before_queued_login_does_not_launch_login(self):
        app = make_app()
        app.start_add_account()
        app.cancel_add_account()
        app.executor.run(0)
        app._process_event_queue()
        app.account_manager.add_managed_account.assert_not_called()
        self.assertFalse(app.is_adding_account)
        self.assertEqual(app.status_message, "Account setup cancelled.")

    def test_event_error_does_not_stop_following_events_or_polling(self):
        app = make_app()
        app.show_window = Mock()
        app.events.put(("refresh_result", "malformed"))
        app.events.put(("tray_action", "show"))
        app._process_event_queue()
        app.show_window.assert_called_once()
        app.root.after.assert_called_once()
        self.assertIn("could not be applied", app.status_message)

    def test_quit_tray_event_stops_processing_later_events(self):
        app = make_app()
        app.show_window = Mock()
        app.events.put(("tray_action", "quit"))
        app.events.put(("tray_action", "show"))
        app._process_event_queue()
        app.show_window.assert_not_called()
        app.root.after.assert_not_called()
        app.snapshot_store.save.assert_called_once()
        app.root.destroy.assert_called_once()

    def test_remove_persistence_failure_preserves_account_and_files(self):
        first = account()
        app = make_app(first)
        app.account_store.save_accounts.side_effect = OSError("disk full")
        with patch("codexcontrol_windows.app.messagebox.askyesno", return_value=True):
            app.remove_account(first)
        self.assertEqual(app.accounts, [first])
        self.assertEqual(len(app.executor.jobs), 0)
        self.assertIn("disk full", app.status_message)

    def test_local_token_result_is_available_before_remote_sync(self):
        first = account()
        app = make_app(first)
        app.token_tracker.start.return_value = {first.id: {"today": 12}}
        app.token_tracker.scan.return_value = {first.id: {"today": 15}}
        def sync(*_):
            app._process_event_queue()
            self.assertEqual(app.token_usage_states[first.id]["today"], 12)
            return [{"host": "test", "isAvailable": False}]
        app.remote_mirror.sync.side_effect = sync
        app._token_tick()
        app.executor.run(0)
        app._process_event_queue()
        self.assertEqual(app.token_usage_states[first.id]["today"], 15)
        self.assertFalse(app._token_busy)

    def test_stale_token_result_does_not_replace_current_data(self):
        first = account()
        app = make_app(first)
        app._token_request_id = 7
        app._token_busy = True
        app._token_context_revision = 2
        app.token_usage_states = {first.id: {"today": 30}}
        app.events.put(("token_result", 7, 1, ({first.id: {"today": 1}}, []), None))
        app._process_event_queue()
        self.assertEqual(app.token_usage_states[first.id]["today"], 30)
        self.assertFalse(app._token_busy)

    def test_quit_flushes_debounced_snapshot_and_cancels_login(self):
        first = account()
        app = make_app(first)
        cached = Mock()
        app.runtime_states[first.id].snapshot = cached
        app._group_refresh_flush_pending = True
        app._add_handle = Mock()
        app.quit()
        app.snapshot_store.save.assert_called_once_with({first.id: cached})
        app._cancel_login_in_background.assert_called_once_with(app._add_handle)

    def test_reload_failure_retains_last_in_memory_snapshot(self):
        first = account()
        app = make_app(first)
        cached = SimpleNamespace(updated_at=datetime.now(timezone.utc))
        app.runtime_states[first.id].snapshot = cached
        app.account_store.load_account_list.side_effect = OSError("cannot read")
        app.snapshot_store.load.side_effect = ValueError("bad json")
        app._load_initial_state()
        self.assertEqual(app.accounts, [first])
        self.assertIs(app.runtime_states[first.id].snapshot, cached)

    def test_failed_initial_account_read_is_not_overwritten_on_quit(self):
        app = make_app()
        app.account_store.load_account_list.side_effect = ValueError("bad json")
        app.snapshot_store.load.return_value = {}
        app._load_initial_state()
        app.quit()
        app.account_store.save_accounts.assert_not_called()

    def test_discovery_failure_retains_accounts_loaded_from_disk(self):
        first = account()
        app = make_app()
        app.account_store.load_account_list.return_value = ([first], [])
        app.account_manager.discover_managed_accounts.side_effect = OSError("unavailable directory")
        app.snapshot_store.load.return_value = {}
        app._load_initial_state()
        self.assertEqual(app.accounts, [first])
        self.assertFalse(app._account_store_read_failed)

    def test_adding_existing_identity_replaces_pending_refresh_and_renders(self):
        first = account()
        app = make_app(first)
        app.refresh_account(first)
        stale_request = app._refresh_requests[first.id][0]
        app.start_add_account()
        add_request = app._add_request_id
        incoming = account("one")
        incoming.codex_home_path = "C:/fixture/fresh-login"
        app._render.reset_mock()
        app._apply_add_account_result(incoming, None, add_request)
        current_request = app._refresh_requests[first.id][0]
        self.assertNotEqual(stale_request, current_request)
        self.assertEqual(len(app.accounts), 1)
        self.assertEqual(app.accounts[0].codex_home_path, incoming.codex_home_path)
        app._apply_refresh_result(first.id, False, None, CodexApiError("unauthorized"), stale_request)
        self.assertTrue(app.runtime_states[first.id].is_loading)
        self.assertIsNone(app.runtime_states[first.id].error_message)
        self.assertFalse(app.is_adding_account)
        app._render.assert_called()

    def test_account_switch_during_add_or_reauth_never_touches_auth(self):
        first = account()
        for adding, reauth in ((True, None), (False, first.id)):
            with self.subTest(adding=adding):
                app = make_app(first)
                app.is_adding_account = adding
                app.reauthenticating_account_id = reauth
                self.assertFalse(app._can_switch_account(first))
                app.switch_account(first)
                app.account_manager.switch_active_account.assert_not_called()
                app.token_tracker.scan.assert_not_called()
                self.assertIn("current sign-in", app.status_message)

    def test_new_logins_cannot_overwrite_auth_while_desktop_restarts(self):
        first = account()
        app = make_app(first)
        app._desktop_restart_busy = True
        app.start_add_account()
        app.reauthenticate(first)
        self.assertEqual(app.executor.jobs, [])
        self.assertFalse(app.is_adding_account)
        self.assertIsNone(app.reauthenticating_account_id)
        self.assertIn("switch to finish", app.status_message)

    def test_switch_queues_and_proceeds_only_after_last_refresh_result(self):
        first, second = account(), account("two")
        app = make_app(first, second)
        app.refresh_all()
        app.switch_account(second)
        self.assertEqual(app._pending_switch_account_id, second.id)
        self.assertIn("Waiting for account refresh", app.status_message)
        app.account_manager.switch_active_account.assert_not_called()
        # Observe the continuation without launching any real switch/restart.
        app.switch_account = Mock()
        with patch("codexcontrol_windows.app.fetch_snapshot", side_effect=OSError("offline")):
            app.executor.run(0)
            app._process_event_queue()
            app.switch_account.assert_not_called()
            app.executor.run(1)
            app._process_event_queue()
        app.switch_account.assert_called_once_with(second)
        self.assertIsNone(app._pending_switch_account_id)

    def test_pending_or_running_switch_blocks_new_refreshes_and_logins(self):
        first = account()
        for queued in (True, False):
            with self.subTest(queued=queued):
                app = make_app(first)
                app._pending_switch_account_id = first.id if queued else None
                app._desktop_restart_busy = not queued
                app.refresh_all()
                app.refresh_account(first)
                app.start_add_account()
                app.reauthenticate(first)
                self.assertEqual(app.executor.jobs, [])
                self.assertFalse(app._can_switch_account(first))

    def test_deleting_pending_switch_target_cancels_automatic_switch(self):
        first, second = account(), account("two")
        app = make_app(first, second)
        app.refresh_all()
        app.switch_account(second)
        with patch("codexcontrol_windows.app.messagebox.askyesno", return_value=True):
            app.remove_account(second)
        self.assertIsNone(app._pending_switch_account_id)
        app.switch_account = Mock()
        with patch("codexcontrol_windows.app.fetch_snapshot", side_effect=OSError("offline")):
            app.executor.run(0)
            app.executor.run(1)
            app._process_event_queue()
        app.switch_account.assert_not_called()

    def test_switch_waits_for_invalidated_refresh_worker_not_only_loading_badge(self):
        first = account()
        app = make_app(first)
        app.refresh_account(first)
        request_id = app._refresh_requests[first.id][0]
        future = app._refresh_futures[request_id]
        future.set_running_or_notify_cancel()
        app._invalidate_account_refresh(first.id)
        self.assertFalse(app._refresh_requests)
        app.switch_account(first)
        self.assertEqual(app._pending_switch_account_id, first.id)
        app.account_manager.switch_active_account.assert_not_called()
        app.switch_account = Mock()
        app._continue_pending_switch()
        app.switch_account.assert_not_called()
        future.set_result(None)
        app._process_event_queue()
        app.switch_account.assert_called_once_with(first)

    def test_switch_rechecks_signin_conflict_after_waiting(self):
        first = account()
        app = make_app(first)
        app._pending_switch_account_id = first.id
        app.is_adding_account = True
        app._continue_pending_switch()
        app.account_manager.switch_active_account.assert_not_called()
        self.assertIsNone(app._pending_switch_account_id)
        self.assertIn("current sign-in", app.status_message)


if __name__ == "__main__":
    unittest.main()
