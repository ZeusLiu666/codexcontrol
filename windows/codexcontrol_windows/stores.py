from __future__ import annotations

import json
import os
import tempfile
import unicodedata
from pathlib import Path
from typing import Iterable
from uuid import UUID

from .file_locations import ACCOUNTS_FILE, SNAPSHOTS_FILE, ensure_directories
from .models import AccountUsageSnapshot, RemovedAccountIdentity, StoredAccount


def _fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(character for character in normalized if not unicodedata.combining(character)).casefold()


def _atomic_write_json(path: Path, payload: object) -> None:
    """Commit complete JSON on the same volume without truncating old data."""
    serialized = json.dumps(payload, indent=2, sort_keys=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f"{path.name}.", suffix=".tmp", delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
        # Close the temporary file first: Windows does not allow replacing an
        # open file. A same-directory replacement preserves the old data if
        # writing or flushing fails before this final commit.
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


class AccountStore:
    current_version = 2

    def load_accounts(self) -> list[StoredAccount]:
        accounts, _ = self.load_account_list()
        return accounts

    def load_removed_accounts(self) -> list[RemovedAccountIdentity]:
        _, removed_accounts = self.load_account_list()
        return removed_accounts

    def load_account_list(self) -> tuple[list[StoredAccount], list[RemovedAccountIdentity]]:
        if not ACCOUNTS_FILE.exists():
            return [], []

        payload = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
        accounts = [StoredAccount.from_dict(item) for item in payload.get("accounts", [])]
        removed_accounts = [
            RemovedAccountIdentity.from_dict(item)
            for item in payload.get("removedAccounts", [])
            if isinstance(item, dict)
        ]
        return self._sorted(accounts), removed_accounts

    def save_accounts(
        self,
        accounts: Iterable[StoredAccount],
        removed_accounts: Iterable[RemovedAccountIdentity] | None = None,
    ) -> None:
        ensure_directories()
        if removed_accounts is None:
            removed_accounts = self.load_removed_accounts() if ACCOUNTS_FILE.exists() else []

        payload = {
            "version": self.current_version,
            "accounts": [account.to_dict() for account in self._sorted(list(accounts))],
            "removedAccounts": [removed.to_dict() for removed in removed_accounts],
        }
        _atomic_write_json(ACCOUNTS_FILE, payload)

    def merge(self, existing: list[StoredAccount], incoming: list[StoredAccount]) -> list[StoredAccount]:
        result = list(existing)
        for candidate in incoming:
            match_index = next((index for index, account in enumerate(result) if account.matches(candidate)), None)
            if match_index is None:
                result.append(candidate)
                continue

            merged = result[match_index]
            merged.merge_from(candidate)
            result[match_index] = merged

        return self._sorted(result)

    def _sorted(self, accounts: list[StoredAccount]) -> list[StoredAccount]:
        return sorted(accounts, key=lambda account: _fold_text(account.display_name))


class SnapshotStore:
    def load(self) -> dict[UUID, AccountUsageSnapshot]:
        if not SNAPSHOTS_FILE.exists():
            return {}

        payload = json.loads(SNAPSHOTS_FILE.read_text(encoding="utf-8"))
        snapshots = payload.get("snapshots", {})
        result: dict[UUID, AccountUsageSnapshot] = {}
        for key, value in snapshots.items():
            result[UUID(str(key))] = AccountUsageSnapshot.from_dict(value)
        return result

    def save(self, snapshots: dict[UUID, AccountUsageSnapshot]) -> None:
        ensure_directories()
        payload = {
            "snapshots": {
                str(account_id): snapshot.to_dict()
                for account_id, snapshot in snapshots.items()
            }
        }
        _atomic_write_json(SNAPSHOTS_FILE, payload)
