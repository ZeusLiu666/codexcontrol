"""Real Tk layout/interaction regression tests with isolated account fixtures."""
import tkinter as tk
import time
import unittest
from datetime import datetime, timedelta
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch, Mock
from uuid import uuid4

from codexcontrol_windows.app import CodexControlWindowsApp
from fixture_support import isolated_app_dependencies
from codexcontrol_windows.models import StoredAccount, StoredAccountSource, AccountRuntimeState, AccountUsageSnapshot, UsageWindowSnapshot, utc_now
from codexcontrol_windows.token_usage import zero
from codexcontrol_windows.ui_components import ActionButton


def children(widget):
    for child in widget.winfo_children():
        yield child
        yield from children(child)


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.fixture_dependencies = self.enterContext(isolated_app_dependencies())
        self.patches = [
            patch.object(CodexControlWindowsApp, '_setup_tray_icon', lambda app: setattr(app, 'tray_icon', None)),
            patch.object(CodexControlWindowsApp, '_load_initial_state', lambda app: None),
            patch.object(CodexControlWindowsApp, '_apply_dark_title_bar', lambda app: None),
        ]
        for item in self.patches:
            self.enterContext(item)
        self.app = CodexControlWindowsApp()
        self.scene = self.app.card_scene
        self.app.root.title('CodexControl isolated test')
        self.app.root.geometry('520x800+5000+5000')
        self.errors = []
        self.app.root.report_callback_exception = lambda *args: self.errors.append(args)
        for name in ('_initial_refresh_job', '_auto_refresh_job', '_token_job'):
            self.app.root.after_cancel(getattr(self.app, name))
            setattr(self.app, name, None)
        self.temp = TemporaryDirectory()
        now = utc_now()
        self.app.accounts = [StoredAccount(uuid4(), f'Workspace {n}', f'demo{n}@example.com', f'sub{n}', f'team{n}', str(Path(self.temp.name)/str(n)), StoredAccountSource.MANAGED_BY_APP, now, now) for n in range(7)]
        for a in self.app.accounts:
            self.app.runtime_states[a.id] = AccountRuntimeState(AccountUsageSnapshot(a.email_hint, a.provider_account_id, 'plus', True, False, UsageWindowSnapshot(28, now+timedelta(hours=3), 18000), UsageWindowSnapshot(9, now+timedelta(days=4), 604800), None, now))
            usage = zero(); usage.update(totalTokens=120000, inputTokens=90000, outputTokens=30000)
            self.app.token_usage_states[a.id] = dict(today=usage, lastSevenDays=usage, allTime=usage, daily=[dict(date=(datetime.now()-timedelta(days=n)).date().isoformat(), usage=usage) for n in reversed(range(7))])
        self.app.selected_account_id = self.app.accounts[0].id
        self.app._mark_accounts_dirty(); self.app._mark_runtime_dirty()
        self.app._render_now()
        self.pump()
        # First mapping schedules the width-dependent render 90ms later.
        # Wait once more after expensive initial Tk layout has returned.
        self.pump(.25)
        self.assertEqual(set(self.scene.card_bounds), {account.id for account in self.app.accounts})

    def pump(self, seconds=.12):
        end = time.monotonic()+seconds
        while time.monotonic()<end:
            self.app.root.update()
            time.sleep(.003)

    def tearDown(self):
        self.app.quit()
        self.temp.cleanup()
        self.assertFalse(self.errors, self.errors)

    def canvas_texts(self):
        return [self.app.canvas.itemcget(item, 'text') for item in self.app.canvas.find_all()
                if self.app.canvas.type(item) == 'text' and self.app.canvas.itemcget(item, 'state') != 'hidden']

    def test_layout_minimum_normal_wide_and_tooltip(self):
        for size in ('460x620', '520x800', '1040x800'):
            self.app.root.geometry(size); self.pump(.2)
            for left, top, right, bottom in self.scene.card_bounds.values():
                self.assertGreaterEqual(left, 0)
                self.assertLessEqual(right, self.app.canvas.winfo_width()+1)
                self.assertGreater(bottom, top)
            self.assertEqual(self.app.canvas.winfo_children(), [])
            self.assertLessEqual(self.app.canvas.winfo_x()+self.app.canvas.winfo_width(), self.app.list_shell.winfo_width())
        self.app.root.geometry('520x800'); self.pump(.2)
        cells = [region for region in self.scene.regions if len(region.key) > 1 and region.key[1] == 'token']
        self.assertEqual(len(cells), 7)
        self.assertIn('120,000', self.scene.tooltip_for(cells[0].key))
        self.assertIn(str(cells[0].key[2]), self.scene.tooltip_for(cells[0].key))

    def test_search_empty_results_recovery_and_expansion(self):
        self.app.search_var.set('demo2'); self.pump(.2)
        self.assertEqual(1, len(self.app.filtered_accounts))
        self.assertEqual(set(self.scene.card_bounds), {self.app.accounts[2].id})
        self.app.search_var.set('no-such-account'); self.pump(.2)
        self.assertFalse(self.app.filtered_accounts)
        self.assertFalse(self.scene.card_bounds)
        self.app.search_var.set(''); self.pump(.2)
        account = self.app.accounts[1]
        self.app._toggle_selection(account.id); self.pump()
        self.assertEqual(account.id, self.app.selected_account_id)
        self.app._toggle_selection(account.id); self.pump()
        self.assertIsNone(self.app.selected_account_id)

    def test_edit_survives_background_refresh_and_saves(self):
        account = self.app.accounts[0]
        self.app._edit_account(account); self.pump()
        entry = self.scene._entry
        entry.focus_force(); entry.delete(0, 'end'); entry.insert(0, 'My edited name')
        self.app._mark_runtime_dirty(); self.app._render_now(); self.pump()
        self.assertIs(entry, self.scene._entry)
        self.assertEqual('My edited name', entry.get())
        entry.event_generate('<Return>'); self.pump()
        self.assertEqual('My edited name', account.nickname)
        self.app.account_store.save_accounts.assert_called()

    def test_refresh_errors_keep_data_and_action_is_keyboard_accessible(self):
        account = self.app.accounts[0]
        state = self.app.runtime_states[account.id]
        state.error_message='Network temporarily unavailable'
        self.app._mark_runtime_dirty(); self.app._render_now(); self.pump()
        labels = self.canvas_texts()
        self.assertTrue(any('Cached' in text for text in labels), labels)
        self.assertIn('72%', labels)
        command = Mock()
        button = ActionButton(self.app.root, icon='refresh', command=command)
        button.pack(); self.pump(); button.focus_force(); self.pump()
        button.event_generate('<KeyPress-Return>'); button.event_generate('<KeyRelease-Return>'); self.pump()
        command.assert_called_once()
        button.set_enabled(False)
        button.event_generate('<KeyPress-Return>'); button.event_generate('<KeyRelease-Return>'); self.pump()
        command.assert_called_once()
        button.destroy()

    def test_selection_change_while_editing_never_leaves_a_stale_card(self):
        account = self.app.accounts[0]
        self.app._edit_account(account); self.pump()
        entry = self.scene._entry
        entry.focus_force(); entry.delete(0, 'end'); entry.insert(0, 'Unsaved draft')
        self.app._toggle_selection(self.app.accounts[1].id); self.pump()
        self.assertFalse(entry.winfo_exists())
        self.assertIsNone(self.app._editing_account_id)
        self.assertEqual('Unsaved draft', self.app.nickname_drafts[account.id])
        self.assertEqual(self.app.accounts[1].id, self.app.selected_account_id)

    def test_toolbar_actions_reach_the_existing_account_backend(self):
        account = self.app.accounts[0]
        callbacks = {name: Mock() for name in ('refresh_account', 'reauthenticate', 'open_folder', 'remove_account', 'switch_account')}
        for name, callback in callbacks.items():
            self.enterContext(patch.object(self.app, name, callback))
        self.enterContext(patch.object(self.app, '_can_switch_account', return_value=True))
        self.app._mark_runtime_dirty(); self.app._render_now()
        for action, method in (('refresh', 'refresh_account'), ('key', 'reauthenticate'), ('folder', 'open_folder'),
                               ('trash', 'remove_account'), ('switch', 'switch_account')):
            self.scene.invoke((account.id, action))
            callbacks[method].assert_called_once_with(account)

    def test_account_operation_flags_disable_conflicting_canvas_actions(self):
        account = self.app.accounts[0]
        self.app.refresh_account = Mock()
        self.app.reauthenticate = Mock()
        self.app.switch_account = Mock()
        self.app._pending_switch_account_id = self.app.accounts[1].id
        self.app._mark_runtime_dirty(); self.app._render_now()
        for action in ('refresh', 'key'):
            region = next(r for r in self.scene.regions if r.key == (account.id, action))
            self.assertFalse(region.enabled)
            self.scene.invoke(region.key)
        self.scene.invoke((account.id, 'switch'))
        self.app.refresh_account.assert_not_called()
        self.app.reauthenticate.assert_not_called()
        self.app.switch_account.assert_not_called()

    def test_token_tooltip_uses_cell_screen_anchor_and_hides_after_scroll(self):
        token = next(r for r in self.scene.regions if r.key[1] == 'token')
        self.scene.focus_region(token.key)
        rect = self.scene._tooltip_rect()
        self.assertIsNotNone(rect)
        x1, y1, x2, y2 = token.rect
        self.assertEqual(rect, (round(self.app.canvas.winfo_rootx()+x1-self.app.canvas.canvasx(0)),
                                round(self.app.canvas.winfo_rooty()+y1-self.app.canvas.canvasy(0)),
                                round(self.app.canvas.winfo_rootx()+x2-self.app.canvas.canvasx(0)),
                                round(self.app.canvas.winfo_rooty()+y2-self.app.canvas.canvasy(0))))
        self.assertIn('120,000 tokens', self.scene.tooltip_for(token.key))
        self.app.canvas.yview_moveto(1)
        self.pump(.04)
        self.assertIsNone(self.scene.tooltip._job)
        self.assertIsNone(self.scene.tooltip.window)

    def test_rename_escape_and_filter_close_the_only_native_card_editor(self):
        account = self.app.accounts[0]
        original = account.nickname
        self.app._edit_account(account); self.pump(.04)
        entry = self.scene._entry
        self.assertEqual(self.app.canvas.winfo_children(), [entry])
        self.assertEqual(len([item for item in self.app.canvas.find_all() if self.app.canvas.type(item) == 'window']), 1)
        entry.focus_force(); entry.delete(0, 'end'); entry.insert(0, 'Draft retained')
        entry.event_generate('<Escape>'); self.pump(.04)
        self.assertIsNone(self.scene._entry)
        self.assertEqual(account.nickname, original)
        self.assertEqual(self.app.nickname_drafts[account.id], 'Draft retained')
        self.app._edit_account(account); self.pump(.04)
        self.assertEqual(self.scene._entry.get(), 'Draft retained')
        self.app.search_var.set('demo2'); self.pump(.12)
        self.assertIsNone(self.scene._entry)
        self.assertEqual(self.app.canvas.winfo_children(), [])


if __name__=='__main__':
    unittest.main()
