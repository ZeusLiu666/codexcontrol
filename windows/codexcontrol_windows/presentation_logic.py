from __future__ import annotations

from .codex_api import AuthBackedIdentity
from .models import AccountUsageSnapshot, StoredAccount, normalize_identifier


def account_sort_key(
    account: StoredAccount,
    snapshot: AccountUsageSnapshot | None,
) -> tuple[int, int, float, float, str]:
    priority = snapshot.sort_priority if snapshot else 2
    name = account.display_name.casefold()
    if snapshot is None:
        return priority, 1, 0.0, float("inf"), name

    reset_at = snapshot.next_reset_at.timestamp() if snapshot.next_reset_at else float("inf")
    if snapshot.has_usable_quota_now:
        return priority, 0, -snapshot.lowest_remaining_percent, reset_at, name
    return priority, 1, 0.0, reset_at, name


def is_active_account(account: StoredAccount, identity: AuthBackedIdentity | None) -> bool:
    if identity is None:
        return False

    return account.matches_identity(identity.email, identity.auth_subject, identity.provider_account_id)


class AccountIdentityPresentation:
    def __init__(self, accounts):
        self.accounts = accounts

    def preferred(self, accounts):
        from .file_locations import AMBIENT_CODEX_HOME
        import os
        ambient = os.path.normcase(os.path.abspath(AMBIENT_CODEX_HOME))
        return sorted(accounts, key=lambda a: (a.standardized_home_path != ambient, str(a.id)))

    @property
    def duplicate_ids(self):
        groups = {}
        for a in self.accounts:
            provider, subject = a.normalized_provider_account_id, a.normalized_auth_subject
            key = (provider, subject) if provider or subject else a.normalized_email_hint
            if key:
                groups.setdefault(key, []).append(a)
        return {a.id for group in groups.values() for a in self.preferred(group)[1:]}

    def active_id(self, identity):
        matches = self.preferred([a for a in self.accounts if is_active_account(a, identity)])
        return matches[0].id if matches else None

    def display_name(self, account):
        names = [a for a in self.accounts if a.display_name.casefold() == account.display_name.casefold()]
        if len(names) <= 1:
            return account.display_name
        provider = account.normalized_provider_account_id
        if provider and len([a for a in names if a.normalized_provider_account_id == provider]) == 1:
            suffix = account.provider_account_id.strip()[-4:].upper()
        elif account.normalized_auth_subject:
            suffix = account.auth_subject.strip()[-4:].upper()
        else:
            suffix = str(self.preferred(names).index(account) + 1)
        return account.display_name + ' · ' + suffix
