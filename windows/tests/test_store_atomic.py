from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from codexcontrol_windows.stores import AccountStore, SnapshotStore


class AtomicStoreTests(unittest.TestCase):
    def _exercise_failure(self, store_class, path_constant: str, save_method: str, failure_point: str) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "persisted.json"
            previous = b'{"accounts": [], "snapshots": {}, "keep": "original"}'
            destination.write_bytes(previous)
            with (
                patch(f"codexcontrol_windows.stores.{path_constant}", destination),
                patch("codexcontrol_windows.stores.ensure_directories"),
                patch(f"codexcontrol_windows.stores.os.{failure_point}", side_effect=OSError("disk failure")),
            ):
                with self.assertRaisesRegex(OSError, "disk failure"):
                    getattr(store_class(), save_method)([] if store_class is AccountStore else {})
            self.assertEqual(destination.read_bytes(), previous)
            self.assertEqual(list(root.iterdir()), [destination])

    def test_flush_failure_preserves_accounts_and_cleans_temporary_file(self) -> None:
        self._exercise_failure(AccountStore, "ACCOUNTS_FILE", "save_accounts", "fsync")

    def test_replace_failure_preserves_snapshots_and_cleans_temporary_file(self) -> None:
        self._exercise_failure(SnapshotStore, "SNAPSHOTS_FILE", "save", "replace")

    def test_success_replaces_complete_json_in_same_directory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "accounts.json"
            destination.write_text('{"accounts": [], "removedAccounts": [], "old": true}', encoding="utf-8")
            with (
                patch("codexcontrol_windows.stores.ACCOUNTS_FILE", destination),
                patch("codexcontrol_windows.stores.ensure_directories"),
            ):
                AccountStore().save_accounts([], [])
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), {
                "version": AccountStore.current_version, "accounts": [], "removedAccounts": [],
            })
            self.assertEqual(list(root.iterdir()), [destination])


if __name__ == "__main__":
    unittest.main()
