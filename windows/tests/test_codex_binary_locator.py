from __future__ import annotations

import json
import os
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codexcontrol_windows import codex_binary_locator as locator


class CodexBinaryLocatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.local = self.root / "Local"
        self.home = self.root / "Home"
        self.start_patch(patch.dict(os.environ, {"LOCALAPPDATA": str(self.local)}))
        self.start_patch(patch.object(locator.Path, "home", return_value=self.home))
        self.which = self.start_patch(patch.object(locator.shutil, "which", return_value=None))
        self.where = self.start_patch(patch.object(locator, "_where_candidates", return_value=[]))
        self.appx = self.start_patch(patch.object(locator, "_appx_path_candidates", return_value=[]))
        self.run = self.start_patch(patch.object(locator.subprocess, "run", side_effect=self.version_success))

    def start_patch(self, patcher):
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    @staticmethod
    def version_success(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, "codex-cli 0.164.0-alpha.11.1\n", "")

    def executable(self, relative: str, subsystem: int = 3) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = bytearray(256)
        payload[:2] = b"MZ"
        struct.pack_into("<I", payload, 60, 128)
        payload[128:132] = b"PE\0\0"
        struct.pack_into("<H", payload, 128 + 24 + 68, subsystem)
        path.write_bytes(payload)
        return path

    def cache_executable(self, hash_name: str) -> Path:
        return self.executable(f"Local/OpenAI/Codex/bin/{hash_name}/codex.exe")

    def test_finds_desktop_hash_cli_without_cli_on_path_or_powershell_query(self) -> None:
        cli = self.cache_executable("2993767bd1dfb009")

        self.assertEqual(locator.resolve(), str(cli))
        self.which.assert_called_once_with("codex")
        self.appx.assert_not_called()
        self.assertEqual(self.run.call_args.args[0], [str(cli), "--version"])
        self.assertEqual(self.run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(self.run.call_args.kwargs["timeout"], locator._VERSION_TIMEOUT_SECONDS)
        self.assertEqual(self.run.call_args.kwargs["creationflags"], getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def test_desktop_update_is_rediscovered_and_rg_only_directory_is_ignored(self) -> None:
        old = self.cache_executable("old-cli")
        os.utime(old, ns=(100, 100))
        self.assertEqual(locator.resolve(), str(old))
        new = self.cache_executable("new-cli")
        os.utime(new, ns=(200, 200))
        rg = self.root / "Local/OpenAI/Codex/bin/newest-rg-only/rg.exe"
        rg.parent.mkdir(parents=True)
        rg.write_bytes(b"rg")
        os.utime(rg.parent, ns=(300, 300))

        self.assertEqual(locator.resolve(), str(new))
        self.assertEqual(locator._desktop_cache_candidates(), [new, old])
        new.unlink()
        self.assertEqual(locator.resolve(), str(old))

    def test_current_msix_resources_cli_is_used_without_extracted_cache(self) -> None:
        cli = self.executable("WindowsApps/OpenAI.Codex_2.0_x64/app/resources/codex.exe")
        self.appx.return_value = [cli]

        self.assertEqual(locator.resolve(), str(cli))
        self.appx.assert_called_once_with()

    def test_gui_on_path_is_rejected_without_launching_it(self) -> None:
        gui = self.executable("WindowsApps/OpenAI.Codex_2.0_x64/app/Codex.exe", subsystem=2)
        cli = self.cache_executable("actual-cli")
        self.which.return_value = str(gui)

        self.assertEqual(locator.resolve(), str(cli))
        self.assertEqual([call.args[0] for call in self.run.call_args_list], [[str(cli), "--version"]])

    def test_timed_out_or_invalid_newer_cli_falls_back(self) -> None:
        valid = self.cache_executable("valid-old")
        timeout = self.cache_executable("timeout-new")
        wrong = self.cache_executable("wrong-newest")
        for order, candidate in enumerate([valid, timeout, wrong], start=1):
            os.utime(candidate, ns=(order * 100, order * 100))

        def probe(args, **kwargs):
            if args[0] == str(timeout):
                raise subprocess.TimeoutExpired(args, kwargs["timeout"])
            if args[0] == str(wrong):
                return subprocess.CompletedProcess(args, 0, "Desktop 9.0.0\n", "")
            return self.version_success(args, **kwargs)

        self.run.side_effect = probe
        self.assertEqual(locator.resolve(), str(valid))

    def test_legacy_fixed_location_still_works(self) -> None:
        cli = self.executable("Local/OpenAI/Codex/bin/codex.exe")
        self.assertEqual(locator.resolve(), str(cli))
        self.appx.assert_not_called()

    def test_batch_wrapper_on_path_is_not_rejected_as_non_pe(self) -> None:
        wrapper = self.root / "codex.cmd"
        wrapper.write_text("@echo off\n", encoding="utf-8")
        self.which.return_value = str(wrapper)
        self.assertEqual(locator.resolve(), str(wrapper))

    def test_invalid_pe_is_not_launched(self) -> None:
        candidate = self.root / "codex.exe"
        candidate.write_bytes(b"MZtruncated")
        self.assertFalse(locator._is_codex_cli(candidate))
        self.run.assert_not_called()

    def test_version_failure_with_codex_text_is_rejected(self) -> None:
        cli = self.cache_executable("broken-cli")
        self.run.return_value = subprocess.CompletedProcess([str(cli)], 1, "codex-cli 1.2.3\n", "")
        self.run.side_effect = None
        self.assertIsNone(locator.resolve())


class AppxDiscoveryTests(unittest.TestCase):
    def test_queries_registered_packages_and_preserves_version_order(self) -> None:
        locations = [r"C:\Program Files\WindowsApps\OpenAI.Codex_2.0_x64", r"C:\Program Files\WindowsApps\OpenAI.Codex_1.0_x64"]
        result = subprocess.CompletedProcess([], 0, json.dumps(locations), "")
        with patch.object(locator.subprocess, "run", return_value=result) as run:
            candidates = locator._appx_path_candidates()

        self.assertEqual(candidates[0], Path(locations[0]) / "app/resources/codex.exe")
        self.assertEqual(candidates[2], Path(locations[1]) / "app/resources/codex.exe")
        args = run.call_args.args[0]
        self.assertEqual(args[:5], ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command"])
        self.assertIn("Get-AppxPackage -Name OpenAI.Codex", args[5])
        self.assertIn("Sort-Object Version -Descending", args[5])
        self.assertNotIn(locations[0], args[5])
        self.assertEqual(run.call_args.kwargs["timeout"], locator._DISCOVERY_TIMEOUT_SECONDS)
        self.assertEqual(run.call_args.kwargs["creationflags"], getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def test_accepts_single_package_json_and_unicode_paths(self) -> None:
        location = str(Path("C:/Users/测试/WindowsApps/OpenAI.Codex_2.0_x64"))
        result = subprocess.CompletedProcess([], 0, "\ufeff" + json.dumps(location), "")
        with patch.object(locator.subprocess, "run", return_value=result):
            self.assertEqual(locator._appx_path_candidates()[0], Path(location) / "app/resources/codex.exe")

    def test_unavailable_or_timed_out_package_query_is_safe(self) -> None:
        for failure in (OSError("PowerShell unavailable"), subprocess.TimeoutExpired(["powershell.exe"], 4)):
            with self.subTest(failure=failure), patch.object(locator.subprocess, "run", side_effect=failure):
                self.assertEqual(locator._appx_path_candidates(), [])

    def test_invalid_json_and_package_query_failures_are_safe(self) -> None:
        for code, output in [(1, "[]"), (0, "invalid JSON"), (0, "null"), (0, '{"unexpected": true}'), (0, "[null, 4, \"\"]")]:
            with self.subTest(code=code, output=output):
                result = subprocess.CompletedProcess([], code, output, "")
                with patch.object(locator.subprocess, "run", return_value=result):
                    self.assertEqual(locator._appx_path_candidates(), [])


if __name__ == "__main__":
    unittest.main()
