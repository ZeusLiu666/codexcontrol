"""The preview must never persist fixtures through previously imported paths."""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from uuid import uuid4

# Deliberately preload these modules before any preview environment override.
import codexcontrol_windows.app as app_module
import codexcontrol_windows.stores as stores
from codexcontrol_windows.models import StoredAccount, StoredAccountSource, utc_now
from fixture_support import isolated_app_dependencies


class FixtureIsolationTests(unittest.TestCase):
    def test_preimported_real_paths_are_untouched_by_fixture_quit(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            accounts_path = root / 'real-profile' / 'accounts.json'
            snapshots_path = root / 'real-profile' / 'snapshots.json'
            accounts_path.parent.mkdir()
            original = b'{"preserve": "original user state"}'
            accounts_path.write_bytes(original)
            snapshots_path.write_bytes(original)
            # Mirrors diagnose_components -> late APPDATA -> visual_preview.
            with patch.object(stores, 'ACCOUNTS_FILE', accounts_path), patch.object(stores, 'SNAPSHOTS_FILE', snapshots_path):
                with patch.dict(os.environ, {'APPDATA': str(root / 'preview-profile')}):
                    with isolated_app_dependencies() as dependencies:
                        app = app_module.CodexControlWindowsApp.__new__(app_module.CodexControlWindowsApp)
                        app.account_store = app_module.AccountStore()
                        app.snapshot_store = app_module.SnapshotStore()
                        app.account_manager = app_module.CodexAccountManager()
                        app.token_tracker = app_module.TokenUsageTracker()
                        app.remote_mirror = app_module.RemoteTokenUsageMirror()
                        app.root = Mock()
                        app.executor = Mock()
                        app.tray_icon = None
                        app._quitting = False
                        app._add_handle = app._reauth_handle = None
                        app._pending_futures = set()
                        now = utc_now()
                        app.accounts = [StoredAccount(uuid4(), 'Fixture only', 'fixture@example.test', None, 'fixture', str(root / 'fixture-home'), StoredAccountSource.MANAGED_BY_APP, now, now)]
                        app.removed_accounts = []
                        app.runtime_states = {}
                        app.quit()
                        self.assertIs(app.account_store, dependencies.accounts)
                        dependencies.accounts.save_accounts.assert_called_once()
                        dependencies.snapshots.save.assert_called_once()
                self.assertEqual(accounts_path.read_bytes(), original)
                self.assertEqual(snapshots_path.read_bytes(), original)
                self.assertFalse((root / 'preview-profile').exists())

    def test_preview_buttons_cannot_reach_real_auth_or_network(self):
        with isolated_app_dependencies() as dependencies:
            manager = app_module.CodexAccountManager()
            for name in ('add_managed_account', 'reauthenticate', 'switch_active_account'):
                with self.subTest(operation=name), self.assertRaisesRegex(RuntimeError, 'disabled in the visual preview'):
                    getattr(manager, name)()
            with self.assertRaisesRegex(RuntimeError, 'disabled in the visual preview'):
                app_module.fetch_snapshot(Mock())
            with self.assertRaisesRegex(RuntimeError, 'disabled in the visual preview'):
                app_module.restart_codex_desktop()
            self.assertEqual(app_module.TokenUsageTracker().scan(None), {})
            self.assertEqual(app_module.RemoteTokenUsageMirror().sync([], None), [])
            dependencies.accounts.save_accounts.assert_not_called()

    def test_dependencies_are_restored_after_fixture_exits(self):
        original = app_module.AccountStore
        with isolated_app_dependencies():
            self.assertIsNot(app_module.AccountStore, original)
        self.assertIs(app_module.AccountStore, original)


if __name__ == '__main__':
    unittest.main()
