"""No-disk, no-auth dependencies for Tk previews, safe after app was imported."""
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch


@contextmanager
def isolated_app_dependencies():
    # Resolve the already imported module explicitly: file_locations constants
    # may still point at the real profile even after APPDATA has been changed.
    import codexcontrol_windows.app as app_module
    from codexcontrol_windows.stores import AccountStore, SnapshotStore
    from codexcontrol_windows.account_manager import CodexAccountManagerError

    account_store = Mock(spec=AccountStore)
    account_store.load_account_list.return_value = ([], [])
    account_store.merge.side_effect = AccountStore().merge
    snapshot_store = Mock(spec=SnapshotStore)
    snapshot_store.load.return_value = {}
    manager = Mock()
    manager.load_active_identity.return_value = None
    manager.discover_managed_accounts.return_value = []
    manager.discover_ambient_account.return_value = None
    for name in ('add_managed_account', 'reauthenticate', 'switch_active_account'):
        getattr(manager, name).side_effect = CodexAccountManagerError('Account operations are disabled in the visual preview.')
    tracker = Mock()
    tracker.start.return_value = {}
    tracker.scan.return_value = {}
    mirror = Mock()
    mirror.sync.return_value = []
    with ExitStack() as stack:
        for name, value in (('AccountStore', account_store), ('SnapshotStore', snapshot_store),
                            ('CodexAccountManager', manager), ('TokenUsageTracker', tracker),
                            ('RemoteTokenUsageMirror', mirror)):
            stack.enter_context(patch.object(app_module, name, return_value=value))
        stack.enter_context(patch.object(app_module, 'fetch_snapshot', side_effect=RuntimeError('Network refresh is disabled in the visual preview.')))
        stack.enter_context(patch.object(app_module, 'restart_codex_desktop', side_effect=RuntimeError('Desktop restart is disabled in the visual preview.')))
        yield SimpleNamespace(accounts=account_store, snapshots=snapshot_store, manager=manager, tracker=tracker, mirror=mirror)
