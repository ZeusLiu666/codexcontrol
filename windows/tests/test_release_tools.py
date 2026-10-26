"""Release containment and reproducibility checks using synthetic payloads."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from release_tools import PORTABLE_FILES, ZIP_TIMESTAMP, portable_zip, requirement_pins, version_resource


class ReleaseToolsTests(unittest.TestCase):
    def test_portable_archive_preserves_the_multi_size_brand_icon(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "payload"
            source.mkdir()
            for name in PORTABLE_FILES:
                (source / name).write_bytes(b"synthetic fixture")
            icon = Path(__file__).resolve().parents[1] / "build-assets" / "CodexControl.ico"
            (source / "CodexControl.ico").write_bytes(icon.read_bytes())
            portable_zip(source, root / "portable.zip")
            with zipfile.ZipFile(root / "portable.zip") as archive:
                self.assertEqual(archive.read("CodexControl.ico"), icon.read_bytes())
                self.assertEqual(archive.namelist().count("CodexControl.ico"), 1)

    def test_portable_release_requires_a_separate_brand_icon(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "payload"
            source.mkdir()
            for name in PORTABLE_FILES:
                if name != "CodexControl.ico":
                    (source / name).write_bytes(b"fixture")
            with self.assertRaisesRegex(ValueError, "allowlist"):
                portable_zip(source, root / "incomplete.zip")
            self.assertFalse((root / "incomplete.zip").exists())

    def test_installer_references_the_installed_versioned_icon_everywhere(self):
        windows = Path(__file__).resolve().parents[1]
        text = (windows / "CodexControl.iss").read_text(encoding="utf-8")
        sections = {}
        section = None
        for line in text.splitlines():
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
                sections[section] = []
            elif section and line.strip() and not line.lstrip().startswith(";"):
                sections[section].append(line)
        installed_icon = "{app}\\CodexControl-{#AppVersion}.ico"
        self.assertIn("SetupIconFile={#PayloadDir}\\CodexControl.ico", sections["Setup"])
        self.assertIn("UninstallDisplayIcon=" + installed_icon, sections["Setup"])
        icon_files = [line for line in sections["Files"] if 'CodexControl.ico"' in line]
        self.assertEqual(len(icon_files), 1)
        self.assertIn('DestName: "CodexControl-{#AppVersion}.ico"', icon_files[0])
        self.assertEqual(len(sections["Icons"]), 3)
        for shortcut in sections["Icons"]:
            self.assertIn('IconFilename: "' + installed_icon + '"', shortcut)
            self.assertIn('Filename: "{app}\\CodexControl.exe"', shortcut)
            self.assertIn('AppUserModelID: "CodexControl.Windows"', shortcut)

    @unittest.skipUnless(shutil.which("powershell.exe"), "PowerShell is required for the Windows installer helper")
    def test_portable_icon_filename_rejects_version_path_injection(self):
        installer = Path(__file__).resolve().parents[1] / "install.ps1"
        # Load only the pure helper AST; never execute installation, shortcuts,
        # process termination or any other top-level installation code.
        script = r'''
$ErrorActionPreference = 'Stop'
$source = $env:CODEXCONTROL_TEST_INSTALLER
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($source, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Installer PowerShell did not parse.' }
$helper = $ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -eq 'Get-CodexControlIconFileName'
}, $true)
if (-not $helper) { throw 'Icon filename helper is missing.' }
. ([scriptblock]::Create($helper.Extent.Text))
$valid = @('1.2.9', '1.2.9.0', '65535.0.0') | ForEach-Object { Get-CodexControlIconFileName $_ }
$invalid = @('', '1.2', '1.2.9-beta', '1.2.9/../../private', '1.2.9\auth.json', "1.2.9`n", '65536.0.0', '999999999999999999999.0.0')
$rejected = 0
foreach ($version in $invalid) {
    try { $null = Get-CodexControlIconFileName $version }
    catch { $rejected++ }
}
@{ valid=$valid; invalid_count=$invalid.Count; rejected=$rejected } | ConvertTo-Json -Compress
'''
        environment = os.environ.copy()
        environment["CODEXCONTROL_TEST_INSTALLER"] = str(installer)
        result = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            text=True, encoding="utf-8", errors="replace", timeout=15, check=False, env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout.lstrip("\ufeff"))
        self.assertEqual(report["valid"], ["CodexControl-1.2.9.ico", "CodexControl-1.2.9.0.ico", "CodexControl-65535.0.0.ico"])
        self.assertEqual(report["rejected"], report["invalid_count"])

    def test_archive_is_deterministic_and_has_generic_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "payload"
            source.mkdir()
            for name in PORTABLE_FILES:
                (source / name).write_text(f"synthetic {name}", encoding="utf-8")
            portable_zip(source, root / "first.zip")
            for name in PORTABLE_FILES:
                (source / name).touch()
            portable_zip(source, root / "second.zip")
            self.assertEqual(hashlib.sha256((root / "first.zip").read_bytes()).digest(),
                             hashlib.sha256((root / "second.zip").read_bytes()).digest())
            with zipfile.ZipFile(root / "first.zip") as archive:
                self.assertEqual(archive.namelist(), list(PORTABLE_FILES))
                for info in archive.infolist():
                    self.assertEqual(info.date_time, ZIP_TIMESTAMP)
                    self.assertEqual(info.create_system, 0)
                    self.assertEqual(info.extra, b"")
                    self.assertEqual(info.comment, b"")

    def test_archive_rejects_unexpected_private_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "payload"
            source.mkdir()
            for name in PORTABLE_FILES:
                (source / name).write_bytes(b"fixture")
            (source / "auth.json").write_bytes(b"synthetic private fixture")
            with self.assertRaisesRegex(ValueError, "allowlist"):
                portable_zip(source, root / "unsafe.zip")
            self.assertFalse((root / "unsafe.zip").exists())

    def test_archive_rejects_missing_license(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "payload"
            source.mkdir()
            for name in PORTABLE_FILES:
                if name != "LICENSE":
                    (source / name).write_bytes(b"fixture")
            with self.assertRaisesRegex(ValueError, "allowlist"):
                portable_zip(source, root / "unsafe.zip")

    def test_archive_rejects_directory_named_like_an_allowed_file(self):
        for filename in ("LICENSE", "CodexControl.ico"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "payload"
                source.mkdir()
                for name in PORTABLE_FILES:
                    (source / name).write_bytes(b"fixture")
                (source / filename).unlink()
                (source / filename).mkdir()
                with self.assertRaisesRegex(ValueError, "ordinary files"):
                    portable_zip(source, root / "unsafe.zip")
                self.assertFalse((root / "unsafe.zip").exists())

    def test_release_requirements_must_be_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "requirements.txt"
            path.write_text("# fixture\nexample==1.2.3\n", encoding="utf-8")
            self.assertEqual(requirement_pins(path), {"example": "1.2.3"})
            path.write_text("example>=1.2.3\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exact"):
                requirement_pins(path)

    def test_version_metadata_is_generic(self):
        with tempfile.TemporaryDirectory() as temporary:
            resource = Path(temporary) / "version.txt"
            version_resource("1.2.8", resource)
            text = resource.read_text(encoding="utf-8")
            self.assertIn("CodexControl contributors", text)
            self.assertIn("1.2.8", text)
            self.assertNotIn(temporary, text)
            self.assertNotIn(str(Path.home()), text)

    def test_version_rejects_resource_overflow_and_injection(self):
        for version in ("65536.0.0", "1.2.3\nmalformed", "1.2"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(ValueError):
                    version_resource(version, Path(temporary) / "version.txt")


if __name__ == "__main__":
    unittest.main()
