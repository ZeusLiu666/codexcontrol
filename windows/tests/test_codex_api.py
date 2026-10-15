from __future__ import annotations

import base64
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from codexcontrol_windows.codex_api import (
    AuthCredentials,
    CodexApiError,
    _account_id_from_id_token,
    _fetch_snapshot,
    _identity_from_credentials,
    _normalize_window_roles,
    _parse_chatgpt_base_url,
    _readable_server_message,
    fetch_snapshot,
)
from codexcontrol_windows.models import AccountUsageSnapshot, StoredAccount, StoredAccountSource, UsageWindowSnapshot


def _id_token(email: str, subject: str, account_id: str) -> str:
    payload = {
        "email": email,
        "sub": subject,
        "https://api.openai.com/auth": {
            "chatgpt_plan_type": "team",
            "chatgpt_account_id": account_id,
        },
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    return f"header.{encoded}.signature"


def _write_auth(home_path: Path, access_token: str, refresh_token: str, id_token: str, last_refresh: datetime) -> None:
    home_path.mkdir(parents=True, exist_ok=True)
    payload = {
        "tokens": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "id_token": id_token,
        },
        "last_refresh": last_refresh.isoformat().replace("+00:00", "Z"),
    }
    (home_path / "auth.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


class CodexApiTests(unittest.TestCase):
    def test_identity_from_credentials_uses_id_token_payload(self) -> None:
        payload = {
            "email": "user@example.com",
            "sub": "auth0|user",
            "https://api.openai.com/auth": {
                "chatgpt_plan_type": "team",
                "chatgpt_account_id": "provider-1",
            },
        }
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
        credentials = AuthCredentials(
            access_token="token",
            refresh_token="",
            id_token=f"header.{encoded}.signature",
            account_id="provider-1",
            last_refresh=datetime(2026, 4, 18, tzinfo=timezone.utc),
        )

        identity = _identity_from_credentials(credentials)

        self.assertEqual(identity.email, "user@example.com")
        self.assertEqual(identity.auth_subject, "auth0|user")
        self.assertEqual(identity.plan, "team")
        self.assertEqual(identity.provider_account_id, "provider-1")

    def test_account_id_from_id_token_is_used_when_token_field_is_missing(self) -> None:
        id_token = _id_token("user@example.com", "auth0|user", "provider-1")

        self.assertEqual(_account_id_from_id_token(id_token), "provider-1")

    def test_parse_chatgpt_base_url(self) -> None:
        contents = """
        # comment
        chatgpt_base_url = "https://example.com/custom"
        """

        self.assertEqual(_parse_chatgpt_base_url(contents), "https://example.com/custom")

    def test_readable_server_message_hides_proxy_eof_details(self) -> None:
        message = _readable_server_message(
            '{"error":"<urlopen error EOF occurred in violation of protocol (_ssl.c:1129)>"}'
        )

        self.assertEqual(message, "the upstream connection closed before the response finished.")

    def test_transient_error_preserves_existing_snapshot(self) -> None:
        error = CodexApiError("Codex usage API is temporarily unavailable (502).", transient=True)

        self.assertTrue(error.preserve_snapshot)

    def test_normalize_window_roles_swaps_weekly_into_secondary_slot(self) -> None:
        now = datetime(2026, 4, 18, tzinfo=timezone.utc)
        weekly = UsageWindowSnapshot(used_percent=12.0, reset_at=now, limit_window_seconds=604_800)
        session = UsageWindowSnapshot(used_percent=45.0, reset_at=now, limit_window_seconds=18_000)

        primary, secondary = _normalize_window_roles(weekly, session)

        self.assertEqual(primary.limit_window_seconds, 18_000)
        self.assertEqual(secondary.limit_window_seconds, 604_800)

    def test_fetch_snapshot_can_skip_verification_for_bulk_refresh(self) -> None:
        now = datetime(2026, 4, 18, tzinfo=timezone.utc)
        account = StoredAccount(
            id=uuid4(),
            nickname=None,
            email_hint="user@example.com",
            auth_subject="auth0|user",
            provider_account_id="provider-1",
            codex_home_path="C:/temp/account",
            source=StoredAccountSource.MANAGED_BY_APP,
            created_at=now,
            updated_at=now,
            last_authenticated_at=now,
        )
        credentials = AuthCredentials(
            access_token="token",
            refresh_token="",
            id_token=None,
            account_id="provider-1",
            last_refresh=now,
        )
        snapshot = AccountUsageSnapshot(
            email="user@example.com",
            provider_account_id="provider-1",
            plan="team",
            allowed=True,
            limit_reached=False,
            primary_window=UsageWindowSnapshot(used_percent=30.0, reset_at=now, limit_window_seconds=18_000),
            secondary_window=None,
            credits=None,
            updated_at=now,
        )

        with (
            patch("codexcontrol_windows.codex_api._load_credentials", return_value=credentials),
            patch("codexcontrol_windows.codex_api._fetch_snapshot", return_value=snapshot) as fast_fetch,
            patch("codexcontrol_windows.codex_api._fetch_verified_snapshot", return_value=snapshot) as verified_fetch,
        ):
            result = fetch_snapshot(account, verify_live_data=False)

        self.assertIs(result, snapshot)
        fast_fetch.assert_called_once()
        verified_fetch.assert_not_called()

    def test_raw_fetch_snapshot_uses_credentials_identity_without_reloading_auth(self) -> None:
        now = datetime(2026, 4, 18, tzinfo=timezone.utc)
        payload = {
            "email": "user@example.com",
            "sub": "auth0|user",
            "https://api.openai.com/auth": {
                "chatgpt_plan_type": "team",
                "chatgpt_account_id": "provider-1",
            },
        }
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
        credentials = AuthCredentials(
            access_token="token",
            refresh_token="",
            id_token=f"header.{encoded}.signature",
            account_id="provider-1",
            last_refresh=now,
        )
        api_payload = {
            "plan_type": "team",
            "rate_limit": {
                "allowed": True,
                "limit_reached": False,
                "primary_window": {
                    "used_percent": 30.0,
                    "reset_at": now.timestamp(),
                    "limit_window_seconds": 18_000,
                },
            },
        }

        with (
            patch("codexcontrol_windows.codex_api._fetch_usage", return_value=api_payload),
            patch("codexcontrol_windows.codex_api.load_identity", side_effect=AssertionError("should not reload auth")),
        ):
            snapshot = _fetch_snapshot("C:/temp/account", credentials, "fallback@example.com")

        self.assertEqual(snapshot.email, "user@example.com")
        self.assertEqual(snapshot.provider_account_id, "provider-1")
        self.assertEqual(snapshot.plan, "team")

    def test_fetch_snapshot_recovers_from_duplicate_home_when_refresh_token_is_stale(self) -> None:
        now = datetime(2026, 4, 18, tzinfo=timezone.utc)
        stale = now - timedelta(days=30)
        provider_id = "provider-1"
        token = _id_token("user@example.com", "auth0|user", provider_id)
        snapshot = AccountUsageSnapshot(
            email="user@example.com",
            provider_account_id=provider_id,
            plan="team",
            allowed=True,
            limit_reached=False,
            primary_window=UsageWindowSnapshot(used_percent=30.0, reset_at=now, limit_window_seconds=18_000),
            secondary_window=None,
            credits=None,
            updated_at=now,
        )

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            selected_home = root / "managed-homes" / "selected"
            recovery_home = root / "managed-homes" / "recovery"
            ambient_home = root / ".codex"
            _write_auth(selected_home, "stale-access", "stale-refresh", token, stale)
            _write_auth(recovery_home, "recovery-access", "recovery-refresh", token, now)

            account = StoredAccount(
                id=uuid4(),
                nickname=None,
                email_hint="user@example.com",
                auth_subject="auth0|user",
                provider_account_id=provider_id,
                codex_home_path=str(selected_home),
                source=StoredAccountSource.MANAGED_BY_APP,
                created_at=now,
                updated_at=now,
                last_authenticated_at=now,
            )

            def refresh(credentials: AuthCredentials) -> AuthCredentials:
                if credentials.refresh_token == "stale-refresh":
                    raise CodexApiError("The refresh token can no longer be reused. Sign in again for this account.")
                return AuthCredentials(
                    access_token="fresh-access",
                    refresh_token="fresh-refresh",
                    id_token=credentials.id_token,
                    account_id=credentials.account_id,
                    last_refresh=now,
                )

            with (
                patch("codexcontrol_windows.codex_api.MANAGED_HOMES_DIRECTORY", root / "managed-homes"),
                patch("codexcontrol_windows.codex_api.AMBIENT_CODEX_HOME", ambient_home),
                patch("codexcontrol_windows.codex_api._refresh", side_effect=refresh),
                patch("codexcontrol_windows.codex_api._fetch_snapshot", return_value=snapshot),
            ):
                result = fetch_snapshot(account, verify_live_data=False)

            self.assertIs(result, snapshot)
            selected_payload = json.loads((selected_home / "auth.json").read_text(encoding="utf-8"))
            self.assertEqual(selected_payload["tokens"]["refresh_token"], "fresh-refresh")
            self.assertEqual(selected_payload["tokens"]["account_id"], provider_id)


if __name__ == "__main__":
    unittest.main()
