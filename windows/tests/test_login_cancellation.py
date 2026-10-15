from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from codexcontrol_windows.account_manager import CodexLoginRunner, ManagedLoginProcess


class LoginCancellationTests(unittest.TestCase):
    def test_cancel_while_login_is_queued_stops_late_bound_process_outside_lock(self) -> None:
        handle = ManagedLoginProcess()
        handle.cancel()
        process = Mock()
        process.poll.return_value = None

        def verify_unlocked() -> None:
            acquired = handle._lock.acquire(blocking=False)
            if acquired:
                handle._lock.release()
            self.assertTrue(acquired, "Stopping the child must not hold the handle state lock")

        process.terminate.side_effect = verify_unlocked
        handle.bind(process)
        self.assertTrue(handle.cancelled)
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=0.75)

    def test_cancel_after_binding_stops_child_and_remains_cancelled_after_clear(self) -> None:
        handle = ManagedLoginProcess()
        process = Mock()
        process.poll.return_value = None
        handle.bind(process)
        handle.cancel()
        handle.clear()
        self.assertTrue(handle.cancelled)
        process.terminate.assert_called_once_with()

    def test_late_bound_already_finished_process_is_not_signalled(self) -> None:
        handle = ManagedLoginProcess()
        handle.cancel()
        process = Mock()
        process.poll.return_value = 0
        handle.bind(process)
        self.assertTrue(handle.cancelled)
        process.send_signal.assert_not_called()
        process.terminate.assert_not_called()

    def test_runner_reports_cancelled_even_when_queued_child_returns_success(self) -> None:
        handle = ManagedLoginProcess()
        handle.cancel()
        process = Mock()
        process.poll.return_value = None
        process.communicate.return_value = ("Login completed", "")
        process.returncode = 0
        with (
            patch("codexcontrol_windows.account_manager.codex_binary_locator.resolve", return_value="fake-codex.exe"),
            patch("codexcontrol_windows.account_manager.subprocess.Popen", return_value=process),
        ):
            result = CodexLoginRunner.run("test-only-home", handle=handle)
        self.assertEqual(result.outcome, "cancelled")
        process.terminate.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
